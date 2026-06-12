from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess

from . import auth_mac

ROOT_OVERRIDE_ENV = "POP_ALLOW_ROOT"
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]+")


def _sanitize_action(action: str) -> str:
    cleaned = _CONTROL_CHARS.sub(" ", str(action)).strip()
    return cleaned[:120] or "protected operation"


def _running_as_root_without_override() -> bool:
    geteuid = getattr(os, "geteuid", None)
    return callable(geteuid) and geteuid() == 0 and os.getenv(ROOT_OVERRIDE_ENV) != "1"


def _auth_via_sudo(action: str, timeout: int = 20) -> bool:
    if _running_as_root_without_override():
        return False
    sudo = shutil.which("sudo")
    if not sudo:
        return False
    prompt = f"[gs-backup] Authenticate to {_sanitize_action(action)}: "
    subprocess.run([sudo, "-k"], check=False)
    try:
        proc = subprocess.run(
            [sudo, "-p", prompt, "-v"],
            check=False,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def require_local_auth(action: str) -> bool:
    system = platform.system()
    if system == "Darwin":
        return auth_mac.require_local_auth(action)
    if system == "Linux":
        return _auth_via_sudo(action)
    if os.name == "posix":
        return _auth_via_sudo(action)
    raise RuntimeError(f"local authentication is unsupported on {system}")
