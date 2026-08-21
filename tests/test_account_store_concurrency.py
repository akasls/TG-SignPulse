import concurrent.futures
import shutil
import tempfile
from pathlib import Path
from backend.core.config import get_settings
from backend.utils.tg_session import (
    set_account_profile,
    get_account_profile,
    list_account_names,
    delete_account_session_string,
)


def test_concurrent_account_store_updates(monkeypatch):
    temp_dir = Path(tempfile.mkdtemp())
    try:
        store_file = temp_dir / "accounts.json"
        monkeypatch.setattr("backend.utils.tg_session._account_store_path", lambda: store_file)

        def worker(i):
            acc_name = f"account_{i % 5}"
            set_account_profile(acc_name, remark=f"remark_{i}", proxy=f"socks5://127.0.0.1:{1080 + i}")
            profile = get_account_profile(acc_name)
            assert profile is not None

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker, i) for i in range(50)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        names = list_account_names()
        assert len(names) == 5
        assert set(names) == {f"account_{i}" for i in range(5)}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
