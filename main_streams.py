"""Sorties standard de secours pour une application sans console (voir main.py)."""
import sys


def fix_streams() -> None:
    if sys.stdout is not None and sys.stderr is not None:
        return
    from config import data_dir
    log = open(data_dir() / "jimmy.log", "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log
