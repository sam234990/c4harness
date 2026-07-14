"""Global data and runtime path resolution."""

from __future__ import annotations

import os
from pathlib import Path


def data_home() -> Path:
    configured = os.environ.get("XDG_DATA_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".local" / "share"


def default_memory_path() -> Path:
    configured = os.environ.get("C4HARNESS_MEMORY")
    if configured:
        return Path(configured).expanduser()
    return data_home() / "c4harness" / "memory.sqlite3"
