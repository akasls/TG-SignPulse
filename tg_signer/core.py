import asyncio
import json
import logging
import os
import pathlib
import random
import re
import sqlite3
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from datetime import time as dt_time
from typing import (
    BinaryIO,
    Generic,
    List,
    Optional,
    Type,
    TypeVar,
    Union,
)
from urllib import parse

import httpx
from croniter import CroniterBadCronError, croniter
from pydantic import BaseModel, ValidationError
from pyrogram import Client as BaseClient
from pyrogram import errors, filters, raw
from pyrogram.enums import ChatMembersFilter, ChatType
from pyrogram.handlers import EditedMessageHandler, MessageHandler
from pyrogram.methods.utilities.idle import idle
from pyrogram.session import Session
from pyrogram.storage import MemoryStorage
from pyrogram.types import (
    Chat,
    InlineKeyboardMarkup,
    Message,
    Object,
    ReplyKeyboardMarkup,
    User,
)

from tg_signer.config import (
    ActionT,
    BaseJSONConfig,
    ChooseOptionByImageAction,
    ClickButtonByCalculationProblemAction,
    ClickKeyboardByTextAction,
    HttpCallback,
    MatchConfig,
    MonitorConfig,
    ReplyByCalculationProblemAction,
    ReplyByImageRecognitionAction,
    SendDiceAction,
    SendTextAction,
    SignChatV3,
    SignConfigV3,
    SupportAction,
    UDPForward,
)

from .ai_tools import AITools, OpenAIConfigManager
from .notification.server_chan import sc_send
from .utils import UserInput, print_to_user

# Monkeypatch sqlite3.connect to increase default timeout
_original_sqlite3_connect = sqlite3.connect


def _patched_sqlite3_connect(*args, **kwargs):
    # Force timeout to be at least 10 seconds, even if Pyrogram sets it to 1
    if "timeout" in kwargs:
        if kwargs["timeout"] < 30:
            kwargs["timeout"] = 30
    else:
        kwargs["timeout"] = 30
    return _original_sqlite3_connect(*args, **kwargs)


sqlite3.connect = _patched_sqlite3_connect

# Monkeypatch pyrogram.Client.invoke to add backpressure and retry logic for updates
_original_invoke = BaseClient.invoke
_get_channel_diff_semaphore = asyncio.Semaphore(50)

async def _patched_invoke(self, query, *args, **kwargs):
    if isinstance(query, (raw.functions.updates.GetChannelDifference, raw.functions.updates.GetDifference)):
        # Disable Pyrogram's internal sleep and retry mechanisms to prevent blocking the semaphore indefinitely
        kwargs.setdefault("sleep_threshold", 0)
        kwargs["retries"] = 0
        kwargs.setdefault("timeout", 5.0)

        async with _get_channel_diff_semaphore:
            max_retries = 2
            base_delay = 1.0
            for attempt in range(max_retries + 1):
                try:
                    return await _original_invoke(self, query, *args, **kwargs)
                except Exception as e:
                    err_str = str(e).lower()
                    if isinstance(e, asyncio.TimeoutError) or "timeout" in err_str or "connection" in err_str or "flood" in err_str or "network" in err_str:
                        if attempt < max_retries:
                            delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                            if "flood" in err_str and hasattr(e, "value"):
                                delay = min(e.value, 3.0)  # Wait for a shorter time, max 3 seconds
                            await asyncio.sleep(delay)
                            continue

                        logger.warning(f"Drop updates for {type(query).__name__} due to error: {e}")

                        if isinstance(query, raw.functions.updates.GetChannelDifference):
                            from pyrogram.raw.types.updates import (
                                ChannelDifferenceEmpty,
                            )
                            return ChannelDifferenceEmpty(pts=query.pts, timeout=0, final=True)
                        elif isinstance(query, raw.functions.updates.GetDifference):
                            from pyrogram.raw.types.updates import DifferenceEmpty
                            return DifferenceEmpty(date=query.date, seq=query.pts)
                    raise
    return await _original_invoke(self, query, *args, **kwargs)

BaseClient.invoke = _patched_invoke

logger = logging.getLogger("tg-signer")

DICE_EMOJIS = ("🎲", "🎯", "🏀", "⚽", "🎳", "🎰")

Session.START_TIMEOUT = 5  # 原始超时时间为2秒，但一些代理访问会超时，所以这里调大一点

OPENAI_USE_PROMPT = "当前任务需要配置大模型，请确保运行前正确设置`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`等环境变量，或通过`tg-signer llm-config`持久化配置。"


def readable_message(message: Message):
    s = "\nMessage: "
    s += f"\n  text: {message.text or ''}"
    if message.photo:
        s += f"\n  图片: [({message.photo.width}x{message.photo.height}) {message.caption}]"
    if message.reply_markup:
        if isinstance(message.reply_markup, InlineKeyboardMarkup):
            s += "\n  InlineKeyboard: "
            for row in message.reply_markup.inline_keyboard:
                s += "\n   "
                for button in row:
                    s += f"{button.text} | "
        elif isinstance(message.reply_markup, ReplyKeyboardMarkup):
            s += "\n  ReplyKeyboard: "
            for row in message.reply_markup.keyboard:
                s += "\n   "
                for button in row:
                    s += f"{getattr(button, 'text', str(button))} | "
    return s


def readable_chat(chat: Chat):
    if chat.type == ChatType.BOT:
        type_ = "BOT"
    elif chat.type == ChatType.GROUP:
        type_ = "群组"
    elif chat.type == ChatType.SUPERGROUP:
        type_ = "超级群组"
    elif chat.type == ChatType.CHANNEL:
        type_ = "频道"
    else:
        type_ = "个人"

    none_or_dash = lambda x: x or "-"  # noqa: E731

    return f"id: {chat.id}, username: {none_or_dash(chat.username)}, title: {none_or_dash(chat.title)}, type: {type_}, name: {none_or_dash(chat.first_name)}"


_CLIENT_INSTANCES: dict[str, "Client"] = {}

# reference counts and async locks for shared client lifecycle management
# Keyed by account name. Use asyncio locks to serialize start/stop operations
# so multiple coroutines in the same process can safely share one Client.
_CLIENT_REFS: defaultdict[str, int] = defaultdict(int)
_CLIENT_ASYNC_LOCKS: dict[str, asyncio.Lock] = {}


class Client(BaseClient):
    def __init__(self, name: str, *args, **kwargs):
        key = kwargs.pop("key", None)
        super().__init__(name, *args, **kwargs)
        self.key = key or str(pathlib.Path(self.workdir).joinpath(self.name).resolve())
        if self.in_memory and not self.session_string:
            self.load_session_string()
            self.storage = MemoryStorage(self.name, self.session_string)

    async def __aenter__(self):
        lock = _CLIENT_ASYNC_LOCKS.get(self.key)
        if lock is None:
            lock = asyncio.Lock()
            _CLIENT_ASYNC_LOCKS[self.key] = lock
        async with lock:
            _CLIENT_REFS[self.key] += 1
            if _CLIENT_REFS[self.key] == 1:
                # Retry loop for database locks
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        if not self.is_connected:
                            await self.connect()

                        try:
                            await self.get_me()
                        except Exception as e:
                            # Prevent interactive login attempt
                            raise ConnectionError(f"Session invalid: {e}")

                        try:
                            await self.start()
                        except ConnectionError as e:
                            if "already connected" not in str(e).lower():
                                raise e

                        # Enable WAL mode after start
                        if hasattr(self, "storage") and hasattr(self.storage, "conn"):
                            try:
                                self.storage.conn.execute("PRAGMA journal_mode=WAL")
                                self.storage.conn.execute("PRAGMA busy_timeout=30000")
                            except Exception as e:
                                logger.error(f"Failed to enable WAL mode: {e}")

                        # Success! Break loop
                        break

                    except Exception as e:
                        # If this is a database lock and we have retries left, wait and retry
                        is_locked = "database is locked" in str(e)
                        if is_locked and attempt < max_retries - 1:
                            # Cleanup before retry
                            try:
                                if self.is_connected:
                                    await self.stop()
                            except Exception:
                                pass

                            wait_time = (attempt + 1) * 2
                            logger.warning(f"Database locked when starting client {self.name}, retrying in {wait_time}s... ({attempt + 1}/{max_retries})")
                            await asyncio.sleep(wait_time)
                            continue

                        # If execution reaches here, it's a fatal error or retries exhausted
                        # Rollback the ref count
                        _CLIENT_REFS[self.key] -= 1
                        if _CLIENT_REFS[self.key] <= 0:
                            _CLIENT_REFS.pop(self.key, None)
                            _CLIENT_INSTANCES.pop(self.key, None)
                            try:
                                await self.stop()
                            except Exception:
                                pass
                        raise e
            return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        lock = _CLIENT_ASYNC_LOCKS.get(self.key)
        if lock is None:
            return
        async with lock:
            _CLIENT_REFS[self.key] -= 1
            if _CLIENT_REFS[self.key] == 0:
                try:
                    await self.stop()
                except Exception:
                    pass
                # DO NOT POP FROM _CLIENT_INSTANCES HERE.
                # Keep the client instance cached so future connections reuse the safe asyncio lock mechanisms.

    @property
    def session_string_file(self):
        return self.workdir / (self.name + ".session_string")

    async def save_session_string(self):
        with open(self.session_string_file, "w") as fp:
            fp.write(await self.export_session_string())

    def load_session_string(self):
        logger.info("Loading session_string from local file.")
        if self.session_string_file.is_file():
            with open(self.session_string_file, "r") as fp:
                self.session_string = fp.read()
                logger.info("The session_string has been loaded.")
        return self.session_string

    async def log_out(
        self,
    ):
        await super().log_out()
        if self.session_string_file.is_file():
            os.remove(self.session_string_file)


def get_api_config():
    api_id_env = os.environ.get("TG_API_ID")
    api_hash_env = os.environ.get("TG_API_HASH")

    api_id = 611335
    if api_id_env:
        try:
            api_id = int(api_id_env)
        except (TypeError, ValueError):
            pass

    if isinstance(api_hash_env, str) and api_hash_env.strip():
        api_hash = api_hash_env.strip()
    else:
        api_hash = "d524b414d21f4d37f08684c1df41ac9c"

    return api_id, api_hash


def get_proxy(proxy: str = None):
    proxy = proxy or os.environ.get("TG_PROXY")
    if proxy:
        r = parse.urlparse(proxy)
        return {
            "scheme": r.scheme,
            "hostname": r.hostname,
            "port": r.port,
            "username": r.username,
            "password": r.password,
        }
    return None


def get_client(
    name: str = "my_account",
    proxy: dict = None,
    workdir: Union[str, pathlib.Path] = ".",
    session_string: str = None,
    in_memory: bool = False,
    api_id: int = None,
    api_hash: str = None,
    **kwargs,
) -> Client:
    proxy = proxy or get_proxy()
    if not api_id or not api_hash:
        _api_id, _api_hash = get_api_config()
        api_id = api_id or _api_id
        api_hash = api_hash or _api_hash

    key = str(pathlib.Path(workdir).joinpath(name).resolve())
    if key in _CLIENT_INSTANCES:
        return _CLIENT_INSTANCES[key]
    client = Client(
        name,
        api_id=api_id,
        api_hash=api_hash,
        proxy=proxy,
        workdir=workdir,
        session_string=session_string,
        in_memory=in_memory,
        key=key,
        **kwargs,
    )
    _CLIENT_INSTANCES[key] = client
    return client


async def close_client_by_name(name: str, workdir: Union[str, pathlib.Path] = "."):
    """
    Forcefully close a client instance by its name and release resources.
    """
    key = str(pathlib.Path(workdir).joinpath(name).resolve())

    # Check if we have a lock for this client
    lock = _CLIENT_ASYNC_LOCKS.get(key)
    if lock:
        # Acquire the lock to ensure we have exclusive access
        # Note: This might block if a task is running.
        # If we want to forceful kill, we might skip this, but that's dangerous.
        # For deletion, waiting a moment is acceptable.
        try:
            # Try to acquire with timeout to avoid deadlocks if something is stuck
            await asyncio.wait_for(lock.acquire(), timeout=5.0)
            try:
                # Reset references to 0 to ensure proper cleanup
                _CLIENT_REFS[key] = 0
            finally:
                # Even if we manipulated refs, release the lock we just acquired
                lock.release()
        except asyncio.TimeoutError:
            logger.warning(
                f"Timeout waiting for lock on client {name}, proceeding with forceful cleanup"
            )
            _CLIENT_REFS[key] = 0

    client = _CLIENT_INSTANCES.get(key)
    if client:
        try:
            if client.is_connected:
                await client.stop()
        except Exception as e:
            logger.warning(f"Error stopping client {name}: {e}")
        finally:
            _CLIENT_INSTANCES.pop(key, None)

    # Clean up locks
    if key in _CLIENT_ASYNC_LOCKS:
        _CLIENT_ASYNC_LOCKS.pop(key, None)
    if key in _CLIENT_REFS:
        _CLIENT_REFS.pop(key, None)


def get_now():
    return datetime.now(tz=timezone(timedelta(hours=8)))


def make_dirs(path: pathlib.Path, exist_ok=True):
    path = pathlib.Path(path)
    if not path.is_dir():
        os.makedirs(path, exist_ok=exist_ok)
    return path


ConfigT = TypeVar("ConfigT", bound=BaseJSONConfig)


