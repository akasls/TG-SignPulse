import re
from typing import Optional

from httpx import AsyncClient

_sc_client: Optional[AsyncClient] = None


def _get_sc_client() -> AsyncClient:
    global _sc_client
    if _sc_client is None or _sc_client.is_closed:
        _sc_client = AsyncClient(
            headers={"Content-Type": "application/json;charset=utf-8"},
            timeout=10,
        )
    return _sc_client


async def sc_send(sendkey, title, desp="", options=None):
    if options is None:
        options = {}
    # 判断 sendkey 是否以 'sctp' 开头，并提取数字构造 URL
    if sendkey.startswith("sctp"):
        match = re.match(r"sctp(\d+)t", sendkey)
        if match:
            num = match.group(1)
            url = f"https://{num}.push.ft07.com/send/{sendkey}.send"
        else:
            raise ValueError("Invalid sendkey format for sctp")
    else:
        url = f"https://sctapi.ftqq.com/{sendkey}.send"
    params = {"title": title, "desp": desp, **options}
    client = _get_sc_client()
    response = await client.post(url, json=params)
    return response.json()
