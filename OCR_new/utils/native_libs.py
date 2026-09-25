"""
utils/native_libs.py
--------------------
Load native libraries in an order that works on Windows.

On Windows, PyTorch fails to load (or the process crashes) when its DLLs
are loaded after PaddlePaddle's, and pyarrow crashes when it is first
imported after PaddleOCR has started.  Importing them early, before Paddle,
avoids both.  Call ``preload()`` before anything imports paddle.  It does
nothing on other systems.
"""

from __future__ import annotations

import importlib
import sys

_done = False


def preload() -> None:
    global _done
    if _done or sys.platform != "win32":
        return
    _done = True
    for name in ("torch", "pyarrow", "pyarrow.dataset", "pandas"):
        try:
            importlib.import_module(name)
        except Exception:  # not installed, or a DLL problem that paddle-free code can live with
            pass
