from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from pyrogram import filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message

from backend.core.config import get_settings
from backend.services.push_notifications import send_keyword_push
from backend.utils.account_locks import get_account_lock
from backend.utils.proxy import build_proxy_dict
from backend.utils.tg_session import (
    get_account_proxy,
    get_account_session_string,
    get_session_mode,
    load_session_string_file,
)

logger = logging.getLogger("backend.keyword_monitor")
settings = get_settings()


@dataclass(frozen=True)
class KeywordMonitorRule:
    account_name: str
    task_name: str
    chat_id: int
    chat_name: str
    message_thread_id: Optional[int]
    action: Dict[str, Any]


def _parse_keywords(value: Any) -> List[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = re.split(r"[\n,]+", str(value or ""))
    return [str(item).strip() for item in raw_items if str(item).strip()]


def _message_text(message: Message) -> str:
    return (message.text or message.caption or "").strip()


def _message_url(message: Message) -> str:
    link = getattr(message, "link", None)
    if isinstance(link, str) and link:
        return link

    username = getattr(message.chat, "username", None)
    if username:
        return f"https://t.me/{username}/{message.id}"

    chat_id = getattr(message.chat, "id", None)
    if isinstance(chat_id, int):
        chat_id_text = str(chat_id)
        if chat_id_text.startswith("-100"):
            return f"https://t.me/c/{chat_id_text[4:]}/{message.id}"
    return ""


def _as_int_or_none(value: Any) -> Optional[int]:
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_forward_chat_id(value: Any) -> Optional[Union[int, str]]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("@"):
        return text
    try:
        return int(text)
    except ValueError:
        return text


class KeywordMonitorService:
    def __init__(self) -> None:
        self._handler_refs: list[tuple[Any, Any]] = []
        self._rules: list[KeywordMonitorRule] = []
        self._active_key = ""
        self._lock = asyncio.Lock()

    def _rules_key(self, rules: list[KeywordMonitorRule]) -> str:
        return repr(
            [
                {
                    "account_name": rule.account_name,
                    "task_name": rule.task_name,
                    "chat_id": rule.chat_id,
                    "message_thread_id": rule.message_thread_id,
                    "action": rule.action,
                }
                for rule in rules
            ]
        )

    def _load_rules(self) -> list[KeywordMonitorRule]:
        from backend.services.sign_tasks import get_sign_task_service

        rules: list[KeywordMonitorRule] = []
        tasks = get_sign_task_service().list_tasks(force_refresh=True)
        for task in tasks:
            account_name = str(task.get("account_name") or "").strip()
            task_name = str(task.get("name") or "").strip()
            if not account_name or not task_name or not task.get("enabled", True):
                continue
            for chat in task.get("chats") or []:
                chat_id = chat.get("chat_id")
                try:
                    chat_id_int = int(chat_id)
                except (TypeError, ValueError):
                    continue
                for action in chat.get("actions") or []:
                    try:
                        action_id = int(action.get("action"))
                    except (TypeError, ValueError, AttributeError):
                        continue
                    if action_id != 8 or not _parse_keywords(action.get("keywords")):
                        continue
                    rules.append(
                        KeywordMonitorRule(
                            account_name=account_name,
                            task_name=task_name,
                            chat_id=chat_id_int,
                            chat_name=str(chat.get("name") or chat_id_int),
                            message_thread_id=_as_int_or_none(
                                chat.get("message_thread_id")
                            ),
                            action=dict(action),
                        )
                    )
        return rules

    def _match_keyword(self, action: Dict[str, Any], text: str) -> Optional[str]:
        keywords = _parse_keywords(action.get("keywords"))
        if not keywords or not text:
            return None

        mode = (action.get("match_mode") or "contains").strip()
        ignore_case = bool(action.get("ignore_case", True))
        haystack = text.lower() if ignore_case else text

        for keyword in keywords:
            needle = keyword.lower() if ignore_case else keyword
            if mode == "exact" and haystack == needle:
                return keyword
            if mode == "regex":
                flags = re.IGNORECASE if ignore_case else 0
                try:
                    if re.search(keyword, text, flags=flags):
                        return keyword
                except re.error as exc:
                    logger.warning("Invalid keyword monitor regex %r: %s", keyword, exc)
                continue
            if mode not in {"exact", "regex"} and needle in haystack:
                return keyword
        return None

    def _message_thread_id(self, message: Message) -> Optional[int]:
        return _as_int_or_none(
            getattr(message, "message_thread_id", None)
            or getattr(message, "reply_to_top_message_id", None)
        )

    async def _on_message(self, account_name: str, client: Any, message: Message) -> None:
        try:
            from backend.services.config import get_config_service

            text = _message_text(message)
            if not text:
                return
            message_thread_id = self._message_thread_id(message)
            matched_rules = [
                rule
                for rule in self._rules
                if rule.account_name == account_name
                and rule.chat_id == message.chat.id
                and (
                    rule.message_thread_id is None
                    or rule.message_thread_id == message_thread_id
                )
            ]
            if not matched_rules:
                return

            global_settings = get_config_service().get_global_settings()
            url = _message_url(message)
            chat_title = (
                getattr(message.chat, "title", None)
                or getattr(message.chat, "username", None)
                or str(getattr(message.chat, "id", ""))
            )
            sender = ""
            if message.from_user:
                sender = (
                    message.from_user.username
                    or " ".join(
                        item
                        for item in [
                            message.from_user.first_name,
                            message.from_user.last_name,
                        ]
                        if item
                    )
                    or str(message.from_user.id)
                )

            for rule in matched_rules:
                matched = self._match_keyword(rule.action, text)
                if not matched:
                    continue
                body_lines = [
                    f"Task: {rule.task_name}",
                    f"Chat: {chat_title}",
                    f"Keyword: {matched}",
                ]
                if sender:
                    body_lines.append(f"Sender: {sender}")
                body_lines.append("")
                body_lines.append(text)
                forward_text = "\n".join(body_lines)

                forward_chat_id = _parse_forward_chat_id(
                    rule.action.get("forward_chat_id")
                )
                if forward_chat_id is not None:
                    try:
                        forward_kwargs: dict[str, Any] = {}
                        forward_thread_id = _as_int_or_none(
                            rule.action.get("forward_message_thread_id")
                        )
                        if forward_thread_id is not None:
                            forward_kwargs["message_thread_id"] = forward_thread_id
                        forward_payload = forward_text
                        if url:
                            forward_payload += f"\n\nLink: {url}"
                        await client.send_message(
                            forward_chat_id,
                            forward_payload[:3900],
                            **forward_kwargs,
                        )
                    except Exception as exc:
                        logger.warning(
                            "Failed to forward keyword match to %r: %s",
                            forward_chat_id,
                            exc,
                        )

                push_settings = dict(global_settings)
                push_settings["keyword_monitor_push_channel"] = rule.action.get(
                    "push_channel", "telegram"
                )
                push_settings["keyword_monitor_bark_url"] = rule.action.get("bark_url")
                push_settings["keyword_monitor_custom_url"] = rule.action.get(
                    "custom_url"
                )
                await send_keyword_push(
                    push_settings,
                    {
                        "title": "TG-SignPulse keyword matched",
                        "body": forward_text,
                        "text": text,
                        "keyword": matched,
                        "account_name": account_name,
                        "task_name": rule.task_name,
                        "chat_id": getattr(message.chat, "id", None),
                        "chat_title": chat_title,
                        "sender": sender,
                        "message_id": message.id,
                        "url": url,
                    },
                )
        except Exception as exc:
            logger.warning("Keyword monitor handling failed: %s", exc, exc_info=True)

    async def restart_from_tasks(self) -> None:
        async with self._lock:
            from backend.services.config import get_config_service
            from tg_signer.core import get_client

            rules = self._load_rules()
            key = self._rules_key(rules)
            if key == self._active_key:
                return

            await self.stop()
            self._rules = rules
            if not rules:
                self._active_key = key
                return

            session_dir = settings.resolve_session_dir()
            global_settings = get_config_service().get_global_settings()
            tg_config = get_config_service().get_telegram_config()
            api_id = os.getenv("TG_API_ID") or tg_config.get("api_id")
            api_hash = os.getenv("TG_API_HASH") or tg_config.get("api_hash")
            try:
                api_id = int(api_id) if api_id is not None else None
            except (TypeError, ValueError):
                api_id = None

            accounts = sorted({rule.account_name for rule in rules})
            for account_name in accounts:
                account_rules = [rule for rule in rules if rule.account_name == account_name]
                chat_ids = sorted({rule.chat_id for rule in account_rules})
                proxy_value = get_account_proxy(account_name)
                if not proxy_value:
                    proxy_value = (global_settings.get("global_proxy") or "").strip() or None
                proxy = build_proxy_dict(proxy_value) if proxy_value else None

                session_mode = get_session_mode()
                session_string = None
                in_memory = False
                if session_mode == "string":
                    session_string = get_account_session_string(
                        account_name
                    ) or load_session_string_file(session_dir, account_name)
                    in_memory = bool(session_string)
                    if not session_string:
                        logger.warning(
                            "Keyword monitor account %s has no session_string",
                            account_name,
                        )
                        continue

                client = get_client(
                    account_name,
                    proxy=proxy,
                    workdir=session_dir,
                    session_string=session_string,
                    in_memory=in_memory,
                    api_id=api_id,
                    api_hash=api_hash,
                )

                async def handler(client, message: Message, name: str = account_name) -> None:
                    await self._on_message(name, client, message)

                handler_ref = client.add_handler(
                    MessageHandler(
                        handler,
                        filters.chat(chat_ids) & (filters.text | filters.caption),
                    )
                )
                self._handler_refs.append((client, handler_ref))

                lock = get_account_lock(account_name)
                async with lock:
                    if not getattr(client, "is_connected", False):
                        await client.start()
                logger.info(
                    "Keyword monitor started for %s in %s", account_name, chat_ids
                )

            self._active_key = key

    async def stop(self) -> None:
        for client, handler_ref in self._handler_refs:
            try:
                client.remove_handler(*handler_ref)
            except Exception:
                pass
        self._handler_refs = []
        self._rules = []


_keyword_monitor_service: Optional[KeywordMonitorService] = None


def get_keyword_monitor_service() -> KeywordMonitorService:
    global _keyword_monitor_service
    if _keyword_monitor_service is None:
        _keyword_monitor_service = KeywordMonitorService()
    return _keyword_monitor_service
