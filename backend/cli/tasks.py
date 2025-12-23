from __future__ import annotations

import subprocess
from typing import Optional

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


def run_task_cli(
    account_name: str,
    task_name: str,
    num_of_dialogs: int = 50,
) -> subprocess.CompletedProcess:
    """
    Run a tg-signer sign task using CLI:
    tg-signer --workdir ... --session_dir ... --account <account_name> run <task_name>
    """
    args = _base_args(account_name) + [
        "run",
        task_name,
        "--num-of-dialogs",
        str(num_of_dialogs),
    ]
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
    )



