from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.cli.signer import login_account
from backend.models.account import Account


def list_accounts(db: Session) -> list[Account]:
    return db.query(Account).order_by(Account.id.desc()).all()


def get_account(db: Session, account_id: int) -> Optional[Account]:
    return db.query(Account).filter(Account.id == account_id).first()


def create_account(
    db: Session,
    account_name: str,
    api_id: str,
    api_hash: str,
    proxy: Optional[str] = None,
) -> Account:
    obj = Account(
        account_name=account_name,
        api_id=api_id,
        api_hash=api_hash,
        proxy=proxy,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update_account(
    db: Session,
    account: Account,
    api_id: Optional[str] = None,
    api_hash: Optional[str] = None,
    proxy: Optional[str] = None,
    status: Optional[str] = None,
) -> Account:
    if api_id is not None:
        account.api_id = api_id
    if api_hash is not None:
        account.api_hash = api_hash
    if proxy is not None:
        account.proxy = proxy
    if status is not None:
        account.status = status
    db.commit()
    db.refresh(account)
    return account


def delete_account(db: Session, account: Account) -> None:
    db.delete(account)
    db.commit()


def start_login(db: Session, account: Account) -> dict:
    account.status = "logging_in"
    db.commit()
    db.refresh(account)
    result = login_account(account.account_name)
    return {
        "account_id": account.id,
        "status": "pending_code",
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }


def verify_login(
    db: Session,
    account: Account,
    code: Optional[str],
    password: Optional[str] = None,
) -> dict:
    result = login_account(account.account_name, code=code, password=password)
    account.status = "ready" if result.returncode == 0 else "error"
    account.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(account)
    return {
        "account_id": account.id,
        "status": account.status,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }


