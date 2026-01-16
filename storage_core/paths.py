from __future__ import annotations

import os
import platform
from pathlib import Path

APP_NAME = "gs-backup-storage"
STORAGE_ENV_VAR = "GSBACKUP_STORAGE"
CONFIG_FILENAME = "config.json"
CATALOG_DIRNAME = "meta"
CATALOG_FILENAME = "catalog.json"
RECORDS_DIRNAME = "records"
KEYSTORE_FILENAME = "keystore.json"
TOTP_FILENAME = "totp.json"
OBJECTS_DIRNAME = "objects"
ECC_DIRNAME = "ecc"


def get_default_storage_path() -> Path:
    home = Path.home()
    system = platform.system()
    if system == "Darwin":
        return home / "Library" / "Application Support" / APP_NAME
    if system == "Linux":
        legacy = home / "Library" / "Application Support" / APP_NAME
        if legacy.exists():
            return legacy
        xdg = os.getenv("XDG_DATA_HOME")
        if xdg:
            return Path(xdg) / APP_NAME
        return home / ".local" / "share" / APP_NAME
    return home / APP_NAME


def get_storage_root() -> Path:
    env = os.getenv(STORAGE_ENV_VAR)
    if env:
        return Path(env).expanduser()
    return get_default_storage_path()


def get_catalog_path(storage_root: Path) -> Path:
    return storage_root / CATALOG_DIRNAME / CATALOG_FILENAME


def get_records_dir(storage_root: Path) -> Path:
    return storage_root / CATALOG_DIRNAME / RECORDS_DIRNAME


def get_record_path(storage_root: Path, doc_id: str, version: int) -> Path:
    safe_doc_id = str(doc_id)
    return get_records_dir(storage_root) / safe_doc_id / f"v{version}.bin"


def get_keystore_path(storage_root: Path) -> Path:
    return storage_root / CATALOG_DIRNAME / KEYSTORE_FILENAME


def get_totp_path(storage_root: Path) -> Path:
    return storage_root / CATALOG_DIRNAME / TOTP_FILENAME


def get_ecc_dir(storage_root: Path) -> Path:
    return storage_root / ECC_DIRNAME
