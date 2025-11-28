from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "gs-backup-storage"
STORAGE_ENV_VAR = "GSBACKUP_STORAGE"
CONFIG_FILENAME = "config.json"
INDEX_DIRNAME = "meta"
INDEX_FILENAME = "index.json"
OBJECTS_DIRNAME = "objects"


def get_default_storage_path() -> Path:
    home = Path.home()
    return home / "Library" / "Application Support" / APP_NAME


def get_storage_root() -> Path:
    env = os.getenv(STORAGE_ENV_VAR)
    if env:
        return Path(env).expanduser()
    return get_default_storage_path()
