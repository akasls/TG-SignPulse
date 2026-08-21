from __future__ import annotations

import ctypes
import gc
import logging
import sys

_logger = logging.getLogger("tg_signer.memory")


def trim_memory() -> None:
    """
    强制执行 Python 垃圾回收并尝试将未使用的内存页归还给操作系统。
    在 Linux (glibc) 环境下调用 malloc_trim(0)。
    """
    try:
        gc.collect()
        if sys.platform.startswith("linux"):
            try:
                libc = ctypes.CDLL("libc.so.6")
                if hasattr(libc, "malloc_trim"):
                    libc.malloc_trim(0)
            except Exception:
                pass
    except Exception as exc:
        _logger.debug("trim_memory failed: %s", exc)
