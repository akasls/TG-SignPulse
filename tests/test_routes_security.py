import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.core.auth import create_access_token, get_current_user
from backend.core.database import get_db, Base, get_engine
from backend.models.user import User
from backend.models.task_log import TaskLog
from backend.core.security import hash_password
from backend.core.config import get_settings


@pytest.fixture
def client_with_user():
    # Setup test user
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    db_gen = get_db()
    db = next(db_gen)

    user = db.query(User).filter(User.username == "sec_test_user").first()
    if not user:
        user = User(
            username="sec_test_user",
            password_hash=hash_password("ValidPassword123!"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(data={"sub": user.username})

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    yield client, headers, user, db


def test_account_traversal_blocked(client_with_user):
    client, headers, user, db = client_with_user

    # Trying invalid names / reserved device names / illegal characters
    res = client.get("/api/accounts/con/avatar", headers=headers)
    assert res.status_code == 400

    res = client.delete("/api/accounts/..:evil", headers=headers)
    assert res.status_code == 400

    res = client.get("/api/accounts/invalid*name/exists", headers=headers)
    assert res.status_code == 400


def test_task_log_path_traversal_defense(client_with_user, monkeypatch, tmp_path):
    client, headers, user, db = client_with_user

    from backend.core.config import Settings

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Settings, "resolve_logs_dir", lambda self: logs_dir)

    # Valid log inside logs_dir
    valid_file = logs_dir / "task_1.log"
    valid_file.write_text("Valid log content", encoding="utf-8")

    # Outside secret file
    secret_file = tmp_path / "secret.env"
    secret_file.write_text("SECRET_KEY=leaked", encoding="utf-8")

    # DB log pointing outside
    malicious_log = TaskLog(
        task_id=1,
        status="success",
        log_path=str(secret_file),
    )
    db.add(malicious_log)
    db.commit()
    db.refresh(malicious_log)

    res = client.get(f"/api/tasks/logs/{malicious_log.id}/output", headers=headers)
    assert res.status_code == 403

    # DB log pointing inside
    safe_log = TaskLog(
        task_id=1,
        status="success",
        log_path=str(valid_file),
    )
    db.add(safe_log)
    db.commit()
    db.refresh(safe_log)

    res_safe = client.get(f"/api/tasks/logs/{safe_log.id}/output", headers=headers)
    assert res_safe.status_code == 200
    assert res_safe.json()["output"] == "Valid log content"


def test_totp_reset_requires_password(client_with_user):
    client, headers, user, db = client_with_user

    user.totp_secret = "JBSWY3DPEHPK3PXP"
    db.commit()

    # Attempt reset with wrong password
    res = client.post("/api/user/totp/reset", json={"password": "WrongPassword"}, headers=headers)
    assert res.status_code == 400
    assert res.json()["detail"] == "密码错误"

    # Attempt reset with correct password
    res = client.post("/api/user/totp/reset", json={"password": "ValidPassword123!"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["success"] is True

    db.refresh(user)
    assert user.totp_secret is None