class BaseUserWorker(Generic[ConfigT]):
    _workdir = "."
    _tasks_dir = "tasks"
    cfg_cls: Type["ConfigT"] = BaseJSONConfig

    def __init__(
        self,
        task_name: str = None,
        session_dir: str = ".",
        account: str = "my_account",
        proxy=None,
        workdir=None,
        session_string: str = None,
        in_memory: bool = False,
        api_id: int = None,
        api_hash: str = None,
        no_updates: Optional[bool] = None,
        *,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        self.task_name = task_name or "my_task"
        self._session_dir = pathlib.Path(session_dir)
        self._account = account
        self._proxy = proxy
        if workdir:
            self._workdir = pathlib.Path(workdir)
        client_kwargs = {
            "workdir": self._session_dir,
            "session_string": session_string,
            "in_memory": in_memory,
            "api_id": api_id,
            "api_hash": api_hash,
            "loop": loop,
        }
        if no_updates is not None:
            client_kwargs["no_updates"] = no_updates

        self.app = get_client(
            account,
            proxy,
            **client_kwargs,
        )
        self.loop = self.app.loop
        self.user: Optional[User] = None
        self._config = None
        self.context = self.ensure_ctx()

    def ensure_ctx(self):
        return {}

    def app_run(self, coroutine=None):
        if coroutine is not None:
            run = self.loop.run_until_complete
            run(coroutine)
        else:
            self.app.run()

    @property
    def workdir(self) -> pathlib.Path:
        workdir = self._workdir
        make_dirs(workdir)
        return pathlib.Path(workdir)

    @property
    def tasks_dir(self):
        tasks_dir = self.workdir / self._tasks_dir
        make_dirs(tasks_dir)
        return pathlib.Path(tasks_dir)

    @property
    def task_dir(self):
        task_dir = self.tasks_dir / self.task_name
        make_dirs(task_dir)
        return task_dir

    def get_user_dir(self, user: User):
        user_dir = self.workdir / "users" / str(user.id)
        make_dirs(user_dir)
        return user_dir

    @property
    def config_file(self):
        return self.task_dir.joinpath("config.json")

    @property
    def config(self) -> ConfigT:
        return self._config or self.load_config()

    @config.setter
    def config(self, value):
        self._config = value

    def log(self, msg, level: str = "INFO", **kwargs):
        msg = f"账户「{self._account}」- 任务「{self.task_name}」: {msg}"
        if level.upper() == "INFO":
            logger.info(msg, **kwargs)
        elif level.upper() == "WARNING":
            logger.warning(msg, **kwargs)
        elif level.upper() == "ERROR":
            logger.error(msg, **kwargs)
        elif level.upper() == "CRITICAL":
            logger.critical(msg, **kwargs)
        else:
            logger.debug(msg, **kwargs)

    def ask_for_config(self):
        raise NotImplementedError

    def write_config(self, config: BaseJSONConfig):
        with open(self.config_file, "w", encoding="utf-8") as fp:
            json.dump(config.to_jsonable(), fp, ensure_ascii=False)

    def reconfig(self):
        config = self.ask_for_config()
        self.write_config(config)
        return config

    def load_config(self, cfg_cls: Type[ConfigT] = None) -> ConfigT:
        cfg_cls = cfg_cls or self.cfg_cls
        if not self.config_file.exists():
            config = self.reconfig()
        else:
            with open(self.config_file, "r", encoding="utf-8") as fp:
                config, from_old = cfg_cls.load(json.load(fp))
                if from_old:
                    self.write_config(config)
        self.config = config
        return config

    def get_task_list(self):
        signs = []
        for d in os.listdir(self.tasks_dir):
            if self.tasks_dir.joinpath(d).is_dir():
                signs.append(d)
        return signs

    def list_(self):
        print_to_user("已配置的任务：")
        for d in self.get_task_list():
            print_to_user(d)

    def set_me(self, user: User):
        self.user = user
        with open(
            self.get_user_dir(user).joinpath("me.json"), "w", encoding="utf-8"
        ) as fp:
            fp.write(str(user))

    async def login(self, num_of_dialogs=20, print_chat=True):
        self.log("开始登录...")
        app = self.app
        async with app:
            me = await app.get_me()
            self.set_me(me)
            latest_chats = []
            try:
                async for dialog in app.get_dialogs(num_of_dialogs):
                    try:
                        chat = getattr(dialog, "chat", None)
                        if chat is None:
                            self.log("get_dialogs 返回空 chat，已跳过", level="WARNING")
                            continue
                        chat_id = getattr(chat, "id", None)
                        if chat_id is None:
                            self.log("get_dialogs 返回 chat.id 为空，已跳过", level="WARNING")
                            continue
                        latest_chats.append(
                            {
                                "id": chat_id,
                                "title": chat.title,
                                "type": chat.type,
                                "username": chat.username,
                                "first_name": chat.first_name,
                                "last_name": chat.last_name,
                            }
                        )
                        if print_chat:
                            print_to_user(readable_chat(chat))
                    except Exception as e:
                        self.log(
                            f"处理 dialog 失败，已跳过: {type(e).__name__}: {e}",
                            level="WARNING",
                        )
                        continue
            except Exception as e:
                self.log(
                    f"get_dialogs 中断，返回已获取结果: {type(e).__name__}: {e}",
                    level="WARNING",
                )

            with open(
                self.get_user_dir(me).joinpath("latest_chats.json"),
                "w",
                encoding="utf-8",
            ) as fp:
                json.dump(
                    latest_chats,
                    fp,
                    indent=4,
                    default=Object.default,
                    ensure_ascii=False,
                )
            await self.app.save_session_string()

    async def logout(self):
        self.log("开始登出...")
        is_authorized = await self.app.connect()
        if not is_authorized:
            await self.app.storage.delete()
            return None
        return await self.app.log_out()

    async def send_message(
        self, chat_id: Union[int, str], text: str, delete_after: int = None, **kwargs
    ):
        """
        发送文本消息
        :param chat_id:
        :param text:
        :param delete_after: 秒, 发送消息后进行删除，``None`` 表示不删除, ``0`` 表示立即删除.
        :param kwargs:
        :return:
        """
        message = await self.app.send_message(chat_id, text, **kwargs)
        self.log(
            f"已发送文本消息到 {chat_id}: {text}"
            + (
                f" (thread_id={kwargs.get('message_thread_id')})"
                if kwargs.get("message_thread_id") is not None
                else ""
            )
        )
        if delete_after is not None:
            self.log(
                f"Message「{text}」 to {chat_id} will be deleted after {delete_after} seconds."
            )
            self.log("Waiting...")
            await asyncio.sleep(delete_after)
            await message.delete()
            self.log(f"Message「{text}」 to {chat_id} deleted!")
        return message

    async def send_dice(
        self,
        chat_id: Union[int, str],
        emoji: str = "🎲",
        delete_after: int = None,
        **kwargs,
    ):
        """
        发送DICE类型消息
        :param chat_id:
        :param emoji: Should be one of "🎲", "🎯", "🏀", "⚽", "🎳", or "🎰".
        :param delete_after:
        :param kwargs:
        :return:
        """
        emoji = emoji.strip()
        if emoji not in DICE_EMOJIS:
            self.log(
                f"Warning, emoji should be one of {', '.join(DICE_EMOJIS)}",
                level="WARNING",
            )
        message = await self.app.send_dice(chat_id, emoji, **kwargs)
        self.log(
            f"已发送骰子到 {chat_id}: {emoji}"
            + (
                f" (thread_id={kwargs.get('message_thread_id')})"
                if kwargs.get("message_thread_id") is not None
                else ""
            )
        )
        if message and delete_after is not None:
            self.log(
                f"Dice「{emoji}」 to {chat_id} will be deleted after {delete_after} seconds."
            )
            self.log("Waiting...")
            await asyncio.sleep(delete_after)
            try:
                await message.delete()
                self.log(f"Dice「{emoji}」 to {chat_id} deleted!")
            except Exception as e:
                self.log(f"删除骰子消息失败: {e}", level="ERROR")
        return message

    async def search_members(
        self, chat_id: Union[int, str], query: str, admin=False, limit=10
    ):
        filter_ = ChatMembersFilter.SEARCH
        if admin:
            filter_ = ChatMembersFilter.ADMINISTRATORS
            query = ""
        async for member in self.app.get_chat_members(
            chat_id, query, limit=limit, filter=filter_
        ):
            yield member

    async def list_members(
        self, chat_id: Union[int, str], query: str = "", admin=False, limit=10
    ):
        async with self.app:
            async for member in self.search_members(chat_id, query, admin, limit):
                print_to_user(
                    User(
                        id=member.user.id,
                        username=member.user.username,
                        first_name=member.user.first_name,
                        last_name=member.user.last_name,
                        is_bot=member.user.is_bot,
                    )
                )

    def export(self):
        with open(self.config_file, "r", encoding="utf-8") as fp:
            data = fp.read()
        return data

    def import_(self, config_str: str):
        with open(self.config_file, "w", encoding="utf-8") as fp:
            fp.write(config_str)

    def ask_one(self):
        raise NotImplementedError

    def ensure_ai_cfg(self):
        cfg_manager = OpenAIConfigManager(self.workdir)
        cfg = cfg_manager.load_config()
        if not cfg:
            cfg = cfg_manager.ask_for_config()
        return cfg

    def get_ai_tools(self):
        return AITools(self.ensure_ai_cfg())


class Waiter:
    def __init__(self):
        self.waiting_ids = set()
        self.waiting_counter = Counter()

    def add(self, elm):
        self.waiting_ids.add(elm)
        self.waiting_counter[elm] += 1

    def discard(self, elm):
        self.waiting_ids.discard(elm)
        self.waiting_counter.pop(elm, None)

    def sub(self, elm):
        self.waiting_counter[elm] -= 1
        if self.waiting_counter[elm] <= 0:
            self.discard(elm)

    def clear(self):
        self.waiting_ids.clear()
        self.waiting_counter.clear()

    def __bool__(self):
        return bool(self.waiting_ids)

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.waiting_counter}>"


class UserSignerWorkerContext(BaseModel):
    """签到工作上下文"""

    class Config:
        arbitrary_types_allowed = True

    waiter: Waiter
    sign_chats: dict  # 签到配置列表, int -> list[SignChatV3]
    chat_messages: dict  # 收到的消息, int -> dict[int, Optional[Message]]
    waiting_message: Optional[Message] = None  # 正在处理的消息


