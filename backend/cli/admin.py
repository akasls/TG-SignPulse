from __future__ import annotations

import argparse
import sys
from typing import Optional


def reset_totp_cmd(username: str) -> bool:
    """Reset TOTP two-factor authentication for the specified username."""
    from sqlalchemy.orm import Session
    from backend.core.database import get_session_local, init_engine
    from backend.models.user import User

    init_engine()
    session_factory = get_session_local()
    db: Session = session_factory()
    try:
        user = db.query(User).filter(User.username == username.strip()).first()
        if not user:
            print(f"[ERROR] User '{username}' not found in database.", file=sys.stderr)
            return False

        had_totp = bool(user.totp_secret)
        user.totp_secret = None
        db.commit()

        if had_totp:
            print(f"[SUCCESS] 2FA/TOTP has been successfully disabled/reset for user '{username}'.")
        else:
            print(f"[INFO] User '{username}' did not have 2FA enabled.")
        return True
    except Exception as exc:
        db.rollback()
        print(f"[ERROR] Failed to reset TOTP: {exc}", file=sys.stderr)
        return False
    finally:
        db.close()


def reset_password_cmd(username: str, new_password: str) -> bool:
    """Reset password for the specified username."""
    if len(new_password) < 6:
        print("[ERROR] Password must be at least 6 characters long.", file=sys.stderr)
        return False

    from sqlalchemy.orm import Session
    from backend.core.database import get_session_local, init_engine
    from backend.core.security import hash_password
    from backend.models.user import User

    init_engine()
    session_factory = get_session_local()
    db: Session = session_factory()
    try:
        user = db.query(User).filter(User.username == username.strip()).first()
        if not user:
            print(f"[ERROR] User '{username}' not found in database.", file=sys.stderr)
            return False

        user.password_hash = hash_password(new_password)
        db.commit()
        print(f"[SUCCESS] Password for user '{username}' has been successfully updated.")
        return True
    except Exception as exc:
        db.rollback()
        print(f"[ERROR] Failed to reset password: {exc}", file=sys.stderr)
        return False
    finally:
        db.close()


def list_users_cmd() -> bool:
    """List all registered users and their 2FA status."""
    from sqlalchemy.orm import Session
    from backend.core.database import get_session_local, init_engine
    from backend.models.user import User

    init_engine()
    session_factory = get_session_local()
    db: Session = session_factory()
    try:
        users = db.query(User).all()
        if not users:
            print("[INFO] No users found in database.")
            return True

        print(f"{'ID':<6} {'Username':<24} {'2FA Enabled':<12}")
        print("-" * 46)
        for u in users:
            totp_status = "YES" if u.totp_secret else "NO"
            print(f"{u.id:<6} {u.username:<24} {totp_status:<12}")
        return True
    except Exception as exc:
        print(f"[ERROR] Failed to list users: {exc}", file=sys.stderr)
        return False
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m backend.cli",
        description="TG-SignPulse Server Administration CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # reset-totp
    totp_parser = subparsers.add_parser("reset-totp", help="Reset 2FA/TOTP for a user")
    totp_parser.add_argument("username", help="Username to reset 2FA for")

    # reset-password
    pwd_parser = subparsers.add_parser("reset-password", help="Reset password for a user")
    pwd_parser.add_argument("username", help="Username to update")
    pwd_parser.add_argument("password", help="New password (minimum 6 characters)")

    # list-users
    subparsers.add_parser("list-users", help="List all users and their 2FA status")

    args = parser.parse_args()
    if args.command == "reset-totp":
        success = reset_totp_cmd(args.username)
        sys.exit(0 if success else 1)
    elif args.command == "reset-password":
        success = reset_password_cmd(args.username, args.password)
        sys.exit(0 if success else 1)
    elif args.command == "list-users":
        success = list_users_cmd()
        sys.exit(0 if success else 1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
