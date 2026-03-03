import asyncio
import importlib.util
import logging
import os
import random
import re
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, Dict, Iterable, Literal, Optional

from pyrogram.types import Message

from tg_signer.config import HttpCallback, UDPForward
from tg_signer.core import UserMonitor
from tg_signer.notification.server_chan import sc_send

from .models import AutomationContext, Event

# 统一 handler 返回值语义：
# - continue: 继续执行后续 handler
# - stop/defer: 中断当前规则链
HandlerResult = Literal["continue", "stop", "defer"]
HandlerFn = Callable[
    [Event, AutomationContext, Dict[str, Any]], Awaitable[HandlerResult]
]

_REGISTRY: Dict[str, HandlerFn] = {}


class SafeFormatDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def render_template(text: Any, event: Event, ctx: AutomationContext) -> Any:
    if not isinstance(text, str):
        return text
    message = event.message or SimpleNamespace(text="", id=None, chat=None)
    mapping = SafeFormatDict()
    mapping.update(ctx.vars)
    mapping.update(
        {
            "chat_id": event.chat_id,
            "now": event.now,
            "message": message,
            "event": event,
        }
    )
    try:
        return text.format_map(mapping)
    except Exception:  # noqa: BLE001
        return text


def message_text(message: Any) -> str:
    if message is None:
        return ""
    return getattr(message, "text", None) or getattr(message, "caption", None) or ""


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def message_sender(message: Message) -> str:
    if message is None:
        return "unknown"
    from_user = message.from_user
    if from_user is not None:
        username = from_user.username
        if username:
            return f"@{username}"
        first_name = from_user.first_name or ""
        last_name = from_user.last_name or ""
        full_name = f"{first_name} {last_name}".strip()
        if full_name:
            return full_name
        user_id = from_user.id
        return str(user_id)
    sender_chat = message.sender_chat
    if sender_chat is not None:
        title = sender_chat.title or sender_chat.username
        if title:
            return str(title)
    return "unknown"


