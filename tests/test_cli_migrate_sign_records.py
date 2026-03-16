import json

from click.testing import CliRunner

import tg_signer.cli.signer as signer_cli


def test_migrate_sign_records_command(tmp_path):
    workdir = tmp_path / ".signer"
    record_file = workdir / "signs" / "linuxdo" / "sign_record.json"
    record_file.parent.mkdir(parents=True, exist_ok=True)
    with open(record_file, "w", encoding="utf-8") as fp:
        json.dump({"2026-03-17": "2026-03-17T06:00:00+08:00"}, fp)

    runner = CliRunner()
    result = runner.invoke(
        signer_cli.tg_signer,
        [
            "--workdir",
            str(workdir),
            "migrate-sign-records",
            "--legacy-user-id",
            "123456",
        ],
    )

    assert result.exit_code == 0
    assert "迁移文件数: 1" in result.output
    assert "迁移记录数: 1" in result.output
    assert (workdir / "data.sqlite3").is_file()
