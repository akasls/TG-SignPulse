from __future__ import annotations

import asyncio
import logging
import os
import re
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


def _parse_chat_id(value: Any) -> Union[int, str, None]:
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


def _parse_keywords(value: Any) -> List[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = re.split(r"[\n,，]+", str(value or ""))
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


class KeywordMonitorService:
    def __init__(self) -> None:
        self._client = None
        self._handler_ref = None
        self._active_key = ""
        self._lock = asyncio.Lock()

    def _settings_key(self, cfg: Dict[str, Any]) -> str:
        fields = [
            "keyword_monitor_enabled",
            "keyword_monitor_account_name",
            "keyword_monitor_chat_id",
            "keyword_monitor_message_thread_id",
            "keyword_monitor_keywords",
            "keyword_monitor_match_mode",
            "keyword_monitor_ignore_case",
            "keyword_monitor_push_channel",
            "keyword_monitor_bark_url",
            "keyword_monitor_custom_url",
            "telegram_bot_token",
            "telegram_bot_chat_id",
            "telegram_bot_message_thread_id",
        ]
        return repr({field: cfg.get(field) for field in fields})

    def _match_keyword(self, cfg: Dict[str, Any], text: str) -> Optional[str]:
        keywords = _parse_keywords(cfg.get("keyword_monitor_keywords"))
        if not keywords or not text:
            return None

        mode = (cfg.get("keyword_monitor_match_mode") or "contains").strip()
        ignore_case = bool(cfg.get("keyword_monitor_ignore_case", True))
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

    async def _on_message(self, _, message: Message) -> None:
        try:
            from backend.services.config import get_config_service

            cfg = get_config_service().get_global_settings()
            if not cfg.get("keyword_monitor_enabled"):
                return

            target_thread_id = cfg.get("keyword_monitor_message_thread_id")
            if target_thread_id is not None and str(target_thread_id).strip():
                message_thread_id = getattr(message, "message_thread_id", None) or getattr(
                    message, "reply_to_top_message_id", None
                )
                if int(target_thread_id) != int(message_thread_id or 0):
                    return

            text = _message_text(message)
            matched = self._match_keyword(cfg, text)
            if not matched:
                return

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

            body_lines = [
                f"群组: {chat_title}",
                f"关键词: {matched}",
            ]
            if sender:
                body_lines.append(f"发送者: {sender}")
            body_lines.append("")
            body_lines.append(text)

            await send_keyword_push(
                cfg,
                {
                    "title": "TG-SignPulse 关键词命中",
                    "body": "\n".join(body_lines),
                    "text": text,
                    "keyword": matched,
                    "chat_id": getattr(message.chat, "id", None),
                    "chat_title": chat_title,
                    "sender": sender,
                    "message_id": message.id,
                    "url": url,
                },
            )
        except Exception as exc:
            logger.warning("Keyword monitor handling failed: %s", exc, exc_info=True)

    async def restart_from_settings(self) -> None:
        async with self._lock:
            from backend.services.config import get_config_service
            from tg_signer.core import get_client

            cfg = get_config_service().get_global_settings()
            key = self._settings_key(cfg)
            if key == self._active_key:
                return

            await self.stop()

            if not cfg.get("keyword_monitor_enabled"):
                self._active_key = key
                return

            account_name = (cfg.get("keyword_monitor_account_name") or "").strip()
            chat_id = _parse_chat_id(cfg.get("keyword_monitor_chat_id"))
            if not account_name or chat_id is None or not _parse_keywords(
                cfg.get("keyword_monitor_keywords")
            ):
                logger.warning("Keyword monitor is enabled but not fully configured")
                return

            proxy_value = get_account_proxy(account_name)
            if not proxy_value:
                proxy_value = (cfg.get("global_proxy") or "").strip() or None
            proxy = build_proxy_dict(proxy_value) if proxy_value else None

            session_mode = get_session_mode()
            session_string = None
            in_memory = False
            session_dir = settings.resolve_session_dir()
            if session_mode == "string":
                session_string = get_account_session_string(
                    account_name
                ) or load_session_string_file(session_dir, account_name)
                in_memory = bool(session_string)
                if not session_string:
                    logger.warning(
                        "Keyword monitor account %s has no session_string", account_name
                    )
                    return

            tg_config = get_config_service().get_telegram_config()
            api_id = os.getenv("TG_API_ID") or tg_config.get("api_id")
            api_hash = os.getenv("TG_API_HASH") or tg_config.get("api_hash")
            try:
                api_id = int(api_id) if api_id is not None else None
            except (TypeError, ValueError):
                api_id = None

            client = get_client(
                account_name,
                proxy=proxy,
                workdir=session_dir,
                session_string=session_string,
                in_memory=in_memory,
                api_id=api_id,
                api_hash=api_hash,
            )
            self._client = client
            self._handler_ref = client.add_handler(
                MessageHandler(
                    self._on_message,
                    filters.chat(chat_id) & (filters.text | filters.caption),
                )
            )

            lock = get_account_lock(account_name)
            async with lock:
                if not getattr(client, "is_connected", False):
                    await client.start()
            self._active_key = key
            logger.info("Keyword monitor started for %s in %s", account_name, chat_id)

    async def stop(self) -> None:
        if self._client is not None and self._handler_ref is not None:
            try:
                self._client.remove_handler(*self._handler_ref)
            except Exception:
                pass
        self._client = None
        self._handler_ref = None


_keyword_monitor_service: Optional[KeywordMonitorService] = None


def get_keyword_monitor_service() -> KeywordMonitorService:
    global _keyword_monitor_service
    if _keyword_monitor_service is None:
        _keyword_monitor_service = KeywordMonitorService()
    return _keyword_monitor_service