async def resolve_ai_input(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> str:
    # 显式 input 优先；若未提供，再根据 recent_limit 动态拼装上下文。
    input_text = params.get("input")
    if input_text is not None:
        return str(render_template(input_text, event, ctx))

    recent_limit = params.get("recent_limit", params.get("recent_messages"))
    if recent_limit is None:
        return message_text(event.message)
    try:
        recent_limit = int(recent_limit)
    except (TypeError, ValueError):
        recent_limit = 0
    if recent_limit <= 0:
        return message_text(event.message)

    history_chat_id = (
        params.get("history_chat_id") or params.get("chat_id") or event.chat_id
    )
    if history_chat_id is None:
        ctx.log(
            "ai_reply: 缺少history_chat_id/chat_id，无法读取历史消息", level="WARNING"
        )
        return message_text(event.message)

    lines: list[str] = []
    try:
        # get_chat_history 通常返回新->旧，后续 reverse 成旧->新。
        async for msg in ctx.client.get_chat_history(
            history_chat_id, limit=recent_limit
        ):
            text = message_text(msg).strip()
            if not text:
                continue
            lines.append(f"[{message_sender(msg)}] {text}")
    except Exception as exc:  # noqa: BLE001
        ctx.log(f"ai_reply: 读取历史消息失败 ({exc})", level="WARNING")
        return message_text(event.message)

    lines.reverse()
    if as_bool(params.get("include_current", False)):
        current_text = message_text(event.message).strip()
        if current_text:
            current_line = f"[current] {current_text}"
            if not lines or lines[-1] != current_line:
                lines.append(current_line)
    if not lines:
        return message_text(event.message)

    separator = params.get("history_separator")
    if separator is None:
        separator = "\n"
    return str(separator).join(lines)


def resolve_blacklist_text(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> str:
    # 按优先级取过滤文本：text > source_var/source_vars > 当前消息。
    source_text = params.get("text")
    if source_text is not None:
        return str(render_template(source_text, event, ctx))

    source_var = params.get("source_var")
    if source_var:
        return str(ctx.vars.get(source_var, "") or "")

    source_vars = params.get("source_vars")
    if isinstance(source_vars, list):
        values = [str(ctx.vars.get(name)) for name in source_vars if ctx.vars.get(name)]
        return "\n".join(values)

    return message_text(event.message)


def register(name: str, fn: HandlerFn) -> None:
    _REGISTRY[name] = fn


def get_handler(name: str) -> Optional[HandlerFn]:
    return _REGISTRY.get(name)


def list_handlers() -> Iterable[str]:
    return sorted(_REGISTRY.keys())


def load_plugins(handlers_dir: Path, logger: logging.Logger) -> None:
    if not handlers_dir.is_dir():
        logger.debug("插件目录不存在，跳过加载: %s", handlers_dir)
        return
    loaded_modules = 0
    registered_handlers = 0
    for path in sorted(handlers_dir.glob("*.py")):
        module_name = f"tg_signer_user_handlers_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                logger.warning(f"无法加载插件: {path}")
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            loaded_modules += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"插件加载失败: {path} ({exc})")
            continue
        handlers = getattr(module, "HANDLERS", None)
        if not isinstance(handlers, dict):
            logger.warning(f"插件未提供HANDLERS: {path}")
            continue
        for name, fn in handlers.items():
            if name in _REGISTRY:
                logger.warning(f"插件handler与内置冲突，跳过: {name}")
                continue
            if not callable(fn):
                logger.warning(f"插件handler不可调用，跳过: {name}")
                continue
            _REGISTRY[name] = fn
            registered_handlers += 1
            logger.debug("插件 handler 注册成功: %s (%s)", name, path.name)
    logger.info(
        "插件加载完成: dir=%s, modules=%s, handlers=%s",
        handlers_dir,
        loaded_modules,
        registered_handlers,
    )


async def send_text(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    text = params.get("text") or ""
    if not text:
        ctx.log("send_text: 空文本", level="WARNING")
        return "stop"
    chat_id = params.get("chat_id") or event.chat_id
    if chat_id is None:
        ctx.log("send_text: 缺少chat_id", level="WARNING")
        return "stop"
    text = render_template(text, event, ctx)
    delete_after = params.get("delete_after")
    reply_to_message_id = params.get("reply_to_message_id")
    ctx.log(
        f"send_text: chat_id={chat_id}, delete_after={delete_after}, reply_to={reply_to_message_id}",
        level="DEBUG",
    )
    await ctx.worker.send_message(
        chat_id,
        text,
        delete_after=delete_after,
        reply_to_message_id=reply_to_message_id,
    )
    return "continue"


async def reply_text(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    text = params.get("text") or ""
    if not text:
        ctx.log("reply_text: 空文本", level="WARNING")
        return "stop"
    chat_id = params.get("chat_id") or event.chat_id
    if chat_id is None:
        ctx.log("reply_text: 缺少chat_id", level="WARNING")
        return "stop"
    reply_to_message_id = params.get("reply_to_message_id")
    if reply_to_message_id is None and event.message:
        reply_to_message_id = event.message.id
    if reply_to_message_id is None:
        ctx.log("reply_text: 缺少reply_to_message_id", level="WARNING")
        return "stop"
    text = render_template(text, event, ctx)
    delete_after = params.get("delete_after")
    ctx.log(
        f"reply_text: chat_id={chat_id}, reply_to={reply_to_message_id}, delete_after={delete_after}",
        level="DEBUG",
    )
    await ctx.worker.send_message(
        chat_id,
        text,
        delete_after=delete_after,
        reply_to_message_id=reply_to_message_id,
    )
    return "continue"


async def extract_regex(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    pattern = params.get("pattern") or params.get("regex")
    if not pattern:
        ctx.log("extract_regex: 缺少pattern", level="WARNING")
        return "stop"
    text = params.get("text")
    if text is None:
        text = message_text(event.message)
    flags = re.IGNORECASE if params.get("ignore_case", True) else 0
    match = re.search(pattern, text, flags=flags)
    if not match:
        ctx.log("extract_regex: 未匹配到结果", level="DEBUG")
        return "continue"
    group = params.get("group", 1)
    var = params.get("var")
    try:
        value = match.group(group)
    except Exception:  # noqa: BLE001
        value = match.group(0)
    if not var:
        var = str(group)
    ctx.vars[var] = value
    ctx.log(f"extract_regex: 写入变量 {var}={value}", level="DEBUG")
    return "continue"


async def ai_reply(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    prompt = params.get("prompt")
    if not prompt:
        ctx.log("ai_reply: 缺少prompt", level="WARNING")
        return "stop"
    prompt = str(render_template(prompt, event, ctx))
    text = await resolve_ai_input(event, ctx, params)
    reply_to_message_id = params.get("reply_to_message_id")
    if reply_to_message_id is None and event.message:
        reply_to_message_id = event.message.id
    ctx.log(
        f"ai_reply: 调用模型, prompt_len={len(prompt)}, input_len={len(text)}",
        level="DEBUG",
    )
    result = await ctx.worker.get_ai_tools().get_reply(prompt, text)
    store_var = params.get("store_var") or params.get("output_var")
    if store_var:
        # store_var/output_var 语义：只写变量，不直接发送。
        ctx.vars[store_var] = result
        ctx.log(f"ai_reply: 已写入变量 {store_var}", level="DEBUG")
        return "continue"
    chat_id = params.get("chat_id") or event.chat_id
    if chat_id is None:
        ctx.log("ai_reply: 缺少chat_id", level="WARNING")
        return "stop"
    delete_after = params.get("delete_after")
    ctx.log(
        f"ai_reply: 发送回复 chat_id={chat_id}, reply_to={reply_to_message_id}",
        level="DEBUG",
    )
    await ctx.worker.send_message(
        chat_id,
        result,
        delete_after=delete_after,
        reply_to_message_id=reply_to_message_id,
    )
    return "continue"


async def blacklist_filter(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    text = resolve_blacklist_text(event, ctx, params)
    ignore_case = as_bool(params.get("ignore_case", False))
    matched_text = text.lower() if ignore_case else text
    keywords = params.get("keywords") or []
    for kw in keywords:
        if not kw:
            continue
        needle = kw.lower() if ignore_case else kw
        if needle in matched_text:
            ctx.log(f"blacklist_filter: 关键词命中 {kw}", level="DEBUG")
            return "stop"
    regex = params.get("regex")
    if regex:
        try:
            flags = re.IGNORECASE if ignore_case else 0
            if re.search(regex, text, flags=flags):
                ctx.log("blacklist_filter: regex 命中", level="DEBUG")
                return "stop"
        except re.error:
            ctx.log("blacklist_filter: regex无效", level="WARNING")
    return "continue"


async def delay(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    _ = event
    seconds = params.get("seconds")
    if seconds is None:
        seconds = params.get("delay_seconds", 0)
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        seconds = 0
    if seconds > 0:
        ctx.log(f"delay: sleep {seconds}s", level="DEBUG")
        await asyncio.sleep(seconds)
    return "continue"


async def forward(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    if not event.message:
        ctx.log("forward: 缺少message", level="WARNING")
        return "stop"
    to_chat_id = params.get("chat_id") or params.get("to_chat_id")
    if to_chat_id is None:
        ctx.log("forward: 缺少chat_id", level="WARNING")
        return "stop"
    from_chat_id = params.get("from_chat_id") or event.chat_id
    message_id = params.get("message_id") or event.message.id
    ctx.log(
        f"forward: from={from_chat_id}, to={to_chat_id}, message_id={message_id}",
        level="DEBUG",
    )
    await ctx.client.forward_messages(
        to_chat_id,
        from_chat_id,
        message_id,
    )
    return "continue"


async def external_forward(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    if not event.message:
        ctx.log("external_forward: 缺少message", level="WARNING")
        return "stop"
    targets = params.get("targets") or []
    success_count = 0
    for target in targets:
        if not isinstance(target, dict):
            continue
        t_type = target.get("type")
        if t_type == "udp":
            try:
                cfg = UDPForward.model_validate(target)
            except Exception:  # noqa: BLE001
                ctx.log("external_forward: UDP配置无效", level="WARNING")
                continue
            await UserMonitor.udp_forward(cfg, event.message)
            success_count += 1
        elif t_type == "http":
            try:
                cfg = HttpCallback.model_validate(target)
            except Exception:  # noqa: BLE001
                ctx.log("external_forward: HTTP配置无效", level="WARNING")
                continue
            await UserMonitor.http_api_callback(cfg, event.message)
            success_count += 1
        else:
            ctx.log(f"external_forward: 未知目标类型 {t_type}", level="DEBUG")
    ctx.log(f"external_forward: 转发完成 success={success_count}", level="DEBUG")
    return "continue"


async def server_chan(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    send_key = params.get("send_key") or os.environ.get("SERVER_CHAN_SEND_KEY")
    if not send_key:
        ctx.log("server_chan: 未配置SendKey", level="WARNING")
        return "stop"
    title = params.get("title") or "Automation"
    body = params.get("body")
    if body is None:
        body = message_text(event.message)
    title = render_template(title, event, ctx)
    body = render_template(body, event, ctx)
    ctx.log(
        f"server_chan: 发送通知 title={str(title)[:32]}",
        level="DEBUG",
    )
    await sc_send(send_key, title, body)
    return "continue"


async def schedule_next(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    # 支持 trigger_id / target_trigger_id 两种命名，默认回落为当前触发器。
    target_trigger_id = (
        params.get("trigger_id") or params.get("target_trigger_id") or event.trigger_id
    )
    # 先解析基础 delay，再叠加 offset，最终写入 next_run_at。
    delay_seconds = params.get("delay_seconds")
    if delay_seconds is None:
        delay_minutes = params.get("delay_minutes")
        try:
            delay_seconds = float(delay_minutes or 0) * 60
        except (TypeError, ValueError):
            delay_seconds = 0
    from_var = params.get("from_var")
    if from_var:
        try:
            value = float(ctx.vars.get(from_var, delay_seconds))
            unit = str(params.get("from_var_unit") or "").lower().strip()
            if not unit and as_bool(params.get("from_var_minutes", False)):
                unit = "minutes"
            if unit in {"minute", "minutes", "min", "m"}:
                delay_seconds = value * 60
            else:
                delay_seconds = value
        except (TypeError, ValueError):
            pass
    offset_seconds = params.get("offset_seconds")
    if offset_seconds is None:
        offset_minutes = params.get("offset_minutes")
        try:
            offset_seconds = float(offset_minutes or 0) * 60
        except (TypeError, ValueError):
            offset_seconds = 0
    try:
        total_seconds = float(delay_seconds) + float(offset_seconds)
    except (TypeError, ValueError):
        total_seconds = 0
    next_at = event.now + timedelta(seconds=total_seconds) if total_seconds else None
    if total_seconds and next_at:
        ctx.state.set_trigger_next_run(event.rule_id, target_trigger_id, next_at)
        ctx.log(
            f"schedule_next: rule={event.rule_id}, trigger={target_trigger_id}, next={next_at.isoformat()}",
            level="DEBUG",
        )
    else:
        ctx.log(
            f"schedule_next: 未写入 next_run_at, total_seconds={total_seconds}",
            level="DEBUG",
        )
    return "continue"


async def store_state(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    keys = params.get("keys")
    if keys:
        stored = {k: ctx.vars.get(k) for k in keys}
    else:
        stored = dict(ctx.vars)
    ctx.state.set_rule_vars(event.rule_id, stored)
    ctx.log(
        f"store_state: rule={event.rule_id}, keys={list(stored.keys())}",
        level="DEBUG",
    )
    return "continue"


async def load_state(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    _ = params
    stored = ctx.state.get_rule_vars(event.rule_id)
    if stored:
        ctx.vars.update(stored)
        ctx.log(
            f"load_state: rule={event.rule_id}, keys={list(stored.keys())}",
            level="DEBUG",
        )
    else:
        ctx.log(f"load_state: rule={event.rule_id}, 无持久化变量", level="DEBUG")
    return "continue"


async def random_pick(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    choices = params.get("choices") or []
    if not choices:
        ctx.log("random_pick: 缺少choices", level="WARNING")
        return "stop"
    chosen = random.choice(list(choices))
    var = params.get("var")
    if var:
        ctx.vars[var] = chosen
        ctx.log(f"random_pick: 变量模式 {var}={chosen}", level="DEBUG")
        return "continue"
    chat_id = params.get("chat_id") or event.chat_id
    if chat_id is None:
        ctx.log("random_pick: 缺少chat_id", level="WARNING")
        return "stop"
    rendered = render_template(str(chosen), event, ctx)
    ctx.log(f"random_pick: 发送模式 chat_id={chat_id}, value={rendered}", level="DEBUG")
    await ctx.worker.send_message(chat_id, rendered)
    return "continue"


def register_builtin_handlers() -> None:
    register("send_text", send_text)
    register("reply_text", reply_text)
    register("extract_regex", extract_regex)
    register("ai_reply", ai_reply)
    register("blacklist_filter", blacklist_filter)
    register("delay", delay)
    register("forward", forward)
    register("external_forward", external_forward)
    register("server_chan", server_chan)
    register("schedule_next", schedule_next)
    register("store_state", store_state)
    register("load_state", load_state)
    register("random_pick", random_pick)
