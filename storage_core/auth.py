from __future__ import annotations

import os
import platform
import shutil
import subprocess

from . import auth_mac


def _auth_via_sudo(action: str, timeout: int = 20) -> bool:
    sudo = shutil.which("sudo")
    if not sudo:
        return False
    prompt = f"[gs-backup] Authenticate to {action}: "
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
