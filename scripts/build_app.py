#!/usr/bin/env python3
from __future__ import annotations

import argparse
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

APP_DISPLAY_NAME = "Pop"
BINARY_NAME = "pop"
DIST_DIR = Path("dist")


def _run(cmd: list[str]) -> None:
    print("[build]", " ".join(cmd))
    subprocess.run(cmd, check=True)


def _machine() -> str:
    return platform.machine().replace(" ", "_") or "unknown"


def _binary_path() -> Path:
    return DIST_DIR / BINARY_NAME


def run_pyinstaller() -> Path:
    _run([
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--onefile",
        "--console",
        "--name",
        BINARY_NAME,
        "backup.py",
    ])
    binary = _binary_path()
    if not binary.exists():
        raise SystemExit(f"PyInstaller did not create expected binary: {binary}")
    return binary


def _write_text(path: Path, text: str, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _readme_text() -> str:
    return """Pop
===

Experimental local-first encrypted backup vault.

Run the included executable from a terminal. The app stores data in the
platform default gs-backup-storage location unless GSBACKUP_STORAGE is set.

Nextcloud/WebDAV push mirror uses environment variables:
  POP_NEXTCLOUD_URL
  POP_NEXTCLOUD_USER
  POP_NEXTCLOUD_PASSWORD
  POP_NEXTCLOUD_PATH (optional)
"""


def _zip_dir(src: Path, dest: Path) -> None:
    if dest.exists():
        dest.unlink()
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src.rglob("*")):
            arcname = path.relative_to(src.parent).as_posix()
            info = zipfile.ZipInfo(arcname)
            st = path.stat()
            info.date_time = (2026, 1, 1, 0, 0, 0)
            info.external_attr = (stat.S_IMODE(st.st_mode) & 0xFFFF) << 16
            if path.is_dir():
                info.filename += "/"
                zf.writestr(info, b"")
            else:
                zf.writestr(info, path.read_bytes())


def package_linux(binary: Path) -> Path:
    root = DIST_DIR / f"{APP_DISPLAY_NAME}-linux-{_machine()}"
    if root.exists():
        shutil.rmtree(root)
    bin_dir = root / "bin"
    share_dir = root / "share" / "applications"
    bin_dir.mkdir(parents=True)
    shutil.copy2(binary, bin_dir / BINARY_NAME)
    (bin_dir / BINARY_NAME).chmod(0o755)
    _write_text(root / "README.txt", _readme_text())
    _write_text(
        share_dir / "pop.desktop",
        """[Desktop Entry]
Type=Application
Name=Pop
Comment=Experimental encrypted backup vault
Exec=pop
Terminal=true
Categories=Utility;Archiving;
""",
    )
    artifact = DIST_DIR / f"{APP_DISPLAY_NAME}-linux-{_machine()}.tar.gz"
    if artifact.exists():
        artifact.unlink()
    with tarfile.open(artifact, "w:gz") as tf:
        tf.add(root, arcname=root.name)
    return artifact


def package_macos(binary: Path) -> Path:
    app = DIST_DIR / f"{APP_DISPLAY_NAME}.app"
    if app.exists():
        shutil.rmtree(app)
    macos_dir = app / "Contents" / "MacOS"
    resources_dir = app / "Contents" / "Resources"
    macos_dir.mkdir(parents=True)
    resources_dir.mkdir(parents=True)
    shutil.copy2(binary, macos_dir / BINARY_NAME)
    (macos_dir / BINARY_NAME).chmod(0o755)
    _write_text(resources_dir / "README.txt", _readme_text())
    _write_text(
        macos_dir / APP_DISPLAY_NAME,
        """#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
CMD="$(printf "%q" "${DIR}/pop")"
osascript \\
  -e 'tell application "Terminal"' \\
  -e 'activate' \\
  -e "do script \\"${CMD}\\"" \\
  -e 'end tell'
""",
        executable=True,
    )
    _write_text(
        app / "Contents" / "Info.plist",
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>Pop</string>
  <key>CFBundleIdentifier</key>
  <string>dev.pop.backup</string>
  <key>CFBundleName</key>
  <string>Pop</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>0.1-alpha</string>
  <key>CFBundleVersion</key>
  <string>0.1-alpha</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
</dict>
</plist>
""",
    )
    artifact = DIST_DIR / f"{APP_DISPLAY_NAME}-macos-{_machine()}.zip"
    _zip_dir(app, artifact)
    return artifact


def package_current_os(binary: Path) -> Path:
    system = platform.system()
    if system == "Linux":
        return package_linux(binary)
    if system == "Darwin":
        return package_macos(binary)
    raise SystemExit(f"Unsupported packaging platform: {system}; Pop packages Unix-like builds only")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and package Pop for the current OS.")
    parser.add_argument("--skip-pyinstaller", action="store_true", help="Package an existing dist/pop binary.")
    args = parser.parse_args()

    binary = _binary_path() if args.skip_pyinstaller else run_pyinstaller()
    if not binary.exists():
        raise SystemExit(f"Binary not found: {binary}")
    artifact = package_current_os(binary)
    print(f"[build] Artifact: {artifact}")


if __name__ == "__main__":
    main()
