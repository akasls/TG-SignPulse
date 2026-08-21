import asyncio
import json
import logging
import os
import pathlib
import random
import sqlite3
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from datetime import time as dt_time
from types import SimpleNamespace
from typing import (
    Any,
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
from pydantic import BaseModel, Field, ValidationError

try:
    from pydantic import ConfigDict
except ImportError:  # pragma: no cover - pydantic v1 compatibility
    ConfigDict = None

from tg_signer.config import (
    ActionT,
    BaseJSONConfig,
    ChooseOptionByImageAction,
    ClickButtonByCalculationProblemAction,
    ClickKeyboardByTextAction,
    HttpCallback,
    KeywordNotifyAction,
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
from .async_utils import create_logged_task
from .memory import trim_memory
from .notification.server_chan import sc_send
from .utils import UserInput, atomic_write_json, atomic_write_text, print_to_user

_PYDANTIC_V2 = hasattr(BaseModel, "model_validate")
_PYROGRAM_IMPORT_ERROR: Exception | None = None

try:
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
except Exception as exc:  # pragma: no cover - fallback for unsupported runtimes
    _PYROGRAM_IMPORT_ERROR = exc

    def _raise_pyrogram_import_error() -> None:
        raise RuntimeError(
            "Telegram runtime dependencies are unavailable. "
            "Use Python 3.10-3.13 with a compatible pyrogram/kurigram install."
        ) from _PYROGRAM_IMPORT_ERROR

    class _RPCError(Exception):
        pass

    class _FloodWait(_RPCError):
        def __init__(self, *args, value: int = 0, **kwargs):
            super().__init__(*args)
            self.value = value

    errors = SimpleNamespace(
        RPCError=_RPCError,
        FloodWait=_FloodWait,
        BadRequest=_RPCError,
        Unauthorized=_RPCError,
    )

    class _FilterExpr:
        def __and__(self, other):
            return self

        def __or__(self, other):
            return self

    filters = SimpleNamespace(
        text=_FilterExpr(),
        caption=_FilterExpr(),
        chat=lambda *args, **kwargs: _FilterExpr(),
    )

    raw = SimpleNamespace(
        functions=SimpleNamespace(
            updates=SimpleNamespace(
                GetChannelDifference=type("GetChannelDifference", (), {}),
                GetDifference=type("GetDifference", (), {}),
                GetState=type("GetState", (), {}),
            )
        )
    )

    class ChatMembersFilter:  # type: ignore[no-redef]
        SEARCH = "search"
        ADMINISTRATORS = "administrators"

    class ChatType:  # type: ignore[no-redef]
        BOT = "bot"
        GROUP = "group"
        SUPERGROUP = "supergroup"
        CHANNEL = "channel"

    class MessageHandler:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class EditedMessageHandler(MessageHandler):  # type: ignore[no-redef]
        pass

    async def idle():  # type: ignore[no-redef]
        _raise_pyrogram_import_error()

    class Session:  # type: ignore[no-redef]
        START_TIMEOUT = 5

    class MemoryStorage:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class BaseClient:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            _raise_pyrogram_import_error()

        async def invoke(self, *args, **kwargs):
            _raise_pyrogram_import_error()

    class Chat:  # type: ignore[no-redef]
        pass

    class InlineKeyboardMarkup:  # type: ignore[no-redef]
        inline_keyboard = ()

    class Message:  # type: ignore[no-redef]
        pass

    class Object:  # type: ignore[no-redef]
        @staticmethod
        def default(obj):
            return str(obj)

    class ReplyKeyboardMarkup:  # type: ignore[no-redef]
        keyboard = ()

    class User:  # type: ignore[no-redef]
        pass
else:
    def _raise_pyrogram_import_error() -> None:
        return None

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

# Monkeypatch pyrogram FileStorage.open to skip VACUUM (causes exclusive locks)
# and enable WAL mode + busy_timeout immediately on open
try:
    from pyrogram.storage.file_storage import FileStorage as _PyrogramFileStorage

    _original_file_storage_open = _PyrogramFileStorage.open

    async def _patched_file_storage_open(self):
        path = self.database
        file_exists = path.is_file()

        self.conn = _original_sqlite3_connect(str(path), timeout=30, check_same_thread=False)

        # Enable WAL mode and busy_timeout BEFORE any writes
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA busy_timeout=30000")
        except Exception:
            pass

        if not file_exists:
            self.create()
        else:
            self.update()

        # Skip VACUUM - it requires exclusive lock and blocks other connections.
        # WAL mode handles fragmentation well enough for session files.

    _PyrogramFileStorage.open = _patched_file_storage_open
except Exception:
    pass

# Monkeypatch pyrogram.Client.invoke to add backpressure and retry logic for updates
_original_invoke = BaseClient.invoke
_get_channel_diff_semaphore = asyncio.Semaphore(50)


def _read_positive_float_env(name: str, default: float, minimum: float = 1.0) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(float(raw), minimum)
    except (TypeError, ValueError):
        return default


def _read_positive_int_env(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(int(raw), minimum)
    except (TypeError, ValueError):
        return default


async def _patched_invoke(self, query, *args, **kwargs):
    if isinstance(query, (raw.functions.updates.GetChannelDifference, raw.functions.updates.GetDifference)):
        # If client has updates disabled, drop immediately with empty response without network call
        if getattr(self, "_tg_signpulse_no_updates", False):
            if isinstance(query, raw.functions.updates.GetChannelDifference):
                from pyrogram.raw.types.updates import ChannelDifferenceEmpty
                return ChannelDifferenceEmpty(pts=query.pts, timeout=0, final=True)
            elif isinstance(query, raw.functions.updates.GetDifference):
                from pyrogram.raw.types.updates import DifferenceEmpty
                return DifferenceEmpty(date=getattr(query, "date", 0), seq=getattr(query, "pts", 0))

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


def _is_callback_data_invalid(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "data_invalid" in text or "encrypted data is invalid" in text


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
        if _PYROGRAM_IMPORT_ERROR is not None:
            _raise_pyrogram_import_error()
        key = kwargs.pop("key", None)
        self._tg_signpulse_no_updates = kwargs.get("no_updates")
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
                max_retries = 5
                for attempt in range(max_retries):
                    try:
                        if not self.is_connected:
                            is_authorized = await self.connect()
                            if not is_authorized:
                                raise ConnectionError("Session invalid: unauthorized")

                        try:
                            self.me = await self.get_me()
                        except Exception as e:
                            # Prevent interactive login attempt
                            raise ConnectionError(f"Session invalid: {e}")

                        try:
                            await self.invoke(raw.functions.updates.GetState())
                        except ConnectionError as e:
                            if "already started" not in str(e).lower():
                                raise e
                        try:
                            if not getattr(self, "is_initialized", False):
                                await self.initialize()
                        except ConnectionError as e:
                            if "already initialized" not in str(e).lower():
                                raise e

                        # Enable WAL mode after start (redundant with patch but safe)
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
                        is_locked = "database is locked" in str(e).lower()
                        if is_locked and attempt < max_retries - 1:
                            # Cleanup before retry
                            try:
                                if self.is_connected:
                                    await self.stop()
                            except Exception:
                                pass

                            wait_time = 2 + (attempt * 3)
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

    async def clear_client_cache(self):
        """Clean up transient buffers, media sessions, and unneeded caches to keep memory minimal."""
        try:
            # Clean up media sessions (extra DC connections)
            media_sessions = getattr(self, "media_sessions", None)
            if isinstance(media_sessions, dict):
                for dc_id, session in list(media_sessions.items()):
                    try:
                        if hasattr(session, "stop"):
                            await session.stop()
                    except Exception:
                        pass
                media_sessions.clear()

            # Clean up channel difference tracker if not running keyword monitor
            if getattr(self, "_tg_signpulse_no_updates", True):
                if hasattr(self, "_channel_difference") and isinstance(self._channel_difference, dict):
                    self._channel_difference.clear()
        except Exception as exc:
            logger.debug("clear_client_cache error: %s", exc)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        lock = _CLIENT_ASYNC_LOCKS.get(self.key)
        if lock is None:
            return
        async with lock:
            _CLIENT_REFS[self.key] -= 1
            if _CLIENT_REFS[self.key] <= 0:
                _CLIENT_REFS[self.key] = 0
                try:
                    await self.clear_client_cache()
                except Exception:
                    pass
                try:
                    await self.stop()
                except Exception:
                    pass
                # Remove from cache when no longer in use to prevent memory growth
                _CLIENT_INSTANCES.pop(self.key, None)
                _CLIENT_REFS.pop(self.key, None)
                _CLIENT_ASYNC_LOCKS.pop(self.key, None)
                trim_memory()

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

    # Use separate cache keys for in-memory vs file-mode clients to prevent
    # database lock conflicts when keyword monitor (file mode) and manual
    # task execution (in-memory mode) run on the same account
    base_key = str(pathlib.Path(workdir).joinpath(name).resolve())
    key = f"{base_key}::memory" if (in_memory and session_string) else base_key

    if key in _CLIENT_INSTANCES:
        existing = _CLIENT_INSTANCES[key]
        requested_no_updates = kwargs.get("no_updates")
        existing_no_updates = getattr(existing, "_tg_signpulse_no_updates", None)
        refs = _CLIENT_REFS.get(key, 0)
        if (
            requested_no_updates is not None
            and existing_no_updates is not None
            and requested_no_updates != existing_no_updates
            and refs <= 0
            and not getattr(existing, "is_connected", False)
        ):
            _CLIENT_INSTANCES.pop(key, None)
        else:
            return existing
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
    base_key = str(pathlib.Path(workdir).joinpath(name).resolve())
    keys_to_clean = [base_key, f"{base_key}::memory"]

    for key in keys_to_clean:
        lock = _CLIENT_ASYNC_LOCKS.get(key)
        if lock:
            try:
                await asyncio.wait_for(lock.acquire(), timeout=5.0)
                _CLIENT_REFS[key] = 0
                lock.release()
            except Exception:
                _CLIENT_REFS[key] = 0

        client = _CLIENT_INSTANCES.get(key)
        if client:
            try:
                await client.clear_client_cache()
            except Exception:
                pass
            try:
                if getattr(client, "is_connected", False):
                    await client.stop()
            except Exception as e:
                logger.warning(f"Error stopping client {name}: {e}")
            finally:
                _CLIENT_INSTANCES.pop(key, None)

        if key in _CLIENT_ASYNC_LOCKS:
            _CLIENT_ASYNC_LOCKS.pop(key, None)
        if key in _CLIENT_REFS:
            _CLIENT_REFS.pop(key, None)

    trim_memory()


async def close_all_clients(workdir: Union[str, pathlib.Path] = None):
    """
    Forcefully close all cached clients and release resources.
    """
    keys = list(_CLIENT_INSTANCES.keys())
    for key in keys:
        client = _CLIENT_INSTANCES.get(key)
        if client:
            try:
                await client.clear_client_cache()
            except Exception:
                pass
            try:
                if getattr(client, "is_connected", False):
                    await client.stop()
            except Exception as e:
                logger.warning(f"Error stopping client {key}: {e}")
            finally:
                _CLIENT_INSTANCES.pop(key, None)

    _CLIENT_ASYNC_LOCKS.clear()
    _CLIENT_REFS.clear()
    trim_memory()


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
        self._ai_tools: Optional[AITools] = None
        self._ai_cfg_signature: Optional[tuple[str, str, str]] = None
        self.context = self.ensure_ctx()

    def ensure_ctx(self):
        return {}

    async def _ensure_app_ready(self):
        if _PYROGRAM_IMPORT_ERROR is not None:
            _raise_pyrogram_import_error()

        if getattr(self.app, "is_connected", False):
            if not getattr(self.app, "is_initialized", False):
                try:
                    await self.app.initialize()
                except ConnectionError as exc:
                    if "already initialized" not in str(exc).lower():
                        raise
            return

        is_authorized = await self.app.connect()
        if not is_authorized:
            raise ConnectionError("Session invalid: unauthorized")

        try:
            self.me = await self.app.get_me()
        except Exception as exc:
            raise ConnectionError(f"Session invalid: {exc}") from exc

        try:
            await self.app.invoke(raw.functions.updates.GetState())
        except ConnectionError as exc:
            if "already started" not in str(exc).lower():
                raise

        if not getattr(self.app, "is_initialized", False):
            try:
                await self.app.initialize()
            except ConnectionError as exc:
                if "already initialized" not in str(exc).lower():
                    raise

    async def _call_with_retry(
        self,
        callback,
        *,
        operation: str,
        max_retries: int = 4,
    ):
        for attempt in range(1, max_retries + 1):
            try:
                return await callback()
            except errors.FloodWait as exc:
                wait_seconds = max(int(getattr(exc, "value", 1) or 1), 1)
                self.log(
                    f"{operation} 触发 FloodWait，{wait_seconds}s 后重试 ({attempt}/{max_retries})",
                    level="WARNING",
                )
                if attempt >= max_retries:
                    raise
                await asyncio.sleep(wait_seconds)
            except (TimeoutError, asyncio.TimeoutError, OSError, ConnectionError) as exc:
                backoff = min(2 ** (attempt - 1), 8)
                self.log(
                    f"{operation} 暂时失败，{backoff}s 后重试 ({attempt}/{max_retries}): {type(exc).__name__}: {exc}",
                    level="WARNING",
                )
                if attempt >= max_retries:
                    raise
                try:
                    await self._ensure_app_ready()
                except Exception as reconnect_exc:
                    self.log(
                        f"{operation} 重连失败: {type(reconnect_exc).__name__}: {reconnect_exc}",
                        level="WARNING",
                    )
                await asyncio.sleep(backoff)

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
        atomic_write_json(self.config_file, config.to_jsonable())

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
        try:
            atomic_write_text(
                self.get_user_dir(user).joinpath("me.json"), str(user)
            )
        except Exception:
            pass

    async def ensure_user(self) -> User:
        if self.user is not None:
            return self.user
        if getattr(self.app, "is_connected", False):
            me = await self.app.get_me()
        else:
            async with self.app:
                me = await self.app.get_me()
        self.set_me(me)
        return me

    async def login(self, num_of_dialogs: int = 0, print_chat: bool = False):
        self.log("开始登录...")
        app = self.app
        async with app:
            me = await app.get_me()
            self.set_me(me)
            latest_chats = []
            if num_of_dialogs and num_of_dialogs > 0:
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

                try:
                    atomic_write_json(
                        self.get_user_dir(me).joinpath("latest_chats.json"),
                        latest_chats,
                        indent=4,
                        default=Object.default,
                    )
                except Exception:
                    pass
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
        message = await self._call_with_retry(
            lambda: self.app.send_message(chat_id, text, **kwargs),
            operation=f"发送消息到 {chat_id}",
        )
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
            try:
                await message.delete()
                self.log(f"Message「{text}」 to {chat_id} deleted!")
            except Exception as exc:
                self.log(f"删除消息失败: {exc}", level="WARNING")
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
        message = await self._call_with_retry(
            lambda: self.app.send_dice(chat_id, emoji, **kwargs),
            operation=f"发送骰子到 {chat_id}",
        )
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

    @staticmethod
    def _build_ai_cfg_signature(cfg) -> tuple[str, str, str]:
        return (
            str(cfg.get("api_key") or ""),
            str(cfg.get("base_url") or ""),
            str(cfg.get("model") or ""),
        )

    def get_ai_tools(self):
        cfg = self.ensure_ai_cfg()
        signature = self._build_ai_cfg_signature(cfg)
        if self._ai_tools is None or self._ai_cfg_signature != signature:
            self._ai_tools = AITools(cfg)
            self._ai_cfg_signature = signature
        return self._ai_tools


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

    if _PYDANTIC_V2 and ConfigDict is not None:
        model_config = ConfigDict(arbitrary_types_allowed=True)
    else:
        class Config:
            arbitrary_types_allowed = True

    waiter: Waiter
    sign_chats: dict  # 签到配置列表, int -> list[SignChatV3]
    chat_messages: dict  # 收到的消息, int -> dict[int, Optional[Message]]
    waiting_message: Optional[Message] = None  # 正在处理的消息
    stop_after_current_action: bool = False
    stop_reason: Optional[str] = None
    last_callback_answer: Optional[str] = None
    current_action_index: Optional[int] = None
    current_action_total: Optional[int] = None
    current_action_description: str = ""
    logged_action_message_markers: set = Field(default_factory=set)


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
            stop_after_current_action=False,
            stop_reason=None,
            last_callback_answer=None,
            current_action_index=None,
            current_action_total=None,
            current_action_description="",
            logged_action_message_markers=set(),
        )

    @staticmethod
    def _resolve_action_delay(action, fallback_delay: float) -> float:
        raw_delay = getattr(action, "delay", None)
        if raw_delay is None:
            return max(float(fallback_delay or 0), 0.0)

        delay_text = str(raw_delay).strip()
        if not delay_text:
            return max(float(fallback_delay or 0), 0.0)

        try:
            if "-" in delay_text:
                start_text, end_text = delay_text.split("-", 1)
                start = float(start_text)
                end = float(end_text)
                if end < start:
                    start, end = end, start
                return max(random.uniform(start, end), 0.0)
            return max(float(delay_text), 0.0)
        except (TypeError, ValueError):
            return max(float(fallback_delay or 0), 0.0)

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
                resolved_peer = False

                # Historical configs may store a user/bot id before Pyrogram knows
                # its access hash. get_users warms the local peer cache.
                if chat.chat_id > 0:
                    try:
                        await self.app.get_users(chat.chat_id)
                        self.log(
                            f"Preheated peer with get_users: {chat.chat_id}",
                            level="WARNING",
                        )
                        resolved_peer = True
                        last_error = None
                    except Exception as e2:
                        last_error = e2

                if not resolved_peer:
                    cached = self._find_cached_chat(chat.chat_id, chat.name)
                    if cached:
                        username = cached.get("username")
                        cached_id = cached.get("id")
                        if username:
                            try:
                                resolved = await self.app.get_chat(username)
                                self.log(
                                    f"Preheated peer with cached username: {chat.chat_id} -> @{username}",
                                    level="WARNING",
                                )
                                chat.chat_id = resolved.id
                                resolved_peer = True
                                last_error = None
                            except Exception as e2:
                                last_error = e2
                        if (
                            not resolved_peer
                            and cached_id
                            and cached_id != chat.chat_id
                        ):
                            try:
                                await self.app.get_chat(cached_id)
                                self.log(
                                    f"Preheated peer with cached chat_id: {chat.chat_id} -> {cached_id}",
                                    level="WARNING",
                                )
                                chat.chat_id = cached_id
                                resolved_peer = True
                                last_error = None
                            except Exception as e2:
                                last_error = e2

                if not resolved_peer:
                    candidates = []
                    if chat.chat_id > 0:
                        candidates.append(-chat.chat_id)
                        candidates.append(int(f"-100{chat.chat_id}"))
                    elif chat.chat_id < 0 and not str(chat.chat_id).startswith("-100"):
                        candidates.append(int(f"-100{abs(chat.chat_id)}"))

                    for candidate in candidates:
                        if candidate == chat.chat_id:
                            continue
                        try:
                            await self.app.get_chat(candidate)
                            self.log(
                                f"Preheated peer with fallback chat_id: {chat.chat_id} -> {candidate}",
                                level="WARNING",
                            )
                            chat.chat_id = candidate
                            resolved_peer = True
                            last_error = None
                            break
                        except Exception as e2:
                            last_error = e2
                            continue

                if not resolved_peer:
                    self.log(
                        f"Failed to preheat chat_id={chat.chat_id}, error={type(last_error).__name__}: {last_error}",
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
        self.log(self._describe_chat_run(chat))
        total_actions = len(chat.actions)
        if total_actions == 0:
            raise RuntimeError("任务没有配置任何执行动作")
        max_flow_attempts = _read_positive_int_env("SIGN_TASK_FLOW_RETRY_ATTEMPTS", 3, 1)
        last_error: Optional[Exception] = None

        for flow_attempt in range(1, max_flow_attempts + 1):
            if max_flow_attempts > 1:
                self.log(f"开始第 {flow_attempt}/{max_flow_attempts} 次脚本流程尝试")
            try:
                self.context.chat_messages[chat.chat_id].clear()
                self.context.stop_after_current_action = False
                self.context.stop_reason = None
                self.context.last_callback_answer = None
                for index, action in enumerate(chat.actions, start=1):
                    action_description = self._set_current_action_context(
                        index,
                        total_actions,
                        action,
                    )
                    action_delay = self._resolve_action_delay(
                        action,
                        float(chat.action_interval or 0) if index > 1 else 0.0,
                    )
                    try:
                        if action_delay > 0:
                            self.log(
                                f"{self._current_action_step_label()}将在 {action_delay:g} 秒后执行：{action_description}"
                            )
                        self.log(
                            f"正在执行{self._current_action_step_label()}：{action_description}"
                        )
                        if action_delay > 0:
                            await asyncio.sleep(action_delay)
                        next_action = (
                            chat.actions[index] if index < total_actions else None
                        )
                        result = await self.wait_for(
                            chat,
                            action,
                            next_action=next_action,
                        )
                        if result is False:
                            raise RuntimeError(
                                f"{self._current_action_step_label()}执行失败：{action_description}"
                            )
                        self.log(
                            f"{self._current_action_step_label()}执行完成：{action_description}"
                        )
                        if self.context.stop_after_current_action:
                            stop_reason = (self.context.stop_reason or "").strip()
                            self.log(
                                "检测到任务已完成，停止执行后续动作"
                                + (f": {stop_reason}" if stop_reason else "")
                            )
                            self.context.stop_after_current_action = False
                            self.context.stop_reason = None
                            self.context.last_callback_answer = None
                            return
                    finally:
                        self.context.waiting_message = None
                        self._clear_current_action_context()
                return
            except Exception as exc:
                last_error = exc
                self.context.waiting_message = None
                if flow_attempt >= max_flow_attempts:
                    break
                self.log(
                    f"脚本流程第 {flow_attempt}/{max_flow_attempts} 次尝试失败，"
                    f"将从第 1 步重新开始: {exc}",
                    level="WARNING",
                )
                await asyncio.sleep(max(float(chat.action_interval or 0), 1.0))

        raise RuntimeError(
            f"脚本流程尝试 {max_flow_attempts} 次仍失败: {last_error}"
        ) from last_error

    async def run(
        self, num_of_dialogs: int = 0, only_once: bool = False, force_rerun: bool = False
    ):
        if self.app.in_memory or self.app.session_string:
            return await self.in_memory_run(
                num_of_dialogs, only_once=only_once, force_rerun=force_rerun
            )
        return await self.normal_run(
            num_of_dialogs, only_once=only_once, force_rerun=force_rerun
        )

    async def in_memory_run(
        self, num_of_dialogs: int = 0, only_once: bool = False, force_rerun: bool = False
    ):
        # Use the proper async context manager to integrate with ref counting
        # This avoids "Client is already terminated" when normal_run's internal
        # login() also uses 'async with app' which decrements refs to 0
        async with self.app:
            await self.normal_run(
                num_of_dialogs, only_once=only_once, force_rerun=force_rerun
            )

    async def normal_run(
        self, num_of_dialogs: int = 0, only_once: bool = False, force_rerun: bool = False
    ):
        if self.user is None:
            await self.ensure_user()

        config = self.load_config(self.cfg_cls)
        if config.requires_ai:
            self.ensure_ai_cfg()
        if not config.chats:
            raise RuntimeError("Task config has no chats to execute")

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
                    self.log(
                        f"签到失败: {_e} (chat_id={chat.chat_id})",
                        level="WARNING",
                    )
                    logger.warning(_e, exc_info=True)
                    continue
                finally:
                    # Always clear chat messages to prevent memory accumulation
                    self.context.chat_messages[chat.chat_id].clear()

                await asyncio.sleep(config.sign_interval)

            if success_count == 0 and len(config.chats) > 0:
                raise RuntimeError("所有会话均执行失败（详细请看运行日志）")

            sign_record[str(now.date())] = now.isoformat()
            atomic_write_json(self.sign_record_file, sign_record)

        def need_sign(last_date_str):
            if force_rerun:
                return True
            if last_date_str not in sign_record:
                return True
            _last_sign_at = datetime.fromisoformat(sign_record[last_date_str])
            _cron_it = croniter(self._validate_sign_at(config.sign_at), _last_sign_at)
            _next_run: datetime = _cron_it.next(datetime)
            if _next_run > now:
                return False
            return True

        try:
            while True:
                if need_update_handlers and message_handler_ref is None:
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
                            try:
                                if getattr(self.app, "is_connected", False):
                                    await self.app.stop()
                            except ConnectionError:
                                # Already terminated - ignore
                                pass

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
        finally:
            # Always clean up handlers, even on exception
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
            # Clear context to release message references
            if hasattr(self, 'context') and self.context is not None:
                self.context.chat_messages.clear()
                self.context.sign_chats.clear()
                self.context.waiting_message = None
                if hasattr(self.context, 'logged_action_message_markers'):
                    self.context.logged_action_message_markers.clear()
            trim_memory()

    async def run_once(self, num_of_dialogs: int = 0):
        return await self.run(num_of_dialogs, only_once=True, force_rerun=True)

    async def send_text(
        self, chat_id: int, text: str, delete_after: int = None, **kwargs
    ):
        if self.user is None:
            await self.ensure_user()
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
            await self.ensure_user()
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
        chat_msgs = self.context.chat_messages[message.chat.id]
        chat_msgs[message.id] = message
        # Bound message cache per chat to prevent memory growth
        if len(chat_msgs) > 200:
            oldest_keys = sorted(chat_msgs.keys())[:100]
            for k in oldest_keys:
                chat_msgs.pop(k, None)

    async def on_message(self, client: Client, message: Message):
        await self._on_message(client, message)

    async def on_edited_message(self, client, message: Message):
        await self._on_message(client, message)

    def _clean_text_for_match(self, text: str) -> str:
        if not text:
            return ""
        text = unicodedata.normalize("NFKC", str(text))
        return "".join(
            ch
            for ch in text.lower()
            if not unicodedata.category(ch).startswith(("P", "S", "Z", "C"))
        )

    def _button_text_matches(self, target_text: str, button_text: str) -> bool:
        if not target_text or not button_text:
            return False
        if target_text == button_text or target_text in button_text:
            return True
        return len(button_text) >= 2 and button_text in target_text

    def _message_matches_chat_thread(self, message: Message, chat: SignChatV3) -> bool:
        if message is None:
            return False
        if chat.message_thread_id is None:
            return True
        msg_thread_id = getattr(message, "message_thread_id", None) or getattr(
            message, "reply_to_top_message_id", None
        )
        return msg_thread_id == chat.message_thread_id

    @staticmethod
    def _normalize_log_text(text: Optional[str], limit: int = 280) -> str:
        value = " / ".join(
            line.strip() for line in str(text or "").splitlines() if line.strip()
        )
        if len(value) > limit:
            return value[: limit - 3] + "..."
        return value

    def _describe_chat_run(self, chat: SignChatV3) -> str:
        parts = [f"开始执行任务对象: Chat ID={chat.chat_id}"]
        if chat.message_thread_id is not None:
            parts.append(f"话题ID={chat.message_thread_id}")
        if chat.name:
            parts.append(f"名称={self._normalize_log_text(chat.name, 60)}")
        parts.append(f"动作数={len(chat.actions)}")
        return " | ".join(parts)

    def _describe_action(self, action: ActionT) -> str:
        if isinstance(action, SendTextAction):
            return f"发送文本消息：{self._normalize_log_text(action.text, 120)}"
        if isinstance(action, SendDiceAction):
            return f"发送骰子：{self._normalize_log_text(str(action.dice), 40)}"
        if isinstance(action, ClickKeyboardByTextAction):
            return f"点击文字按钮：{self._normalize_log_text(action.text, 80)}"
        if isinstance(action, ChooseOptionByImageAction):
            return "识图后点按钮"
        if isinstance(action, ReplyByCalculationProblemAction):
            return "识别计算题并发送答案"
        if isinstance(action, ReplyByImageRecognitionAction):
            return "识图后发送文本"
        if isinstance(action, ClickButtonByCalculationProblemAction):
            return "计算答案后点击按钮"
        if isinstance(action, KeywordNotifyAction):
            keywords = ", ".join(
                self._normalize_log_text(keyword, 24) for keyword in action.keywords[:3]
            )
            if len(action.keywords) > 3:
                keywords += ", ..."
            return f"关键词监听：{keywords or '未配置关键词'}"
        return str(action)

    def _current_action_step_label(self) -> str:
        index = getattr(self.context, "current_action_index", None)
        total = getattr(self.context, "current_action_total", None)
        if index and total:
            return f"第 {index}/{total} 步"
        if index:
            return f"第 {index} 步"
        return "当前步骤"

    def _set_current_action_context(
        self,
        index: int,
        total: int,
        action: ActionT,
    ) -> str:
        description = self._describe_action(action)
        self.context.current_action_index = index
        self.context.current_action_total = total
        self.context.current_action_description = description
        self.context.logged_action_message_markers.clear()
        return description

    def _clear_current_action_context(self) -> None:
        self.context.current_action_index = None
        self.context.current_action_total = None
        self.context.current_action_description = ""
        self.context.logged_action_message_markers.clear()

    def _log_received_target_message(
        self,
        message: Optional[Message],
        *,
        prefix: Optional[str] = None,
        allow_duplicate: bool = False,
    ) -> None:
        if message is None:
            return

        marker = self._message_state_marker(message)
        if not allow_duplicate:
            markers = getattr(self.context, "logged_action_message_markers", None)
            if markers is not None:
                if marker in markers:
                    return
                markers.add(marker)

        summary = self._summarize_target_message(message)
        if not summary:
            return

        if prefix is None:
            if getattr(message, "photo", None):
                prefix = "收到图片"
            elif getattr(message, "text", None) or getattr(message, "caption", None):
                prefix = "收到回复"
            else:
                prefix = "收到任务对象消息"
        self.log(f"{prefix}：{summary}")

    def _summarize_target_message(self, message: Optional[Message]) -> str:
        if message is None:
            return ""

        parts: list[str] = []
        text = self._normalize_log_text(
            getattr(message, "text", None) or getattr(message, "caption", None)
        )
        if text:
            parts.append(text)
        elif getattr(message, "photo", None):
            parts.append("[图片消息]")
        elif getattr(message, "media", None):
            parts.append(f"[{getattr(message.media, 'value', 'media')}]")

        reply_markup = getattr(message, "reply_markup", None)
        button_texts: list[str] = []
        if isinstance(reply_markup, InlineKeyboardMarkup):
            for row in reply_markup.inline_keyboard:
                for button in row:
                    label = self._normalize_log_text(getattr(button, "text", None), 40)
                    if label:
                        button_texts.append(label)
        elif isinstance(reply_markup, ReplyKeyboardMarkup):
            for row in reply_markup.keyboard:
                for button in row:
                    raw_text = button if isinstance(button, str) else getattr(
                        button, "text", ""
                    )
                    label = self._normalize_log_text(raw_text, 40)
                    if label:
                        button_texts.append(label)

        if button_texts:
            preview = " | ".join(button_texts[:4])
            if len(button_texts) > 4:
                preview += " | ..."
            parts.append(f"按钮: {preview}")

        summary = " | ".join(part for part in parts if part).strip()
        if not summary:
            summary = f"message_id={getattr(message, 'id', '-')}"
        return summary

    def _log_target_message(
        self,
        message: Optional[Message],
        *,
        prefix: str = "任务对象消息",
        level: str = "INFO",
    ) -> None:
        summary = self._summarize_target_message(message)
        if summary:
            self.log(f"{prefix}: {summary}", level=level)

    def _reply_markup_marker(self, reply_markup):
        if isinstance(reply_markup, InlineKeyboardMarkup):
            return (
                "inline",
                tuple(
                    tuple(getattr(button, "text", "") for button in row)
                    for row in reply_markup.inline_keyboard
                ),
            )
        if isinstance(reply_markup, ReplyKeyboardMarkup):
            return (
                "reply",
                tuple(
                    tuple(
                        button if isinstance(button, str) else getattr(button, "text", "")
                        for button in row
                    )
                    for row in reply_markup.keyboard
                ),
            )
        return None

    def _message_state_marker(self, message: Message):
        return (
            getattr(message, "id", None),
            getattr(message, "text", None),
            getattr(message, "caption", None),
            getattr(message, "edit_date", None),
            self._reply_markup_marker(getattr(message, "reply_markup", None)),
        )

    async def _chat_state_snapshot(
        self,
        chat: SignChatV3,
        *,
        history_limit: int,
    ) -> dict[int, tuple]:
        state: dict[int, tuple] = {}
        messages_dict = self.context.chat_messages.get(chat.chat_id) or {}
        for message in messages_dict.values():
            if not self._message_matches_chat_thread(message, chat):
                continue
            state[message.id] = self._message_state_marker(message)

        try:
            async for message in self.app.get_chat_history(
                chat.chat_id,
                limit=history_limit,
            ):
                if not self._message_matches_chat_thread(message, chat):
                    continue
                state[message.id] = self._message_state_marker(message)
        except Exception as e:
            self.log(f"点击前消息状态快照失败: {e}", level="WARNING")
        return state

    async def _wait_for_chat_advance(
        self,
        chat: SignChatV3,
        before_state: dict[int, tuple],
        *,
        history_limit: int,
        timeout: float,
    ) -> bool:
        deadline = time.perf_counter() + max(timeout, 0.5)
        while time.perf_counter() < deadline:
            await asyncio.sleep(0.25)
            current_state = await self._chat_state_snapshot(
                chat,
                history_limit=history_limit,
            )
            for message_id, marker in current_state.items():
                if before_state.get(message_id) != marker:
                    return True
        return False

    def _message_has_button_text(
        self,
        message: Message,
        text: str,
    ) -> bool:
        target_text = self._clean_text_for_match(text)
        if not target_text:
            return False

        reply_markup = getattr(message, "reply_markup", None)
        if isinstance(reply_markup, InlineKeyboardMarkup):
            rows = reply_markup.inline_keyboard
        elif isinstance(reply_markup, ReplyKeyboardMarkup):
            rows = reply_markup.keyboard
        else:
            return False

        for row in rows:
            for button in row:
                button_text = (
                    button if isinstance(button, str) else getattr(button, "text", "")
                )
                if not button_text:
                    continue
                if self._button_text_matches(
                    target_text,
                    self._clean_text_for_match(button_text),
                ):
                    return True
        return False

    def _resolve_message_thread_id(self, message: Message) -> Optional[int]:
        return getattr(message, "message_thread_id", None) or getattr(
            message, "reply_to_top_message_id", None
        )

    def _collect_clickable_buttons(self, message: Message) -> list[tuple[str, Any, str]]:
        reply_markup = getattr(message, "reply_markup", None)
        clickable_buttons: list[tuple[str, Any, str]] = []
        if isinstance(reply_markup, InlineKeyboardMarkup):
            for row in reply_markup.inline_keyboard:
                for button in row:
                    button_text = getattr(button, "text", "")
                    if button_text:
                        clickable_buttons.append(("inline", button, button_text))
        elif isinstance(reply_markup, ReplyKeyboardMarkup):
            for row in reply_markup.keyboard:
                for button in row:
                    button_text = (
                        button if isinstance(button, str) else getattr(button, "text", "")
                    )
                    if button_text:
                        clickable_buttons.append(("reply", button, button_text))
        return clickable_buttons

    def _message_supports_next_action(self, action: ActionT, message: Message) -> bool:
        if message is None:
            return False
        reply_markup = getattr(message, "reply_markup", None)
        if isinstance(action, ClickKeyboardByTextAction):
            return self._message_has_button_text(message, action.text)
        if isinstance(action, ChooseOptionByImageAction):
            return bool(message.photo and self._collect_clickable_buttons(message))
        if isinstance(action, ReplyByCalculationProblemAction):
            return bool(message.text or message.caption)
        if isinstance(action, ReplyByImageRecognitionAction):
            return bool(message.photo)
        if isinstance(action, ClickButtonByCalculationProblemAction):
            return bool((message.text or message.caption) and reply_markup)
        return False

    async def _chat_has_action_candidate(
        self,
        chat: SignChatV3,
        action: ActionT,
        *,
        history_limit: int,
    ) -> bool:
        messages_dict = self.context.chat_messages.get(chat.chat_id) or {}
        for message in reversed(list(messages_dict.values())):
            if self._message_matches_chat_thread(message, chat) and (
                self._message_supports_next_action(action, message)
            ):
                return True

        try:
            async for message in self.app.get_chat_history(
                chat.chat_id,
                limit=history_limit,
            ):
                if self._message_matches_chat_thread(message, chat) and (
                    self._message_supports_next_action(action, message)
                ):
                    return True
        except Exception as e:
            self.log(f"下一步动作候选消息检查失败: {e}", level="WARNING")
        return False

    async def _wait_for_next_action_candidate(
        self,
        chat: SignChatV3,
        next_action: ActionT,
        before_state: dict[int, tuple],
        *,
        history_limit: int,
        timeout: float,
    ) -> bool:
        deadline = time.perf_counter() + max(timeout, 0.5)
        while time.perf_counter() < deadline:
            await asyncio.sleep(0.3)
            current_state = await self._chat_state_snapshot(
                chat,
                history_limit=history_limit,
            )
            changed_ids = {
                message_id
                for message_id, marker in current_state.items()
                if before_state.get(message_id) != marker
            }

            messages_dict = self.context.chat_messages.get(chat.chat_id) or {}
            for message in messages_dict.values():
                if (
                    self._message_matches_chat_thread(message, chat)
                    and getattr(message, "id", None) in changed_ids
                    and self._message_supports_next_action(next_action, message)
                ):
                    return True

            try:
                async for message in self.app.get_chat_history(
                    chat.chat_id,
                    limit=history_limit,
                ):
                    if (
                        self._message_matches_chat_thread(message, chat)
                        and getattr(message, "id", None) in changed_ids
                        and self._message_supports_next_action(next_action, message)
                    ):
                        return True
            except Exception as e:
                self.log(f"下一步动作候选消息检查失败: {e}", level="WARNING")
        return False

    def _text_has_terminal_success_text(self, text: Optional[str]) -> bool:
        normalized = str(text or "").strip().lower()
        if not normalized:
            return False
        failure_markers = (
            "失败",
            "错误",
            "异常",
            "未成功",
            "无法",
            "failed",
            "failure",
            "error",
            "invalid",
        )
        if any(marker in normalized for marker in failure_markers):
            return False
        additional_action_markers = (
            "请完成",
            "请先",
            "请根据",
            "请回答",
            "请填写",
            "请发送",
            "请点击",
            "请选择",
            "进行验证",
            "完成验证",
            "验证后",
            "诗句填空",
            "填空",
            "答题",
            "作答",
            "输入答案",
            "发送答案",
            "验证码",
            "口令",
            "滑块",
            "拖动",
        )
        if any(marker in normalized for marker in additional_action_markers):
            return False
        strong_success_markers = (
            "签到成功",
            "已签到",
            "已经签到",
            "已经签到过",
            "今天已经签到",
            "今日已签到",
            "今日已经签到",
            "您今天已经签到",
            "您今日已签到",
            "签到过了",
            "重复签到",
            "任务完成",
            "执行完成",
            "操作完成",
        )
        if any(marker in normalized for marker in strong_success_markers):
            return True
        generic_success_markers = (
            "成功",
            "完成",
            "success",
            "successful",
            "done",
            "completed",
        )
        success_context_markers = (
            "签到",
            "任务",
            "执行",
            "操作",
            "领取",
            "打卡",
            "run",
            "task",
            "checkin",
            "check-in",
            "sign",
        )
        return any(marker in normalized for marker in generic_success_markers) and any(
            marker in normalized for marker in success_context_markers
        )

    def _callback_text_has_terminal_success_text(self, text: Optional[str]) -> bool:
        normalized = str(text or "").strip().lower()
        if not normalized:
            return False
        if not self._text_has_terminal_success_text(normalized):
            return False
        callback_success_markers = (
            "签到成功",
            "已签到",
            "已经签到",
            "已经签到过",
            "今天已经签到",
            "今日已签到",
            "今日已经签到",
            "您今天已经签到",
            "您今日已签到",
            "签到过了",
            "重复签到",
            "任务完成",
            "执行完成",
            "操作完成",
            "success",
            "successful",
            "done",
            "completed",
        )
        return any(marker in normalized for marker in callback_success_markers)

    def _message_has_terminal_success_text(self, message: Message) -> bool:
        text = "\n".join(
            item
            for item in [
                getattr(message, "text", None),
                getattr(message, "caption", None),
            ]
            if item
        )
        return self._text_has_terminal_success_text(text)

    async def _wait_for_terminal_success(
        self,
        chat: SignChatV3,
        before_state: dict[int, tuple],
        *,
        history_limit: int,
        timeout: float,
    ) -> bool:
        deadline = time.perf_counter() + max(timeout, 0.5)
        while time.perf_counter() < deadline:
            await asyncio.sleep(0.3)
            current_state = await self._chat_state_snapshot(
                chat,
                history_limit=history_limit,
            )
            changed_ids = {
                message_id
                for message_id, marker in current_state.items()
                if before_state.get(message_id) != marker
            }

            messages_dict = self.context.chat_messages.get(chat.chat_id) or {}
            for message in messages_dict.values():
                if (
                    self._message_matches_chat_thread(message, chat)
                    and getattr(message, "id", None) in changed_ids
                    and self._message_has_terminal_success_text(message)
                ):
                    self.context.stop_reason = self._summarize_target_message(message)
                    self._log_received_target_message(message, prefix="收到回复")
                    return True

            try:
                async for message in self.app.get_chat_history(
                    chat.chat_id,
                    limit=history_limit,
                ):
                    if (
                        self._message_matches_chat_thread(message, chat)
                        and getattr(message, "id", None) in changed_ids
                        and self._message_has_terminal_success_text(message)
                    ):
                        self.context.stop_reason = self._summarize_target_message(message)
                        self._log_received_target_message(message, prefix="收到回复")
                        return True
            except Exception as e:
                self.log(f"最终成功消息检查失败: {e}", level="WARNING")
        return False

    async def _handle_post_click_followup(
        self,
        chat: SignChatV3,
        *,
        action_text: str,
        next_action: Optional[ActionT],
        before_click_state: dict[int, tuple],
        history_limit: int,
        timeout: float,
    ) -> str:
        callback_text = (self.context.last_callback_answer or "").strip()
        if self._callback_text_has_terminal_success_text(callback_text):
            self.context.stop_after_current_action = True
            self.context.stop_reason = callback_text
            self.log(
                f"按钮「{action_text}」回调提示表明任务已完成，将跳过后续动作: {callback_text}"
            )
            return "success"

        if await self._wait_for_terminal_success(
            chat,
            before_click_state,
            history_limit=history_limit,
            timeout=timeout,
        ):
            self.context.stop_after_current_action = True
            self.log(f"按钮「{action_text}」后已检测到任务完成响应，将跳过后续动作")
            return "success"

        if next_action is not None and await self._wait_for_next_action_candidate(
            chat,
            next_action,
            before_click_state,
            history_limit=history_limit,
            timeout=timeout,
        ):
            self.log(f"按钮「{action_text}」后已检测到下一步动作可执行，继续流程")
            return "next"

        return "none"

    async def _click_inline_button(self, message: Message, btn) -> bool:
        callback_data = getattr(btn, "callback_data", None)
        if callback_data is not None:
            if (
                await self.request_callback_answer(
                    self.app,
                    message.chat.id,
                    message.id,
                    callback_data,
                )
                is not None
            ):
                return True

        click = getattr(message, "click", None)
        if callable(click):
            for args, kwargs in (
                ((getattr(btn, "text", None),), {}),
                ((), {"text": getattr(btn, "text", None)}),
            ):
                try:
                    await click(*args, **kwargs)
                    self.log("点击完成")
                    return True
                except TypeError:
                    continue
                except Exception as e:
                    if _is_callback_data_invalid(e):
                        self.log(
                            "Message.click 也无法确认按钮回调，继续等待机器人后续消息确认",
                            level="WARNING",
                        )
                    else:
                        self.log(f"Message.click 无法确认按钮回调: {e}", level="WARNING")
                    break

        if callback_data is None:
            self.log(
                "按钮没有可用 callback_data，且 Message.click 未确认点击结果，将等待后续消息判断",
                level="WARNING",
            )
        else:
            self.log(
                "按钮回调未被 Telegram API 确认，将等待后续消息判断是否已推进",
                level="WARNING",
            )
        return False

    async def _click_keyboard_by_text_result(
        self,
        action: ClickKeyboardByTextAction,
        message: Message,
        *,
        message_thread_id: Optional[int] = None,
        before_click=None,
        log_not_found: bool = True,
    ) -> tuple[bool, bool]:
        target_text = self._clean_text_for_match(action.text)
        if not target_text:
            self.log("Click button action has empty target text after cleaning", level="WARNING")
            return False, False

        if reply_markup := message.reply_markup:
            if isinstance(reply_markup, InlineKeyboardMarkup):
                flat_buttons = (b for row in reply_markup.inline_keyboard for b in row)
                for btn in flat_buttons:
                    if not btn.text:
                        continue
                    btn_text_clean = self._clean_text_for_match(btn.text)
                    if self._button_text_matches(target_text, btn_text_clean):
                        self.context.last_callback_answer = None
                        self.log(f"成功匹配到并点击按钮: [{btn.text}] (匹配词: {action.text})")
                        if before_click:
                            await before_click()
                        return await self._click_inline_button(message, btn), True
                if log_not_found:
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
                        if self._button_text_matches(target_text, btn_text_clean):
                            self.log(f"成功匹配并发送回复键盘文本: [{btn_text}] (匹配词: {action.text})")
                            kwargs = {}
                            if message_thread_id is not None:
                                kwargs["message_thread_id"] = message_thread_id
                            if before_click:
                                await before_click()
                            await self.send_message(message.chat.id, btn_text, **kwargs)
                            return True, True
                if log_not_found:
                    self.log(
                        f"Target button '{action.text}' not found in reply keyboard.",
                        level="WARNING",
                    )
        return False, False

    async def _click_keyboard_by_text(
        self,
        action: ClickKeyboardByTextAction,
        message: Message,
        *,
        message_thread_id: Optional[int] = None,
    ):
        clicked, _matched = await self._click_keyboard_by_text_result(
            action,
            message,
            message_thread_id=message_thread_id,
        )
        return clicked

    async def _reply_by_calculation_problem(
        self, action: ReplyByCalculationProblemAction, message
    ):
        if message.text:
            self._log_received_target_message(message)
            self.log("AI 正在分析计算题")
            self.log(f"题目内容：{self._normalize_log_text(message.text, 220)}")
            if (action.ai_prompt or "").strip():
                self.log("当前 AI 动作使用自定义提示词")
            answer = await self.get_ai_tools().calculate_problem(
                message.text,
                system_prompt=action.ai_prompt,
            )
            answer = (answer or "").strip()
            if not answer:
                self.log("AI 未返回有效答案", level="WARNING")
                return False
            self.log(f"AI 计算结果：{answer}")
            await self.send_message(message.chat.id, answer)
            return True
        return False

    async def _reply_by_image_recognition(
        self, action: ReplyByImageRecognitionAction, message
    ):
        if not message.photo:
            return False
        self._log_received_target_message(message)
        self.log("AI 正在分析图片中的文字")
        image_buffer: BinaryIO = await self.app.download_media(
            message.photo.file_id, in_memory=True
        )
        try:
            image_buffer.seek(0)
            image_bytes = image_buffer.read()
        finally:
            if hasattr(image_buffer, "close"):
                image_buffer.close()
            image_buffer = None
            trim_memory()

        if (action.ai_prompt or "").strip():
            self.log("当前 AI 动作使用自定义提示词")
        text = await self.get_ai_tools().extract_text_by_image(
            image_bytes,
            system_prompt=action.ai_prompt,
        )
        del image_bytes
        text = (text or "").strip()
        if not text:
            self.log("AI 未识别到可发送文本", level="WARNING")
            return False
        self.log(f"AI 识别结果：{text}")
        await self.send_message(message.chat.id, text)
        return True

    async def _click_button_by_calculation_problem(
        self, action: ClickButtonByCalculationProblemAction, message
    ):
        if not message.text:
            return False
        self._log_received_target_message(message)
        self.log("AI 正在计算按钮答案")
        if (action.ai_prompt or "").strip():
            self.log("当前 AI 动作使用自定义提示词")
        answer = await self.get_ai_tools().calculate_problem(
            message.text,
            system_prompt=action.ai_prompt,
        )
        answer = (answer or "").strip()
        if not answer:
            self.log("AI 未返回可用于点击的答案", level="WARNING")
            return False
        self.log(f"AI 计算结果：{answer}")
        proxy_action = ClickKeyboardByTextAction(text=answer)
        return await self._click_keyboard_by_text(proxy_action, message)

    async def _choose_option_by_image(self, action: ChooseOptionByImageAction, message):
        if not message.photo:
            return False
        clickable_buttons = self._collect_clickable_buttons(message)
        if clickable_buttons:
            self._log_received_target_message(message)
            self.log("AI 正在分析图片并匹配可点击按钮")
            image_buffer: BinaryIO = await self.app.download_media(
                message.photo.file_id, in_memory=True
            )
            try:
                image_buffer.seek(0)
                image_bytes = image_buffer.read()
            finally:
                if hasattr(image_buffer, "close"):
                    image_buffer.close()
                image_buffer = None
                trim_memory()

            options = [button_text for _, _, button_text in clickable_buttons]
            if not options:
                self.log("未找到可供点击的按钮", level="WARNING")
                return False
            question_text = (message.caption or message.text or "").strip()
            if not question_text:
                question_text = "选择正确的选项"
            if (action.ai_prompt or "").strip():
                self.log("当前 AI 动作使用自定义提示词")
            result_indexes = await self.get_ai_tools().choose_options_by_image(
                image_bytes,
                question_text,
                list(enumerate(options, start=1)),
                system_prompt=action.ai_prompt,
            )
            del image_bytes
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
                button_kind, target_btn, result = clickable_buttons[selected_idx]
                self.log(f"AI 选择并点击选项：{result}")
                if button_kind == "inline":
                    if await self._click_inline_button(message, target_btn):
                        clicked += 1
                else:
                    kwargs = {}
                    message_thread_id = self._resolve_message_thread_id(message)
                    if message_thread_id is not None:
                        kwargs["message_thread_id"] = message_thread_id
                    await self.send_message(message.chat.id, result, **kwargs)
                    clicked += 1
                await asyncio.sleep(0.3)
            return clicked > 0
        return False

    async def wait_for(
        self,
        chat: SignChatV3,
        action: ActionT,
        timeout=None,
        *,
        next_action: Optional[ActionT] = None,
    ):
        if timeout is None:
            timeout = _read_positive_float_env("SIGN_TASK_ACTION_TIMEOUT", 25.0, 5.0)
        kwargs = {}
        if chat.message_thread_id is not None:
            kwargs["message_thread_id"] = chat.message_thread_id
        if isinstance(action, SendTextAction):
            return await self.send_message(chat.chat_id, action.text, chat.delete_after, **kwargs)
        elif isinstance(action, SendDiceAction):
            return await self.send_dice(chat.chat_id, action.dice, chat.delete_after, **kwargs)
        elif isinstance(action, KeywordNotifyAction):
            self.log("关键词监听通知动作为后台常驻监听配置，当前运行时跳过")
            return True
        history_limit = _read_positive_int_env("SIGN_TASK_HISTORY_LOOKBACK", 12, 3)
        self.context.waiter.add(chat.chat_id)
        start = time.perf_counter()
        last_message = None
        self.context.last_callback_answer = None
        try:
            if isinstance(action, ClickKeyboardByTextAction):
                next_history_scan = 0.0
                while time.perf_counter() - start < timeout:
                    messages_dict = self.context.chat_messages.get(chat.chat_id) or {}
                    for message in reversed(list(messages_dict.values())):
                        if message is None:
                            continue
                        if not self._message_matches_chat_thread(message, chat):
                            continue
                        self._log_received_target_message(message)
                        self.context.waiting_message = message

                        before_click_state: dict[int, tuple] = {}

                        async def remember_before_click():
                            nonlocal before_click_state
                            before_click_state = await self._chat_state_snapshot(
                                chat,
                                history_limit=history_limit,
                            )

                        ok, matched = await self._click_keyboard_by_text_result(
                            action,
                            message,
                            message_thread_id=chat.message_thread_id,
                            before_click=remember_before_click,
                            log_not_found=False,
                        )
                        if ok:
                            if next_action is not None:
                                follow_timeout = min(6.0, timeout)
                                await self._handle_post_click_followup(
                                    chat,
                                    action_text=action.text,
                                    next_action=next_action,
                                    before_click_state=before_click_state,
                                    history_limit=history_limit,
                                    timeout=follow_timeout,
                                )
                            self.context.chat_messages[chat.chat_id][message.id] = None
                            return True
                        if matched:
                            self.context.waiting_message = None
                            follow_timeout = min(6.0, timeout)
                            if next_action is not None:
                                followup_state = await self._handle_post_click_followup(
                                    chat,
                                    action_text=action.text,
                                    next_action=next_action,
                                    before_click_state=before_click_state,
                                    history_limit=history_limit,
                                    timeout=follow_timeout,
                                )
                                if followup_state in {"success", "next"}:
                                    return True
                                self.log(
                                    "按钮点击返回异常，且未检测到下一步动作，准备重试完整流程",
                                    level="WARNING",
                                )
                                return False
                            if await self._wait_for_terminal_success(
                                chat,
                                before_click_state,
                                history_limit=history_limit,
                                timeout=follow_timeout,
                            ):
                                self.log(
                                    f"按钮「{action.text}」回调未确认，但已检测到成功回复，判定该步骤完成"
                                )
                                return True
                            self.log(
                                "按钮点击返回异常，且未检测到明确成功消息，准备重试完整流程",
                                level="WARNING",
                            )
                            return False

                    now_ts = time.perf_counter()
                    if now_ts >= next_history_scan:
                        next_history_scan = now_ts + 1.5
                        try:
                            history_messages = []
                            async for message in self.app.get_chat_history(
                                chat.chat_id,
                                limit=history_limit,
                            ):
                                history_messages.append(message)

                            for message in history_messages:
                                if message is None:
                                    continue
                                if not self._message_matches_chat_thread(message, chat):
                                    continue
                                self._log_received_target_message(message)

                                before_click_state: dict[int, tuple] = {}

                                async def remember_before_click():
                                    nonlocal before_click_state
                                    before_click_state = await self._chat_state_snapshot(
                                        chat,
                                        history_limit=history_limit,
                                    )

                                ok, matched = await self._click_keyboard_by_text_result(
                                    action,
                                    message,
                                    message_thread_id=chat.message_thread_id,
                                    before_click=remember_before_click,
                                    log_not_found=False,
                                )
                                if ok:
                                    if next_action is not None:
                                        follow_timeout = min(6.0, timeout)
                                        await self._handle_post_click_followup(
                                            chat,
                                            action_text=action.text,
                                            next_action=next_action,
                                            before_click_state=before_click_state,
                                            history_limit=history_limit,
                                            timeout=follow_timeout,
                                        )
                                    return True
                                if matched:
                                    self.context.waiting_message = None
                                    follow_timeout = min(6.0, timeout)
                                    if next_action is not None:
                                        followup_state = await self._handle_post_click_followup(
                                            chat,
                                            action_text=action.text,
                                            next_action=next_action,
                                            before_click_state=before_click_state,
                                            history_limit=history_limit,
                                            timeout=follow_timeout,
                                        )
                                        if followup_state in {"success", "next"}:
                                            return True
                                        self.log(
                                            "按钮点击返回异常，且未检测到下一步动作，准备重试完整流程",
                                            level="WARNING",
                                        )
                                        return False
                                    if await self._wait_for_terminal_success(
                                        chat,
                                        before_click_state,
                                        history_limit=history_limit,
                                        timeout=follow_timeout,
                                    ):
                                        self.log(
                                            f"按钮「{action.text}」回调未确认，但已检测到成功回复，判定该步骤完成"
                                        )
                                        return True
                                    self.log(
                                        "按钮点击返回异常，且未检测到明确成功消息，准备重试完整流程",
                                        level="WARNING",
                                    )
                                    return False
                        except Exception as e:
                            self.log(f"最近消息按钮查找失败: {e}", level="WARNING")

                    await asyncio.sleep(0.3)

                self.log(
                    f"未在 {timeout}s 内找到可点击按钮，不再直接发送按钮文本: {action.text}",
                    level="WARNING",
                )
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
                    self._log_received_target_message(message)
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
                    self.log("等待超时，尝试从最近消息回退处理当前步骤", level="WARNING")
                    async for message in self.app.get_chat_history(chat.chat_id, limit=history_limit):
                        self._log_received_target_message(message)
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

            self.log(
                f"{self._current_action_step_label()}等待超时：{self._describe_action(action)}",
                level="WARNING",
            )
            raise RuntimeError(
                f"Action did not complete within {timeout}s. chat_id={chat.chat_id}, action={action}"
            )
        finally:
            self.context.waiter.discard(chat.chat_id)
            self.context.waiting_message = None
            self.context.last_callback_answer = None

    async def request_callback_answer(
        self,
        client: Client,
        chat_id: Union[int, str],
        message_id: int,
        callback_data: Union[str, bytes],
        **kwargs,
    ):
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                answer = await client.request_callback_answer(
                    chat_id, message_id, callback_data=callback_data, **kwargs
                )
                callback_message = self._normalize_log_text(
                    getattr(answer, "message", None), 220
                )
                callback_url = self._normalize_log_text(getattr(answer, "url", None), 220)
                self.context.last_callback_answer = callback_message or None
                self.log("点击完成")
                if callback_message:
                    self.log(f"收到回复（按钮提示）：{callback_message}")
                if callback_url:
                    self.log(f"按钮回调跳转：{callback_url}")
                return answer
            except errors.FloodWait as e:
                wait_seconds = max(int(getattr(e, "value", 1) or 1), 1)
                self.log(
                    f"触发 FloodWait，{wait_seconds}s 后重试 ({attempt}/{max_retries})",
                    level="WARNING",
                )
                if attempt >= max_retries:
                    self.log(e, level="ERROR")
                    return None
                await asyncio.sleep(wait_seconds)
            except (TimeoutError, asyncio.TimeoutError, OSError, ConnectionError) as e:
                backoff = min(2**attempt, 8)
                self.log(
                    f"按钮回调暂未响应，{backoff}s 后重试确认 ({attempt}/{max_retries})",
                    level="WARNING",
                )
                if attempt >= max_retries:
                    self.log(e, level="ERROR")
                    return None
                try:
                    await self._ensure_app_ready()
                except Exception as reconnect_exc:
                    self.log(
                        f"按钮回调重连失败: {type(reconnect_exc).__name__}: {reconnect_exc}",
                        level="WARNING",
                    )
                await asyncio.sleep(backoff)
            except errors.BadRequest as e:
                if _is_callback_data_invalid(e):
                    self.log(
                        "Telegram 返回 DATA_INVALID，按钮点击结果无法由 callback API 确认，将改用后续消息判断",
                        level="WARNING",
                    )
                    return None
                self.log(e, level="ERROR")
                return None
        return None

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
            await self.ensure_user()
        results = []
        async with self.app:
            for n in range(next_times):
                next_dt: datetime = it.next(ret_type=datetime) + timedelta(
                    seconds=random.randint(0, random_seconds)
                )
                results.append({"at": next_dt.isoformat(), "text": text})
                await self._call_with_retry(
                    lambda _next_dt=next_dt: self.app.send_message(
                        chat_id,
                        text,
                        schedule_date=_next_dt,
                    ),
                    operation=f"计划发送消息到 {chat_id}",
                )
                await asyncio.sleep(0.1)
                print_to_user(f"已配置次数：{n + 1}")
        self.log(f"已配置定时发送消息，次数{next_times}")
        return results

    async def get_schedule_messages(self, chat_id):
        if self.user is None:
            await self.ensure_user()
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
        headers = dict(f.headers or {})
        headers.update({"Content-Type": "application/json"})
        content = str(message).encode("utf-8")
        timeout = httpx.Timeout(10.0, connect=5.0)
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
            last_error: Exception | None = None
            for attempt in range(1, 4):
                try:
                    response = await client.post(
                        str(f.url),
                        content=content,
                        headers=headers,
                    )
                    response.raise_for_status()
                    return
                except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                    last_error = exc
                    if attempt >= 3:
                        break
                    await asyncio.sleep(min(2**(attempt - 1), 4))
            if last_error is not None:
                raise last_error

    async def forward_to_external(self, match_cfg: MatchConfig, message: Message):
        if not match_cfg.external_forwards:
            return
        for forward in match_cfg.external_forwards:
            self.log(f"转发消息至{forward}")
            if isinstance(forward, UDPForward):
                create_logged_task(
                    self.udp_forward(
                        forward,
                        message,
                    ),
                    logger=logger,
                    description=f"UDP forward {forward.host}:{forward.port}",
                )
            elif isinstance(forward, HttpCallback):
                create_logged_task(
                    self.http_api_callback(
                        forward,
                        message,
                    ),
                    logger=logger,
                    description=f"HTTP callback {forward.url}",
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

    async def run(self, num_of_dialogs: int = 0):
        if self.user is None:
            await self.ensure_user()

        cfg = self.load_config(self.cfg_cls)
        if cfg.requires_ai:
            self.ensure_ai_cfg()

        self.app.add_handler(
            MessageHandler(self.on_message, filters.text & filters.chat(cfg.chat_ids)),
        )
        try:
            async with self.app:
                self.log("开始监控...")
                await idle()
        finally:
            trim_memory()


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