class UserSigner(BaseUserWorker[SignConfigV3]):
    _workdir = ".signer"
    _tasks_dir = "signs"
    cfg_cls = SignConfigV3
    context: UserSignerWorkerContext

    def ensure_ctx(self) -> UserSignerWorkerContext:
        return UserSignerWorkerContext(
            waiter=Waiter(),
            sign_chats=defaultdict(list),
            chat_messages=defaultdict(dict),
            waiting_message=None,
        )

    def _load_chat_cache(self) -> List[dict]:
        try:
            cache_file = self.tasks_dir / self._account / "chats_cache.json"
            if not cache_file.exists():
                return []
            with open(cache_file, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _find_cached_chat(self, chat_id: int, name: Optional[str]) -> Optional[dict]:
        entries = self._load_chat_cache()

        candidate_ids = {chat_id}
        if isinstance(chat_id, int):
            candidate_ids.add(-chat_id)
            try:
                candidate_ids.add(int(f"-100{abs(chat_id)}"))
            except Exception:
                pass

        def _search_entries(cache_entries: List[dict]) -> Optional[dict]:
            for entry in cache_entries:
                try:
                    if entry.get("id") in candidate_ids:
                        return entry
                except Exception:
                    continue
            if name:
                name_key = name.strip().lower().lstrip("@")
                for entry in cache_entries:
                    username = (entry.get("username") or "").strip().lower()
                    title = (entry.get("title") or "").strip().lower()
                    if username and username == name_key:
                        return entry
                    if title and title == name.strip().lower():
                        return entry
            return None

        # 1. Search current account cache
        found = _search_entries(entries)
        if found:
            return found

        # 2. Search all other accounts caches
        try:
            for account_dir in self.tasks_dir.iterdir():
                if not account_dir.is_dir() or account_dir.name == self._account:
                    continue
                other_cache_file = account_dir / "chats_cache.json"
                if other_cache_file.exists():
                    try:
                        with open(other_cache_file, "r", encoding="utf-8") as fp:
                            other_data = json.load(fp)
                        if isinstance(other_data, list):
                            found = _search_entries(other_data)
                            if found:
                                return found
                    except Exception:
                        continue
        except Exception:
            pass

        return None

    @property
    def sign_record_file(self):
        sign_record_dir = self.task_dir / str(self.user.id)
        make_dirs(sign_record_dir)
        return sign_record_dir / "sign_record.json"

    def _ask_actions(
        self, input_: UserInput, available_actions: List[SupportAction] = None
    ) -> List[ActionT]:
        print_to_user(f"{input_.index_str}开始配置<动作>，请按照实际签到顺序配置。")
        available_actions = available_actions or list(SupportAction)
        actions = []
        while True:
            try:
                local_input_ = UserInput()
                print_to_user(f"第{len(actions) + 1}个动作: ")
                for action in available_actions:
                    print_to_user(f"  {action.value}: {action.desc}")
                print_to_user()
                action_str = local_input_("输入对应的数字选择动作: ").strip()
                action = SupportAction(int(action_str))
                if action not in available_actions:
                    raise ValueError(f"不支持的动作: {action}")
                if len(actions) == 0 and action not in [
                    SupportAction.SEND_TEXT,
                    SupportAction.SEND_DICE,
                ]:
                    raise ValueError(
                        f"第一个动作必须为「{SupportAction.SEND_TEXT.desc}」或「{SupportAction.SEND_DICE.desc}」"
                    )
                if action == SupportAction.SEND_TEXT:
                    text = local_input_("输入要发送的文本: ")
                    actions.append(SendTextAction(text=text))
                elif action == SupportAction.SEND_DICE:
                    dice = local_input_("输入要发送的骰子（如 🎲, 🎯）: ")
                    actions.append(SendDiceAction(dice=dice))
                elif action == SupportAction.CLICK_KEYBOARD_BY_TEXT:
                    text_of_btn_to_click = local_input_("键盘中需要点击的按钮文本: ")
                    actions.append(ClickKeyboardByTextAction(text=text_of_btn_to_click))
                elif action == SupportAction.CHOOSE_OPTION_BY_IMAGE:
                    print_to_user(
                        "图片识别将使用大模型回答，请确保大模型支持图片识别。"
                    )
                    actions.append(ChooseOptionByImageAction())
                elif action == SupportAction.REPLY_BY_CALCULATION_PROBLEM:
                    print_to_user("计算题将使用大模型回答。")
                    actions.append(ReplyByCalculationProblemAction())
                elif action == SupportAction.REPLY_BY_IMAGE_RECOGNITION:
                    print_to_user("AI will recognize text from image and send it automatically.")
                    actions.append(ReplyByImageRecognitionAction())
                elif action == SupportAction.CLICK_BUTTON_BY_CALCULATION_PROBLEM:
                    print_to_user("AI will calculate the answer and click the matching button.")
                    actions.append(ClickButtonByCalculationProblemAction())
                else:
                    raise ValueError(f"不支持的动作: {action}")
                if local_input_("是否继续添加动作？(y/N)：").strip().lower() != "y":
                    break
            except (ValueError, ValidationError) as e:
                print_to_user("错误: ")
                print_to_user(e)
        input_.incr()
        return actions

    def ask_one(self) -> SignChatV3:
        input_ = UserInput(numbering_lang="chinese_simple")
        chat_id = int(input_("Chat ID（登录时最近对话输出中的ID）: "))
        name = input_("Chat名称（可选）: ")
        actions = self._ask_actions(input_)
        delete_after = (
            input_(
                "等待N秒后删除消息（发送消息后等待进行删除, '0'表示立即删除, 不需要删除直接回车）, N: "
            )
            or None
        )
        if delete_after:
            delete_after = int(delete_after)
        cfgs = {
            "chat_id": chat_id,
            "name": name,
            "delete_after": delete_after,
            "actions": actions,
        }
        return SignChatV3.parse_obj(cfgs)

    def ask_for_config(self) -> "SignConfigV3":
        chats = []
        i = 1
        print_to_user(f"开始配置任务<{self.task_name}>\n")
        while True:
            print_to_user(f"第{i}个任务: ")
            try:
                chat = self.ask_one()
                print_to_user(chat)
                print_to_user(f"第{i}个任务配置成功\n")
                chats.append(chat)
            except Exception as e:
                print_to_user(e)
                print_to_user("配置失败")
                i -= 1
            continue_ = input("继续配置任务？(y/N)：")
            if continue_.strip().lower() != "y":
                break
            i += 1
        sign_at_prompt = "签到时间（time或crontab表达式，如'06:00:00'或'0 6 * * *'）: "
        sign_at_str = input(sign_at_prompt) or "06:00:00"
        while not (sign_at := self._validate_sign_at(sign_at_str)):
            print_to_user("请输入正确的时间格式")
            sign_at_str = input(sign_at_prompt) or "06:00:00"

        random_seconds_str = input("签到时间误差随机秒数（默认为0）: ") or "0"
        random_seconds = int(float(random_seconds_str))
        config = SignConfigV3.parse_obj(
            {
                "chats": chats,
                "sign_at": sign_at,
                "random_seconds": random_seconds,
            }
        )
        if config.requires_ai:
            print_to_user(OPENAI_USE_PROMPT)
        return config

    @classmethod
    def _validate_sign_at(cls, sign_at_str: str) -> Optional[str]:
        sign_at_str = sign_at_str.replace("：", ":").strip()

        try:
            sign_at = dt_time.fromisoformat(sign_at_str)
            crontab_expr = cls._time_to_crontab(sign_at)
        except ValueError:
            try:
                croniter(sign_at_str)
                crontab_expr = sign_at_str
            except CroniterBadCronError:
                return None
        return crontab_expr

    @staticmethod
    def _time_to_crontab(sign_at: time) -> str:
        return f"{sign_at.minute} {sign_at.hour} * * *"

    def load_sign_record(self):
        sign_record = {}
        if not self.sign_record_file.is_file():
            with open(self.sign_record_file, "w", encoding="utf-8") as fp:
                json.dump(sign_record, fp)
        else:
            with open(self.sign_record_file, "r", encoding="utf-8") as fp:
                sign_record = json.load(fp)
        return sign_record

    async def sign_a_chat(
        self,
        chat: SignChatV3,
    ):
        try:
            # 预热会话，确保 peer/access_hash 可用
            await self.app.get_chat(chat.chat_id)
        except Exception as e:
            # 兼容历史配置：部分会话可能保存了缺失负号的 chat_id
            try:
                from pyrogram.errors import ChannelInvalid, PeerIdInvalid
                is_peer_invalid = isinstance(e, (PeerIdInvalid, ChannelInvalid))
            except Exception:
                is_peer_invalid = any(x in str(e) for x in ("PEER_ID_INVALID", "CHANNEL_INVALID"))

            if is_peer_invalid and isinstance(chat.chat_id, int):
                last_error = e
                # First attempt: If it's a positive ID, try get_users (which may still fail if it's completely unknown)
                if chat.chat_id > 0:
                    try:
                        await self.app.get_users(chat.chat_id)
                        self.log(
                            f"预热会话使用 get_users 成功: {chat.chat_id}",
                            level="WARNING",
                        )
                        # The user/bot is now in the storage, we can simply return
                        return
                    except Exception as e2:
                        last_error = e2

                # Second attempt: Try fetching by cached username BEFORE blind negative guessing
                cached = self._find_cached_chat(chat.chat_id, chat.name)
                if cached:
                    username = cached.get("username")
                    cached_id = cached.get("id")
                    if username:
                        try:
                            resolved = await self.app.get_chat(username)
                            self.log(
                                f"预热会话使用缓存用户名成功: {chat.chat_id} -> @{username}",
                                level="WARNING",
                            )
                            chat.chat_id = resolved.id
                            last_error = None
                            return
                        except Exception as e2:
                            last_error = e2
                    if last_error is not None and cached_id and cached_id != chat.chat_id:
                        try:
                            await self.app.get_chat(cached_id)
                            self.log(
                                f"预热会话使用缓存 chat_id 成功: {chat.chat_id} -> {cached_id}",
                                level="WARNING",
                            )
                            chat.chat_id = cached_id
                            last_error = None
                            return
                        except Exception as e2:
                            last_error = e2

                # Third attempt: Try guessing negative variants if nothing worked
                candidates = []
                if chat.chat_id > 0:
                    candidates.append(-chat.chat_id)
                    candidates.append(int(f"-100{chat.chat_id}"))
                elif chat.chat_id < 0:
                    if not str(chat.chat_id).startswith("-100"):
                        candidates.append(int(f"-100{abs(chat.chat_id)}"))

                for candidate in candidates:
                    if candidate == chat.chat_id:
                        continue
                    try:
                        await self.app.get_chat(candidate)
                        self.log(
                            f"预热会话使用回退 chat_id 成功: {chat.chat_id} -> {candidate}",
                            level="WARNING",
                        )
                        chat.chat_id = candidate
                        last_error = None
                        break
                    except Exception as e2:
                        last_error = e2
                        continue

                if last_error is not None:
                    self.log(
                        f"预热会话失败: chat_id={chat.chat_id}, error={type(last_error).__name__}: {last_error}",
                        level="ERROR",
                    )
                    raise RuntimeError(
                        f"Failed to preheat chat_id {chat.chat_id}: {last_error}"
                    ) from last_error
            else:
                self.log(
                    f"预热会话失败: chat_id={chat.chat_id}, error={type(e).__name__}: {e}",
                    level="ERROR",
                )
                raise RuntimeError(
                    f"Failed to preheat chat_id {chat.chat_id}: {e}"
                ) from e
        self.log(f"开始执行: \n{chat}")
        total_actions = len(chat.actions)
        if total_actions == 0:
            raise RuntimeError("任务没有配置任何执行动作")
        for index, action in enumerate(chat.actions, start=1):
            self.log(f"开始第 {index}/{total_actions} 步动作: {action}")
            result = await self.wait_for(chat, action)
            if result is False:
                raise RuntimeError(f"第 {index}/{total_actions} 步动作执行失败: {action}")
            self.log(f"完成第 {index}/{total_actions} 步动作: {action}")
            self.context.waiting_message = None
            await asyncio.sleep(chat.action_interval)

    async def run(
        self, num_of_dialogs=20, only_once: bool = False, force_rerun: bool = False
    ):
        if self.app.in_memory or self.app.session_string:
            return await self.in_memory_run(
                num_of_dialogs, only_once=only_once, force_rerun=force_rerun
            )
        return await self.normal_run(
            num_of_dialogs, only_once=only_once, force_rerun=force_rerun
        )

    async def in_memory_run(
        self, num_of_dialogs=20, only_once: bool = False, force_rerun: bool = False
    ):
        started_here = False
        if not getattr(self.app, "is_connected", False):
            await self.app.start()
            started_here = True
        try:
            await self.normal_run(
                num_of_dialogs, only_once=only_once, force_rerun=force_rerun
            )
        finally:
            if started_here:
                await self.app.stop()

    async def normal_run(
        self, num_of_dialogs=20, only_once: bool = False, force_rerun: bool = False
    ):
        if self.user is None:
            await self.login(num_of_dialogs, print_chat=True)

        config = self.load_config(self.cfg_cls)
        if config.requires_ai:
            self.ensure_ai_cfg()

        sign_record = self.load_sign_record()
        chat_ids = [c.chat_id for c in config.chats]
        need_update_handlers = bool(getattr(config, "requires_updates", True))
        message_handler_ref = None
        edited_handler_ref = None

        async def sign_once():
            success_count = 0
            for chat in config.chats:
                self.context.sign_chats[chat.chat_id].append(chat)
                try:
                    await self.sign_a_chat(chat)
                    success_count += 1
                except errors.RPCError as _e:
                    self.log(f"签到失败: {_e} \nchat: \n{chat}")
                    logger.warning(_e, exc_info=True)
                    continue

                self.context.chat_messages[chat.chat_id].clear()
                await asyncio.sleep(config.sign_interval)

            if success_count == 0 and len(config.chats) > 0:
                raise RuntimeError("所有会话均执行失败（详细请看运行日志）")

            sign_record[str(now.date())] = now.isoformat()
            with open(self.sign_record_file, "w", encoding="utf-8") as fp:
                json.dump(sign_record, fp)

        def need_sign(last_date_str):
            if force_rerun:
                return True
            if last_date_str not in sign_record:
                return True
            _last_sign_at = datetime.fromisoformat(sign_record[last_date_str])
            self.log(f"上次执行时间: {_last_sign_at}")
            _cron_it = croniter(self._validate_sign_at(config.sign_at), _last_sign_at)
            _next_run: datetime = _cron_it.next(datetime)
            if _next_run > now:
                self.log("当前未到下次执行时间，无需执行")
                return False
            return True

        while True:
            if need_update_handlers and message_handler_ref is None:
                self.log(f"adding message handlers for chats: {chat_ids}")
                message_handler_ref = self.app.add_handler(
                    MessageHandler(self.on_message, filters.chat(chat_ids))
                )
                edited_handler_ref = self.app.add_handler(
                    EditedMessageHandler(self.on_edited_message, filters.chat(chat_ids))
                )
            try:
                started_here = False
                if not getattr(self.app, "is_connected", False):
                    await self.app.start()
                    started_here = True
                try:
                    now = get_now()
                    self.log(f"当前时间: {now}")
                    now_date_str = str(now.date())
                    self.context = self.ensure_ctx()
                    if need_sign(now_date_str):
                        if only_once and config.random_seconds > 0:
                            delay = random.randint(0, int(config.random_seconds))
                            if delay > 0:
                                self.log(f"单次执行随机延迟: {delay} 秒")
                                await asyncio.sleep(delay)
                        await sign_once()
                finally:
                    if started_here:
                        await self.app.stop()

            except (OSError, errors.Unauthorized) as e:
                logger.exception(e)
                await asyncio.sleep(30)
                continue

            if only_once:
                break
            cron_it = croniter(self._validate_sign_at(config.sign_at), now)
            next_run: datetime = cron_it.next(datetime) + timedelta(
                seconds=random.randint(0, int(config.random_seconds))
            )
            self.log(f"下次运行时间: {next_run}")
            await asyncio.sleep((next_run - now).total_seconds())


        if message_handler_ref:
            try:
                self.app.remove_handler(*message_handler_ref)
            except Exception:
                pass
        if edited_handler_ref:
            try:
                self.app.remove_handler(*edited_handler_ref)
            except Exception:
                pass

    async def run_once(self, num_of_dialogs):
        return await self.run(num_of_dialogs, only_once=True, force_rerun=True)

    async def send_text(
        self, chat_id: int, text: str, delete_after: int = None, **kwargs
    ):
        if self.user is None:
            await self.login(print_chat=False)
        async with self.app:
            await self.send_message(chat_id, text, delete_after, **kwargs)

    async def send_dice_cli(
        self,
        chat_id: Union[str, int],
        emoji: str = "🎲",
        delete_after: int = None,
        **kwargs,
    ):
        if self.user is None:
            await self.login(print_chat=False)
        async with self.app:
            await self.send_dice(chat_id, emoji, delete_after, **kwargs)

    async def _on_message(self, client: Client, message: Message):
        chats = self.context.sign_chats.get(message.chat.id)
        if not chats:
            self.log("忽略意料之外的聊天", level="WARNING")
            return
        message_thread_id = getattr(message, "message_thread_id", None) or getattr(
            message, "reply_to_top_message_id", None
        )
        topic_matched = False
        for chat in chats:
            if chat.message_thread_id is None or chat.message_thread_id == message_thread_id:
                topic_matched = True
                break
        if not topic_matched:
            self.log(
                f"忽略非目标话题消息: chat_id={message.chat.id}, thread_id={message_thread_id}",
                level="WARNING",
            )
            return
        self.context.chat_messages[message.chat.id][message.id] = message

    async def on_message(self, client: Client, message: Message):
        self.log(
            f"收到来自「{message.from_user.username or message.from_user.id}」的消息: {readable_message(message)}"
        )
        await self._on_message(client, message)

    async def on_edited_message(self, client, message: Message):
        self.log(
            f"收到来自「{message.from_user.username or message.from_user.id}」对消息的更新，消息: {readable_message(message)}"
        )
        # 避免更新正在处理的消息，等待处理完成
        while (
            self.context.waiting_message
            and self.context.waiting_message.id == message.id
        ):
            await asyncio.sleep(0.3)
        await self._on_message(client, message)

    def _clean_text_for_match(self, text: str) -> str:
        if not text:
            return ""
        # Remove emojis, variation selectors, and zero-width characters before matching.
        text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
        text = re.sub(r'[\u2600-\u27bf]', '', text)
        text = re.sub(r'[\u2B50]', '', text)  # ⭐
        text = re.sub(r'[\ufe00-\ufe0f\u200c\u200d\u20e3]', '', text)
        # Remove all whitespace and zero width joiners to make fuzzy match extremely forgiving
        text = re.sub(r'[\s\u200b\u200e\u200f\u202a-\u202e]', '', text)
        # Remove all common punctuation
        text = re.sub(r'[!"#$%&\'()*+,-./:;<=>?@\[\]^_`{|}~，。！？；：“”‘’（）【】《》]', '', text)
        return text.strip().lower()

    async def _click_keyboard_by_text(
        self,
        action: ClickKeyboardByTextAction,
        message: Message,
        *,
        message_thread_id: Optional[int] = None,
    ):
        target_text = self._clean_text_for_match(action.text)
        if not target_text:
            self.log("Click button action has empty target text after cleaning", level="WARNING")
            return False

        if reply_markup := message.reply_markup:
            if isinstance(reply_markup, InlineKeyboardMarkup):
                flat_buttons = (b for row in reply_markup.inline_keyboard for b in row)
                for btn in flat_buttons:
                    if not btn.text:
                        continue
                    btn_text_clean = self._clean_text_for_match(btn.text)
                    if target_text in btn_text_clean:
                        self.log(f"成功匹配到并点击按钮: [{btn.text}] (匹配词: {action.text})")
                        await self.request_callback_answer(
                            self.app,
                            message.chat.id,
                            message.id,
                            btn.callback_data,
                        )
                        return True
                self.log(
                    f"Target button '{action.text}' not found in inline keyboard.",
                    level="WARNING",
                )
            elif isinstance(reply_markup, ReplyKeyboardMarkup):
                for row in reply_markup.keyboard:
                    for btn in row:
                        btn_text = btn if isinstance(btn, str) else getattr(btn, "text", "")
                        if not btn_text:
                            continue
                        btn_text_clean = self._clean_text_for_match(btn_text)
                        if target_text in btn_text_clean:
                            self.log(f"成功匹配并发送回复键盘文本: [{btn_text}] (匹配词: {action.text})")
                            kwargs = {}
                            if message_thread_id is not None:
                                kwargs["message_thread_id"] = message_thread_id
                            await self.send_message(message.chat.id, btn_text, **kwargs)
                            return True
                self.log(
                    f"Target button '{action.text}' not found in reply keyboard.",
                    level="WARNING",
                )
        return False

    async def _reply_by_calculation_problem(
        self, action: ReplyByCalculationProblemAction, message
    ):
        if message.text:
            self.log("检测到文本回复，尝试调用大模型进行计算题回答")
            self.log(f"问题: \n{message.text}")
            answer = await self.get_ai_tools().calculate_problem(message.text)
            answer = (answer or "").strip()
            self.log(f"回答为: {answer}")
            if not answer:
                self.log("AI 未返回有效答案", level="WARNING")
                return False
            await self.send_message(message.chat.id, answer)
            return True
        return False

    async def _reply_by_image_recognition(
        self, action: ReplyByImageRecognitionAction, message
    ):
        if not message.photo:
            return False
        self.log("检测到图片，尝试识别并发送文本")
        image_buffer: BinaryIO = await self.app.download_media(
            message.photo.file_id, in_memory=True
        )
        image_buffer.seek(0)
        image_bytes = image_buffer.read()
        text = await self.get_ai_tools().extract_text_by_image(image_bytes)
        text = (text or "").strip()
        if not text:
            self.log("AI 未识别到可发送文本", level="WARNING")
            return False
        self.log(f"识别结果: {text}")
        await self.send_message(message.chat.id, text)
        return True

    async def _click_button_by_calculation_problem(
        self, action: ClickButtonByCalculationProblemAction, message
    ):
        if not message.text:
            return False
        self.log("检测到计算题，尝试计算并点击按钮")
        answer = await self.get_ai_tools().calculate_problem(message.text)
        answer = (answer or "").strip()
        if not answer:
            self.log("AI 未返回可用于点击的答案", level="WARNING")
            return False
        self.log(f"计算答案: {answer}")
        proxy_action = ClickKeyboardByTextAction(text=answer)
        return await self._click_keyboard_by_text(proxy_action, message)

    async def _choose_option_by_image(self, action: ChooseOptionByImageAction, message):
        if reply_markup := message.reply_markup:
            if isinstance(reply_markup, InlineKeyboardMarkup) and message.photo:
                flat_buttons = [b for row in reply_markup.inline_keyboard for b in row]
                clickable_buttons = [btn for btn in flat_buttons if btn.text]
                self.log("检测到图片按钮验证，调用 AI 识别并按顺序点击选项")
                image_buffer: BinaryIO = await self.app.download_media(
                    message.photo.file_id, in_memory=True
                )
                image_buffer.seek(0)
                image_bytes = image_buffer.read()
                options = [btn.text for btn in clickable_buttons]
                if not options:
                    self.log("未找到可供点击的按钮", level="WARNING")
                    return False
                question_text = (message.caption or message.text or "").strip()
                if not question_text:
                    question_text = "选择正确的选项"
                result_indexes = await self.get_ai_tools().choose_options_by_image(
                    image_bytes,
                    question_text,
                    list(enumerate(options, start=1)),
                )
                if not result_indexes:
                    self.log("AI 未返回可点击选项", level="WARNING")
                    return False
                clicked = 0
                for result_index in result_indexes:
                    if result_index == 0:
                        selected_idx = 0
                    elif 1 <= result_index <= len(options):
                        selected_idx = result_index - 1
                    elif 0 <= result_index < len(options):
                        selected_idx = result_index
                    else:
                        self.log(f"AI 返回了非法选项序号: {result_index}", level="WARNING")
                        return False
                    result = options[selected_idx]
                    self.log(f"AI 选择并点击选项: {result}")
                    target_btn = clickable_buttons[selected_idx]
                    if not target_btn:
                        self.log("未找到匹配的按钮", level="WARNING")
                        return False
                    await self.request_callback_answer(
                        self.app,
                        message.chat.id,
                        message.id,
                        target_btn.callback_data,
                    )
                    clicked += 1
                    await asyncio.sleep(0.3)
                return clicked > 0
        return False

    async def wait_for(self, chat: SignChatV3, action: ActionT, timeout=15):
        kwargs = {}
        if chat.message_thread_id is not None:
            kwargs["message_thread_id"] = chat.message_thread_id
        if isinstance(action, SendTextAction):
            return await self.send_message(chat.chat_id, action.text, chat.delete_after, **kwargs)
        elif isinstance(action, SendDiceAction):
            return await self.send_dice(chat.chat_id, action.dice, chat.delete_after, **kwargs)
        self.context.waiter.add(chat.chat_id)
        start = time.perf_counter()
        last_message = None
        try:
            if isinstance(action, ClickKeyboardByTextAction):
                self.log("先从最近消息中查找可点击按钮")
                try:
                    async for message in self.app.get_chat_history(chat.chat_id, limit=8):
                        if chat.message_thread_id is not None:
                            msg_thread_id = getattr(message, "message_thread_id", None) or getattr(
                                message, "reply_to_top_message_id", None
                            )
                            if msg_thread_id != chat.message_thread_id:
                                continue
                        ok = await self._click_keyboard_by_text(
                            action,
                            message,
                            message_thread_id=chat.message_thread_id,
                        )
                        if ok:
                            return True
                except Exception as e:
                    self.log(f"最近消息按钮查找失败: {e}", level="WARNING")
                self.log(
                    f"未在最近消息中匹配到按钮，尝试直接发送按钮文本: {action.text}",
                    level="WARNING",
                )
                before_message_ids = set(
                    self.context.chat_messages.get(chat.chat_id, {}).keys()
                )
                await self.send_message(
                    chat.chat_id,
                    action.text,
                    **kwargs,
                )
                direct_send_wait_until = time.perf_counter() + min(6, timeout)
                while time.perf_counter() < direct_send_wait_until:
                    await asyncio.sleep(0.3)
                    messages_dict = self.context.chat_messages.get(chat.chat_id)
                    if not messages_dict:
                        continue
                    for message_id, message in messages_dict.items():
                        if message_id in before_message_ids or message is None:
                            continue
                        self.log("直接发送按钮文本后收到新消息，继续执行后续动作")
                        return True
                self.log("直接发送按钮文本后未收到响应，判定该动作失败", level="WARNING")
                return False

            while time.perf_counter() - start < timeout:
                await asyncio.sleep(0.3)
                messages_dict = self.context.chat_messages.get(chat.chat_id)
                if not messages_dict:
                    continue
                messages = list(messages_dict.values())
                # 暂无新消息
                if messages[-1] == last_message:
                    continue
                last_message = messages[-1]
                for message in messages:
                    if message is None:
                        continue
                    self.context.waiting_message = message
                    ok = False
                    if isinstance(action, ClickKeyboardByTextAction):
                        ok = await self._click_keyboard_by_text(
                            action,
                            message,
                            message_thread_id=chat.message_thread_id,
                        )
                    elif isinstance(action, ReplyByCalculationProblemAction):
                        ok = await self._reply_by_calculation_problem(action, message)
                    elif isinstance(action, ChooseOptionByImageAction):
                        ok = await self._choose_option_by_image(action, message)
                    elif isinstance(action, ReplyByImageRecognitionAction):
                        ok = await self._reply_by_image_recognition(action, message)
                    elif isinstance(action, ClickButtonByCalculationProblemAction):
                        ok = await self._click_button_by_calculation_problem(action, message)
                    if ok:
                        # 将消息ID对应value置为None，保证收到消息的编辑时消息所处的顺序
                        self.context.chat_messages[chat.chat_id][message.id] = None
                        return None
                    self.log(f"忽略消息: {readable_message(message)}")
            # Fallback: try recent history in case message handlers missed the reply.
            if isinstance(
                action,
                (
                    ClickKeyboardByTextAction,
                    ReplyByCalculationProblemAction,
                    ChooseOptionByImageAction,
                    ReplyByImageRecognitionAction,
                    ClickButtonByCalculationProblemAction,
                ),
            ):
                try:
                    self.log("等待超时，尝试从历史消息中查找按钮", level="WARNING")
                    async for message in self.app.get_chat_history(chat.chat_id, limit=5):
                        if isinstance(action, ClickKeyboardByTextAction):
                            ok = await self._click_keyboard_by_text(
                                action,
                                message,
                                message_thread_id=chat.message_thread_id,
                            )
                        elif isinstance(action, ReplyByCalculationProblemAction):
                            ok = await self._reply_by_calculation_problem(action, message)
                        elif isinstance(action, ChooseOptionByImageAction):
                            ok = await self._choose_option_by_image(action, message)
                        elif isinstance(action, ReplyByImageRecognitionAction):
                            ok = await self._reply_by_image_recognition(action, message)
                        else:
                            ok = await self._click_button_by_calculation_problem(
                                action, message
                            )
                        if ok:
                            return None
                except Exception as e:
                    self.log(f"历史消息回退失败: {e}", level="WARNING")

            self.log(f"等待超时: \nchat: \n{chat} \naction: {action}", level="WARNING")
            raise RuntimeError(
                f"Action did not complete within {timeout}s. chat_id={chat.chat_id}, action={action}"
            )
        finally:
            self.context.waiter.discard(chat.chat_id)
            self.context.waiting_message = None

    async def request_callback_answer(
        self,
        client: Client,
        chat_id: Union[int, str],
        message_id: int,
        callback_data: Union[str, bytes],
        **kwargs,
    ):
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                await client.request_callback_answer(
                    chat_id, message_id, callback_data=callback_data, **kwargs
                )
                self.log("点击完成")
                return
            except errors.FloodWait as e:
                wait_seconds = max(int(getattr(e, "value", 1) or 1), 1)
                self.log(
                    f"触发 FloodWait，{wait_seconds}s 后重试 ({attempt}/{max_retries})",
                    level="WARNING",
                )
                if attempt >= max_retries:
                    self.log(e, level="ERROR")
                    return
                await asyncio.sleep(wait_seconds)
            except TimeoutError as e:
                backoff = min(2**attempt, 8)
                self.log(
                    f"回调超时，{backoff}s 后重试 ({attempt}/{max_retries})",
                    level="WARNING",
                )
                if attempt >= max_retries:
                    self.log(e, level="ERROR")
                    return
                await asyncio.sleep(backoff)
            except errors.BadRequest as e:
                self.log(e, level="ERROR")
                return

    async def schedule_messages(
        self,
        chat_id: Union[int, str],
        text: str,
        crontab: str = None,
        next_times: int = 1,
        random_seconds: int = 0,
    ):
        now = get_now()
        it = croniter(crontab, start_time=now)
        if self.user is None:
            await self.login(print_chat=False)
        results = []
        async with self.app:
            for n in range(next_times):
                next_dt: datetime = it.next(ret_type=datetime) + timedelta(
                    seconds=random.randint(0, random_seconds)
                )
                results.append({"at": next_dt.isoformat(), "text": text})
                await self.app.send_message(
                    chat_id,
                    text,
                    schedule_date=next_dt,
                )
                await asyncio.sleep(0.1)
                print_to_user(f"已配置次数：{n + 1}")
        self.log(f"已配置定时发送消息，次数{next_times}")
        return results

    async def get_schedule_messages(self, chat_id):
        if self.user is None:
            await self.login(print_chat=False)
        async with self.app:
            messages = await self.app.get_scheduled_messages(chat_id)
            for message in messages:
                print_to_user(f"{message.date}: {message.text}")


class UserMonitor(BaseUserWorker[MonitorConfig]):
    _workdir = ".monitor"
    _tasks_dir = "monitors"
    cfg_cls = MonitorConfig
    config: MonitorConfig

    def ask_one(self):
        input_ = UserInput()
        chat_id = (input_("Chat ID（登录时最近对话输出中的ID）: ")).strip()
        if not chat_id.startswith("@"):
            chat_id = int(chat_id)
        rules = ["exact", "contains", "regex", "all"]
        while rule := (input_(f"匹配规则({', '.join(rules)}): ") or "exact"):
            if rule in rules:
                break
            print_to_user("不存在的规则, 请重新输入!")
        rule_value = None
        if rule != "all":
            while not (rule_value := input_("规则值（不可为空）: ")):
                print_to_user("不可为空！")
                continue
        from_user_ids = (
            input_(
                "只匹配来自特定用户ID的消息（多个用逗号隔开, 匹配所有用户直接回车）: "
            )
            or None
        )
        always_ignore_me = input_("总是忽略自己发送的消息（y/N）: ").lower() == "y"
        if from_user_ids:
            from_user_ids = [
                i if i.startswith("@") else int(i) for i in from_user_ids.split(",")
            ]
        default_send_text = input_("默认发送文本（不需要则回车）: ") or None
        ai_reply = False
        ai_prompt = None
        use_ai_reply = input_("是否使用AI进行回复(y/N): ") or "n"
        if use_ai_reply.lower() == "y":
            ai_reply = True
            while not (ai_prompt := input_("输入你的提示词（作为`system prompt`）: ")):
                print_to_user("不可为空！")
                continue
            print_to_user(OPENAI_USE_PROMPT)

        send_text_search_regex = None
        if not ai_reply:
            send_text_search_regex = (
                input_("从消息中提取发送文本的正则表达式（不需要则直接回车）: ") or None
            )

        if default_send_text or ai_reply or send_text_search_regex:
            delete_after = (
                input_(
                    "发送消息后等待N秒进行删除（'0'表示立即删除, 不需要删除直接回车）， N: "
                )
                or None
            )
            if delete_after:
                delete_after = int(delete_after)
            forward_to_chat_id = (
                input_("转发消息到该聊天ID，默认为消息来源：")
            ).strip()
            if forward_to_chat_id and not forward_to_chat_id.startswith("@"):
                forward_to_chat_id = int(forward_to_chat_id)
        else:
            delete_after = None
            forward_to_chat_id = None

        push_via_server_chan = (
            input_("是否通过Server酱推送消息(y/N): ") or "n"
        ).lower() == "y"
        server_chan_send_key = None
        if push_via_server_chan:
            server_chan_send_key = (
                input_(
                    "Server酱的SendKey（不填将从环境变量`SERVER_CHAN_SEND_KEY`读取）: "
                )
                or None
            )

        forward_to_external = (
            input_("是否需要转发到外部（UDP, Http）(y/N): ").lower() == "y"
        )
        external_forwards = None
        if forward_to_external:
            external_forwards = []
            if input_("是否需要转发到UDP(y/N): ").lower() == "y":
                addr = input_("请输入UDP服务器地址和端口（形如`127.0.0.1:1234`）: ")
                host, port = addr.split(":")
                external_forwards.append(
                    {
                        "host": host,
                        "port": int(port),
                    }
                )

            if input_("是否需要转发到Http(y/N): ").lower() == "y":
                url = input_("请输入Http地址（形如`http://127.0.0.1:1234`）: ")
                external_forwards.append(
                    {
                        "url": url,
                    }
                )

        return MatchConfig.parse_obj(
            {
                "chat_id": chat_id,
                "rule": rule,
                "rule_value": rule_value,
                "from_user_ids": from_user_ids,
                "always_ignore_me": always_ignore_me,
                "default_send_text": default_send_text,
                "ai_reply": ai_reply,
                "ai_prompt": ai_prompt,
                "send_text_search_regex": send_text_search_regex,
                "delete_after": delete_after,
                "forward_to_chat_id": forward_to_chat_id,
                "push_via_server_chan": push_via_server_chan,
                "server_chan_send_key": server_chan_send_key,
                "external_forwards": external_forwards,
            }
        )

    def ask_for_config(self) -> "MonitorConfig":
        i = 1
        print_to_user(f"开始配置任务<{self.task_name}>")
        print_to_user(
            "聊天chat id和用户user id均同时支持整数id和字符串username, username必须以@开头，如@neo"
        )
        match_cfgs = []
        while True:
            print_to_user(f"\n配置第{i}个监控项")
            try:
                match_cfgs.append(self.ask_one())
            except Exception as e:
                print_to_user(e)
                print_to_user("配置失败")
                i -= 1
            continue_ = input("继续配置？(y/N)：")
            if continue_.strip().lower() != "y":
                break
            i += 1
        config = MonitorConfig(match_cfgs=match_cfgs)
        if config.requires_ai:
            print_to_user(OPENAI_USE_PROMPT)
        return config

    @classmethod
    async def udp_forward(cls, f: UDPForward, message: Message):
        data = str(message).encode("utf-8")
        loop = asyncio.get_running_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: _UDPProtocol(), remote_addr=(f.host, f.port)
        )
        try:
            transport.sendto(data)
        finally:
            transport.close()

    @classmethod
    async def http_api_callback(cls, f: HttpCallback, message: Message):
        headers = f.headers or {}
        headers.update({"Content-Type": "application/json"})
        content = str(message).encode("utf-8")
        async with httpx.AsyncClient() as client:
            await client.post(
                str(f.url),
                content=content,
                headers=headers,
                timeout=10,
            )

    async def forward_to_external(self, match_cfg: MatchConfig, message: Message):
        if not match_cfg.external_forwards:
            return
        for forward in match_cfg.external_forwards:
            self.log(f"转发消息至{forward}")
            if isinstance(forward, UDPForward):
                asyncio.create_task(
                    self.udp_forward(
                        forward,
                        message,
                    )
                )
            elif isinstance(forward, HttpCallback):
                asyncio.create_task(
                    self.http_api_callback(
                        forward,
                        message,
                    )
                )

    async def on_message(self, client, message: Message):
        for match_cfg in self.config.match_cfgs:
            if not match_cfg.match(message):
                continue
            self.log(f"匹配到监控项：{match_cfg}")
            await self.forward_to_external(match_cfg, message)
            try:
                send_text = await self.get_send_text(match_cfg, message)
                if not send_text:
                    self.log("发送内容为空", level="WARNING")
                else:
                    forward_to_chat_id = match_cfg.forward_to_chat_id or message.chat.id
                    self.log(f"发送文本：{send_text}至{forward_to_chat_id}")
                    await self.send_message(
                        forward_to_chat_id,
                        send_text,
                        delete_after=match_cfg.delete_after,
                    )

                if match_cfg.push_via_server_chan:
                    server_chan_send_key = (
                        match_cfg.server_chan_send_key
                        or os.environ.get("SERVER_CHAN_SEND_KEY")
                    )
                    if not server_chan_send_key:
                        self.log("未配置Server酱的SendKey", level="WARNING")
                    else:
                        await sc_send(
                            server_chan_send_key,
                            f"匹配到监控项：{match_cfg.chat_id}",
                            f"消息内容为:\n\n{message.text}",
                        )
            except IndexError as e:
                logger.exception(e)

    async def get_send_text(self, match_cfg: MatchConfig, message: Message) -> str:
        send_text = match_cfg.get_send_text(message.text)
        if match_cfg.ai_reply and match_cfg.ai_prompt:
            send_text = await self.get_ai_tools().get_reply(
                match_cfg.ai_prompt,
                message.text,
            )
        return send_text

    async def run(self, num_of_dialogs=20):
        if self.user is None:
            await self.login(num_of_dialogs, print_chat=True)

        cfg = self.load_config(self.cfg_cls)
        if cfg.requires_ai:
            self.ensure_ai_cfg()

        self.app.add_handler(
            MessageHandler(self.on_message, filters.text & filters.chat(cfg.chat_ids)),
        )
        async with self.app:
            self.log("开始监控...")
            await idle()


class _UDPProtocol(asyncio.DatagramProtocol):
    """内部使用的UDP协议处理类"""

    def __init__(self):
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        pass  # 不需要处理接收的数据

    def error_received(self, exc):
        print(f"UDP error received: {exc}")
