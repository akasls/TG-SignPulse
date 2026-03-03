import asyncio
import json
import logging
import random
import re
from collections import OrderedDict, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Union

from croniter import CroniterBadCronError, croniter
from pyrogram import filters
from pyrogram.handlers import EditedMessageHandler, MessageHandler
from pyrogram.methods.utilities.idle import idle
from pyrogram.types import Message

from tg_signer.config import (
    AutomationConfig,
    FilterConfig,
    HandlerConfig,
    MessageTriggerConfig,
    RuleConfig,
    TimerTriggerConfig,
    TriggerConfig,
)
from tg_signer.core import BaseUserWorker, get_now

from .handlers import (
    get_handler,
    list_handlers,
    load_plugins,
    register_builtin_handlers,
)
from .models import AutomationContext, Event, RuleStateStore

logger = logging.getLogger("tg-signer")


class UserAutomation(BaseUserWorker[AutomationConfig]):
    """规则驱动的自动化执行器。

    核心流程：
    1) 载入规则配置；
    2) 监听消息事件 + 启动定时循环；
    3) 按规则触发并串行执行 handler 链。
    """

    _workdir = ".signer"
    _tasks_dir = "automations"
    cfg_cls = AutomationConfig

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state = RuleStateStore(self.state_file, logger)
        self._tick_seconds = 1.0
        # 按 chat_id -> message_id 缓存最近消息，供后续 wait_for/复杂 handler 复用。
        self._message_cache: dict[int, OrderedDict[int, Message]] = defaultdict(
            OrderedDict
        )
        self._message_cache_limit = 200

    def ensure_ctx(self):
        return {}

    @property
    def state_file(self) -> Path:
        return self.task_dir / "state.json"

    @property
    def handlers_dir(self) -> Path:
        return self.workdir / "handlers"

    def _config_candidates(self) -> List[Path]:
        # JSON 优先，其次 YAML，符合当前产品决策。
        return [
            self.task_dir / "config.json",
            self.task_dir / "config.yaml",
            self.task_dir / "config.yml",
        ]

    def _resolve_config_file(self) -> Path:
        # 返回第一个存在的配置文件；若都不存在，则返回默认 JSON 路径。
        for path in self._config_candidates():
            if path.exists():
                return path
        return self._config_candidates()[0]

    def _read_config_payload(self, path: Path) -> Dict[str, object]:
        if path.suffix in {".yml", ".yaml"}:
            try:
                import yaml  # type: ignore
            except ModuleNotFoundError as exc:
                raise ValueError("未安装pyyaml，无法读取YAML配置") from exc
            with open(path, "r", encoding="utf-8") as fp:
                payload = yaml.safe_load(fp) or {}
            if not isinstance(payload, dict):
                raise ValueError("YAML配置必须是字典结构")
            return payload
        with open(path, "r", encoding="utf-8") as fp:
            return json.load(fp)

    def load_config(
        self, cfg_cls: Optional[type[AutomationConfig]] = None
    ) -> AutomationConfig:  # type: ignore[override]
        cfg_cls = cfg_cls or self.cfg_cls
        config_path = self._resolve_config_file()
        self.log(f"读取自动化配置: {config_path}", level="DEBUG")
        if not config_path.exists():
            self.log("配置文件不存在，生成模板配置", level="INFO")
            config = self.reconfig()
        else:
            payload = self._read_config_payload(config_path)
            loaded = cfg_cls.load(payload)
            if loaded is None:
                raise ValueError(f"无法解析配置: {config_path}")
            config, from_old = loaded
            if config_path.suffix in {".yml", ".yaml"}:
                self.config = config
                self.log(
                    f"配置加载完成: rules={len(config.rules)} (yaml)", level="INFO"
                )
                return config
            if config_path.suffix == ".json" and from_old:
                self.write_config(config)
                self.log("检测到旧版配置并已自动迁移为当前结构", level="INFO")
        self.config = config
        self.log(f"配置加载完成: rules={len(config.rules)}", level="INFO")
        return config

    def export(self):  # type: ignore[override]
        config_path = self._resolve_config_file()
        if not config_path.exists():
            raise FileNotFoundError(f"配置不存在: {config_path}")
        with open(config_path, "r", encoding="utf-8") as fp:
            return fp.read()

    def ask_for_config(self) -> AutomationConfig:
        return self.template_config()

    def template_config(self) -> AutomationConfig:
        return AutomationConfig(
            rules=[
                RuleConfig(
                    id="demo_message_reply",
                    enabled=True,
                    triggers=[
                        MessageTriggerConfig(
                            type="message",
                            params={
                                "chat_id": "@channel_or_user",
                                "from_user_ids": None,
                                "reply_to_me": False,
                            },
                        )
                    ],
                    filters=FilterConfig(
                        text_rule="contains",
                        text_value="关键词",
                        ignore_case=True,
                    ),
                    handlers=[
                        HandlerConfig(
                            handler="send_text",
                            params={"text": "自动回复"},
                        )
                    ],
                    vars={},
                )
            ]
        )

    async def run(self, num_of_dialogs: int = 20):
        if self.user is None:
            await self.login(num_of_dialogs, print_chat=True)

        cfg = self.load_config(self.cfg_cls)
        if cfg.requires_ai:
            self.ensure_ai_cfg()

        register_builtin_handlers()
        load_plugins(self.handlers_dir, logger)
        self.log(f"已注册 handlers 数量: {len(list(list_handlers()))}", level="INFO")

        self.app.add_handler(MessageHandler(self.on_message, filters.all))
        self.app.add_handler(EditedMessageHandler(self.on_edited_message, filters.all))
        # startup trigger 每条规则只在进程启动后执行一次。
        startup_tasks = [
            asyncio.create_task(self.run_startup(rule))
            for rule in cfg.rules
            if rule.enabled and self._has_trigger(rule, "startup")
        ]
        self.log(f"startup 任务数: {len(startup_tasks)}", level="DEBUG")
        # timer trigger 统一由轮询调度循环驱动。
        timer_task = asyncio.create_task(self.timer_loop())
        async with self.app:
            self.log("开始自动化运行...")
            await idle()
        for task in startup_tasks:
            task.cancel()
        timer_task.cancel()

    def _has_trigger(self, rule: RuleConfig, trigger_type: str) -> bool:
        return any(trigger.type == trigger_type for trigger in rule.triggers)

    async def run_startup(self, rule: RuleConfig) -> None:
        for index, trigger in enumerate(rule.triggers):
            if trigger.type != "startup":
                continue
            trigger_params = trigger.params
            trigger_id = self._trigger_id(rule, trigger, index)
            self.log(
                f"执行 startup 触发: rule={rule.id}, trigger={trigger_id}",
                level="DEBUG",
            )
            event = Event(
                type="startup",
                chat_id=trigger_params.chat_id,
                message=None,
                now=get_now(),
                trigger_id=trigger_id,
                rule_id=rule.id,
            )
            await self._run_rule(rule, event)

    async def timer_loop(self) -> None:
        self.log(f"timer 轮询启动, tick={self._tick_seconds}s", level="DEBUG")
        while True:
            now = get_now()
            cfg = self.config
            for rule in cfg.rules:
                if not rule.enabled:
                    continue
                for index, trigger in enumerate(rule.triggers):
                    if trigger.type != "timer":
                        continue
                    timer_trigger = trigger
                    trigger_id = self._trigger_id(rule, trigger, index)
                    next_run = self.state.get_trigger_next_run(rule.id, trigger_id)
                    if next_run is None:
                        # 首次见到该 trigger，计算并写入 next_run_at。
                        next_run = self._compute_next_run(timer_trigger, now)
                        if next_run:
                            self.state.set_trigger_next_run(
                                rule.id, trigger_id, next_run
                            )
                            self.state.save()
                            self.log(
                                f"初始化 timer 下次执行: rule={rule.id}, trigger={trigger_id}, next={next_run.isoformat()}",
                                level="DEBUG",
                            )
                        else:
                            self.log(
                                f"timer 未配置 cron/interval: rule={rule.id}, trigger={trigger_id}",
                                level="DEBUG",
                            )
                        continue
                    if now >= next_run:
                        self.log(
                            f"触发 timer: rule={rule.id}, trigger={trigger_id}, due={next_run.isoformat()}",
                            level="DEBUG",
                        )
                        event = Event(
                            type="timer",
                            chat_id=timer_trigger.params.chat_id,
                            message=None,
                            now=now,
                            trigger_id=trigger_id,
                            rule_id=rule.id,
                        )
                        await self._run_rule(rule, event)
                        next_run = self.state.get_trigger_next_run(rule.id, trigger_id)
                        if not next_run or next_run <= now:
                            # 未被 schedule_next 覆盖时，按 trigger 默认策略推导下一次。
                            next_run = self._compute_next_run(timer_trigger, now)
                        self.state.set_trigger_next_run(rule.id, trigger_id, next_run)
                        self.state.set_trigger_last_run(rule.id, trigger_id, now)
                        self.state.save()
                        self.log(
                            f"timer 执行完成: rule={rule.id}, trigger={trigger_id}, next={next_run.isoformat() if next_run else 'None'}",
                            level="DEBUG",
                        )
            await asyncio.sleep(self._tick_seconds)

    async def on_message(self, client, message: Message):
        _ = client
        await self._handle_message_event(message, event_type="message")

    async def on_edited_message(self, client, message: Message):
        _ = client
        await self._handle_message_event(message, event_type="edited_message")

    async def _handle_message_event(self, message: Message, event_type: str) -> None:
        # 消息/编辑消息统一走“触发器匹配 -> 过滤器匹配 -> handler链”三段式流程。
        self._cache_message(message)
        cfg = self.config
        for rule in cfg.rules:
            if not rule.enabled:
                continue
            for index, trigger in enumerate(rule.triggers):
                if trigger.type != "message":
                    continue
                if not self._match_message_trigger(trigger, message):
                    continue
                if rule.filters and not self._match_filter(rule.filters, message):
                    continue
                trigger_id = self._trigger_id(rule, trigger, index)
                self.log(
                    f"{event_type}命中规则: rule={rule.id}, trigger={trigger_id}, chat={message.chat.id}",
                    level="DEBUG",
                )
                event = Event(
                    type=event_type,
                    chat_id=message.chat.id,
                    message=message,
                    now=get_now(),
                    trigger_id=trigger_id,
                    rule_id=rule.id,
                )
                await self._run_rule(rule, event)

    def _cache_message(self, message: Message) -> None:
        message_id = message.id
        chat_id = message.chat and message.chat.id
        if chat_id is None:
            return
        cache = self._message_cache[chat_id]
        cache[message_id] = message
        cache.move_to_end(message_id)
        while len(cache) > self._message_cache_limit:
            cache.popitem(last=False)
        self.log(
            f"消息已缓存: chat={chat_id}, message_id={message_id}, cached={len(cache)}",
            level="DEBUG",
        )

    def get_cached_messages(
        self, chat_id: int, limit: Optional[int] = None
    ) -> List[Message]:
        cache = self._message_cache.get(chat_id)
        if not cache:
            return []
        messages = list(cache.values())
        if limit is None or limit <= 0:
            return messages
        return messages[-limit:]

    def _trigger_id(self, rule: RuleConfig, trigger: TriggerConfig, index: int) -> str:
        return trigger.id or f"{rule.id}:{index}"

    def _compute_next_run(
        self, trigger: TimerTriggerConfig, now: datetime
    ) -> Optional[datetime]:
        # timer 支持 cron 或固定间隔，二选一。
        trigger_params = trigger.params
        if trigger_params.cron:
            try:
                it = croniter(trigger_params.cron, start_time=now)
                next_dt: datetime = it.next(ret_type=datetime)
            except CroniterBadCronError:
                self.log(f"cron表达式无效: {trigger_params.cron}", level="WARNING")
                return None
        elif trigger_params.interval_seconds:
            next_dt = now + timedelta(seconds=trigger_params.interval_seconds)
        else:
            return None
        if trigger_params.random_seconds:
            next_dt += timedelta(
                seconds=random.randint(0, trigger_params.random_seconds)
            )
        self.log(
            f"计算下次 timer: cron={trigger_params.cron}, interval={trigger_params.interval_seconds}, next={next_dt.isoformat()}",
            level="DEBUG",
        )
        return next_dt

    def _match_message_trigger(
        self, trigger: MessageTriggerConfig, message: Message
    ) -> bool:
        trigger_params = trigger.params
        if trigger_params.chat_id or trigger_params.chat_ids:
            if not self._match_chat(
                message, trigger_params.chat_id, trigger_params.chat_ids
            ):
                return False
        if trigger_params.from_user_ids:
            if not self._match_user(message, trigger_params.from_user_ids):
                return False
        if trigger_params.reply_to_me:
            if not message.reply_to_message:
                return False
            if not message.reply_to_message.from_user:
                return False
            if not message.reply_to_message.from_user.is_self:
                return False
        if trigger_params.reply_to_message_id:
            if not message.reply_to_message:
                return False
            if message.reply_to_message.id != trigger_params.reply_to_message_id:
                return False
        return True

    def _match_filter(self, filter_cfg: FilterConfig, message: Message) -> bool:
        if filter_cfg.chat_id or filter_cfg.chat_ids:
            if not self._match_chat(message, filter_cfg.chat_id, filter_cfg.chat_ids):
                return False
        if filter_cfg.from_user_ids:
            if not self._match_user(message, filter_cfg.from_user_ids):
                return False
        text = message.text or message.caption or ""
        rule = filter_cfg.text_rule
        value = filter_cfg.text_value or ""
        if rule != "all" and not value:
            return False
        if rule == "all":
            return True
        if rule == "exact":
            if filter_cfg.ignore_case:
                return text.lower() == value.lower()
            return text == value
        if rule == "contains":
            if filter_cfg.ignore_case:
                return value.lower() in text.lower()
            return value in text
        if rule == "regex":
            flags = 0 if not filter_cfg.ignore_case else re.IGNORECASE
            return re.search(value, text, flags=flags) is not None
        return False

    def _match_user(
        self, message: Message, from_user_ids: Iterable[Union[int, str]]
    ) -> bool:
        if not message.from_user:
            return True
        normalized = {
            self._normalize_user_id(item) for item in from_user_ids if item is not None
        }
        user_id = message.from_user.id
        username = message.from_user.username
        if user_id in normalized:
            return True
        if username and username.lower().strip("@") in normalized:
            return True
        if "me" in normalized and message.from_user.is_self:
            return True
        return False

    def _normalize_user_id(self, value: Union[int, str]) -> Union[int, str]:
        if isinstance(value, str):
            if value in {"me", "self"}:
                return "me"
            return value.lower().strip("@")
        return value

    def _match_chat(
        self,
        message: Message,
        chat_id: Optional[Union[int, str]],
        chat_ids: Optional[List[Union[int, str]]],
    ) -> bool:
        if chat_ids is None:
            chat_ids = []
        if chat_id is not None:
            chat_ids = list(chat_ids) + [chat_id]
        if not chat_ids:
            return True
        for target in chat_ids:
            if isinstance(target, int) and message.chat.id == target:
                return True
            if isinstance(target, str):
                target_norm = target.strip("@")
                if message.chat.username == target_norm:
                    return True
        return False

    async def _run_rule(self, rule: RuleConfig, event: Event) -> None:
        # 规则级变量 = 配置初始变量 + 持久化状态变量（后者覆盖前者）。
        ctx_vars = {**rule.vars, **self.state.get_rule_vars(rule.id)}
        self.log(
            f"开始执行规则: rule={rule.id}, trigger={event.trigger_id}, type={event.type}",
            level="DEBUG",
        )
        ctx = AutomationContext(
            vars=ctx_vars,
            state=self.state,
            client=self.app,
            logger=logger,
            worker=self,
            workdir=self.workdir,
        )
        for handler_cfg in rule.handlers:
            handler = get_handler(handler_cfg.handler)
            if not handler:
                self.log(f"未找到handler: {handler_cfg.handler}", level="WARNING")
                break
            try:
                self.log(
                    f"执行 handler: rule={rule.id}, handler={handler_cfg.handler}",
                    level="DEBUG",
                )
                result = await handler(event, ctx, handler_cfg.params or {})
                self.log(
                    f"handler 结果: rule={rule.id}, handler={handler_cfg.handler}, result={result}",
                    level="DEBUG",
                )
            except Exception as exc:  # noqa: BLE001
                self.log(
                    f"handler执行失败: {handler_cfg.handler} ({exc})", level="ERROR"
                )
                break
            if result in {"stop", "defer"}:
                # stop/defer 都会中断后续 handler。
                break
        self.state.set_rule_vars(rule.id, ctx.vars)
        self.state.save()
        self.log(
            f"规则执行结束并持久化变量: rule={rule.id}, keys={list(ctx.vars.keys())}",
            level="DEBUG",
        )
