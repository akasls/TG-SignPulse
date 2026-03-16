import json
import sqlite3

from tg_signer.sign_record_store import SignRecordStore


def test_sign_record_store_upsert_and_list_groups(tmp_path):
    workdir = tmp_path / ".signer"
    store = SignRecordStore(workdir)

    store.upsert_record(
        "linuxdo",
        "123456",
        "2026-03-17",
        "2026-03-17T06:00:00+08:00",
        account="acct",
    )
    store.upsert_record(
        "linuxdo",
        "123456",
        "2026-03-18",
        "2026-03-18T06:00:00+08:00",
        account="acct",
    )

    assert store.db_path.is_file()
    assert store.load_records("linuxdo", "123456") == {
        "2026-03-17": "2026-03-17T06:00:00+08:00",
        "2026-03-18": "2026-03-18T06:00:00+08:00",
    }

    groups = store.list_record_groups()
    assert len(groups) == 1
    assert groups[0].task_name == "linuxdo"
    assert groups[0].user_id == "123456"
    assert groups[0].records == [
        ("2026-03-18", "2026-03-18T06:00:00+08:00"),
        ("2026-03-17", "2026-03-17T06:00:00+08:00"),
    ]


def test_sign_record_store_runs_explicit_schema_migrations(tmp_path):
    workdir = tmp_path / ".signer"
    workdir.mkdir(parents=True, exist_ok=True)
    db_path = workdir / "data.sqlite3"

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA user_version = 0")
        conn.commit()

    store = SignRecordStore(workdir)
    store.upsert_record(
        "linuxdo",
        "123456",
        "2026-03-17",
        "2026-03-17T06:00:00+08:00",
    )

    with sqlite3.connect(db_path) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        count = conn.execute("SELECT COUNT(*) FROM sign_records").fetchone()[0]

    assert version == store.SCHEMA_VERSION
    assert count == 1


def test_sign_record_store_migrates_legacy_json_with_explicit_user_id(tmp_path):
    workdir = tmp_path / ".signer"
    record_file = workdir / "signs" / "linuxdo" / "sign_record.json"
    record_file.parent.mkdir(parents=True, exist_ok=True)
    with open(record_file, "w", encoding="utf-8") as fp:
        json.dump(
            {
                "2026-03-17": "2026-03-17T06:00:00+08:00",
                "2026-03-18": "2026-03-18T06:00:00+08:00",
            },
            fp,
        )

    store = SignRecordStore(workdir)
    summary = store.migrate_all_json_records(legacy_user_id="123456")

    assert summary.migrated_files == 1
    assert summary.migrated_records == 2
    assert summary.skipped_files == []
    assert store.load_records("linuxdo", "123456") == {
        "2026-03-17": "2026-03-17T06:00:00+08:00",
        "2026-03-18": "2026-03-18T06:00:00+08:00",
    }


def test_sign_record_store_skips_ambiguous_legacy_json(tmp_path):
    workdir = tmp_path / ".signer"
    (workdir / "users" / "1001").mkdir(parents=True, exist_ok=True)
    (workdir / "users" / "1002").mkdir(parents=True, exist_ok=True)
    record_file = workdir / "signs" / "linuxdo" / "sign_record.json"
    record_file.parent.mkdir(parents=True, exist_ok=True)
    with open(record_file, "w", encoding="utf-8") as fp:
        json.dump({"2026-03-17": "2026-03-17T06:00:00+08:00"}, fp)

    store = SignRecordStore(workdir)
    summary = store.migrate_all_json_records()

    assert summary.migrated_files == 0
    assert summary.migrated_records == 0
    assert summary.skipped_files == [record_file]
