from __future__ import annotations

import asyncio
import os
from typing import Callable, Optional

from backend.core.config import get_settings

settings = get_settings()


def _base_args(account_name: str) -> list[str]:
    return [
        "tg-signer",
        "--workdir",
        str(settings.resolve_workdir()),
        "--session_dir",
        str(settings.resolve_session_dir()),
        "--account",
        account_name,
    ]


async def async_run_task_cli(
    account_name: str,
    task_name: str,
    num_of_dialogs: int = 50,
    callback: Optional[Callable[[str], None]] = None,
) -> tuple[int, str, str]:
    """
    Asynchronously run a tg-signer sign task using CLI.
    Returns (returncode, stdout, stderr)
    """
    args = _base_args(account_name) + [
        "run",
        task_name,
        "--num-of-dialogs",
        str(num_of_dialogs),
    ]
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    if not env.get("TG_PROXY"):
        try:
            from backend.services.config import get_config_service

            global_proxy = get_config_service().get_global_settings().get("global_proxy")
            if isinstance(global_proxy, str) and global_proxy.strip():
                env["TG_PROXY"] = global_proxy.strip()
        except Exception:
            pass

    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,  # 合并 stdout 和 stderr 以便于即时按顺序捕获日志
        env=env,
    )

    full_output = []
    while True:
        line = await process.stdout.readline()
        if not line:
            break
        decoded_line = line.decode("utf-8", errors="replace").rstrip()
        if decoded_line:
            full_output.append(decoded_line)
            if callback:
                callback(decoded_line)

    await process.wait()

    return (
        process.returncode or 0,
        "\n".join(full_output),
        "",  # stderr 已经由于合并捕获到了 stdout 中
    )
