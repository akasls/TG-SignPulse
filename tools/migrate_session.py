from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from pyrogram import Client

from backend.core.config import get_settings
from backend.services.config import config_service
from backend.utils.tg_session import save_session_string_file, set_account_session_string


def _resolve_api_credentials() -> tuple[int | None, str | None]:
    tg_config = config_service.get_telegram_config()
    api_id = os.getenv("TG_API_ID") or tg_config.get("api_id")
    api_hash = os.getenv("TG_API_HASH") or tg_config.get("api_hash")

    try:
        api_id = int(api_id) if api_id is not None else None
    except (TypeError, ValueError):
        api_id = None

    if isinstance(api_hash, str):
        api_hash = api_hash.strip()

    return api_id, api_hash


async def _export_session_string(
    account_name: str, session_dir: Path, api_id: int, api_hash: str
) -> str | None:
    session_path = str(session_dir / account_name)
    client = Client(
        name=session_path,
        api_id=api_id,
        api_hash=api_hash,
        in_memory=False,
        no_updates=True,
    )
    try:
        await client.connect()
        return await client.export_session_string()
    except Exception:
        return None
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def _run_migration(session_dir: Path, accounts: list[str]) -> int:
    api_id, api_hash = _resolve_api_credentials()
    if not api_id or not api_hash:
        print("Missing Telegram API ID or API Hash. Aborting.")
        return 2

    failures = 0
    for account_name in accounts:
        session_file = session_dir / f"{account_name}.session"
        if not session_file.exists():
            print(f"[SKIP] {account_name}: session file not found")
            failures += 1
            continue

        session_string = await _export_session_string(
            account_name, session_dir, api_id, api_hash
        )
        if not session_string:
            print(f"[FAIL] {account_name}: export_session_string failed")
            failures += 1
            continue

        set_account_session_string(account_name, session_string)
        save_session_string_file(session_dir, account_name, session_string)
        print(f"[OK] {account_name}: session_string saved")

    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export Pyrogram .session files into session_string storage"
    )
    parser.add_argument(
        "--session-dir",
        dest="session_dir",
        default=None,
        help="Session directory (default: APP_DATA_DIR/sessions)",
    )
    parser.add_argument(
        "--account",
        dest="account",
        default=None,
        help="Only migrate a single account name",
    )
    args = parser.parse_args()

    if args.session_dir:
        session_dir = Path(args.session_dir)
    else:
        settings = get_settings()
        session_dir = settings.resolve_session_dir()

    session_dir.mkdir(parents=True, exist_ok=True)

    if args.account:
        accounts = [args.account]
    else:
        accounts = [p.stem for p in session_dir.glob("*.session")]

    if not accounts:
        print("No session files found.")
        return 1

    return asyncio.run(_run_migration(session_dir, accounts))


if __name__ == "__main__":
    raise SystemExit(main())
