from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .paths import CONFIG_FILENAME
from .util import atomic_write_json

DEFAULT_LANG = "ru"
SUPPORTED_LANGS = {"ru", "en"}


def _config_path(storage_root: Path) -> Path:
    return storage_root / CONFIG_FILENAME


def load_config(storage_root: Path) -> Dict[str, Any]:
    path = _config_path(storage_root)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def save_config(storage_root: Path, config: Dict[str, Any]) -> None:
    path = _config_path(storage_root)
    atomic_write_json(path, config)


def get_ui_language(storage_root: Path, default: str = DEFAULT_LANG) -> str:
    config = load_config(storage_root)
    ui = config.get("ui", {})
    if isinstance(ui, dict):
        lang = ui.get("lang")
        if isinstance(lang, str) and lang.lower() in SUPPORTED_LANGS:
            return lang.lower()
    return default


def set_ui_language(storage_root: Path, lang: str) -> str:
    normalized = lang.strip().lower()
    if normalized not in SUPPORTED_LANGS:
        raise ValueError("unsupported language")
    config = load_config(storage_root)
    ui = config.get("ui")
    if not isinstance(ui, dict):
        ui = {}
    ui["lang"] = normalized
    config["ui"] = ui
    save_config(storage_root, config)
    return normalized
