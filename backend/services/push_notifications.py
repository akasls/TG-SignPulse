from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger("backend.push_notifications")


def _as_int_or_none(value: Any) -> Optional[int]:
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


async def send_telegram_bot_message(
    *,
    bot_token: str,
    chat_id: str,
    text: str,
    message_thread_id: Optional[int] = None,
) -> None:
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": text[:3900],
        "disable_web_page_preview": False,
    }
    if message_thread_id is not None:
        payload["message_thread_id"] = message_thread_id

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json=payload,
        )
        response.raise_for_status()


async def send_keyword_push(settings: Dict[str, Any], payload: Dict[str, Any]) -> None:
    channel = (settings.get("keyword_monitor_push_channel") or "telegram").strip()
    title = str(payload.get("title") or "TG-SignPulse 关键词命中")
    body = str(payload.get("body") or "")
    url = str(payload.get("url") or "")

    if channel == "telegram":
        bot_token = (settings.get("telegram_bot_token") or "").strip()
        chat_id = (settings.get("telegram_bot_chat_id") or "").strip()
        if not bot_token or not chat_id:
            logger.warning("Keyword monitor Telegram notification is not configured")
            return
        text = f"{title}\n\n{body}"
        if url:
            text += f"\n\n链接: {url}"
        await send_telegram_bot_message(
            bot_token=bot_token,
            chat_id=chat_id,
            text=text,
            message_thread_id=_as_int_or_none(
                settings.get("telegram_bot_message_thread_id")
            ),
        )
        return

    if channel == "bark":
        bark_url = (settings.get("keyword_monitor_bark_url") or "").strip()
        if not bark_url:
            logger.warning("Keyword monitor Bark URL is not configured")
            return
        data = {"title": title, "body": body}
        if url:
            data["url"] = url
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(bark_url, json=data)
            response.raise_for_status()
        return

    custom_url = (settings.get("keyword_monitor_custom_url") or "").strip()
    if not custom_url:
        logger.warning("Keyword monitor custom push URL is not configured")
        return

    request_payload = dict(payload)
    request_payload["title"] = title
    request_payload["body"] = body
    request_payload["url"] = url

    if any(token in custom_url for token in ("{title}", "{body}", "{url}")):
        final_url = (
            custom_url.replace("{title}", quote(title))
            .replace("{body}", quote(body))
            .replace("{url}", quote(url))
        )
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(final_url)
            response.raise_for_status()
        return

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(custom_url, json=request_payload)
        response.raise_for_status()
