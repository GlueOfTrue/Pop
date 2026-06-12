#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON:-python3}"
VENV_DIR="${VENV_DIR:-.venv-build}"
USE_EXISTING_VENV="${USE_EXISTING_VENV:-0}"

log() {
  printf "[build] %s\n" "$*"
}

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Python not found: ${PYTHON_BIN}"
  exit 1
fi

PY_VER="$(${PYTHON_BIN} - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"

MAJOR="${PY_VER%%.*}"
MINOR="${PY_VER##*.}"
if [ "${MAJOR}" -lt 3 ] || [ "${MINOR}" -lt 11 ]; then
  echo "Python 3.11+ required. Detected ${PY_VER}"
  exit 1
fi

if [ "${USE_EXISTING_VENV}" = "1" ]; then
  if [ ! -d "${VENV_DIR}" ]; then
    echo "USE_EXISTING_VENV=1 but ${VENV_DIR} not found."
    exit 1
  fi
else
  log "Creating venv at ${VENV_DIR}"
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

PIP_BIN="${VENV_DIR}/bin/pip"
PY_BIN="${VENV_DIR}/bin/python"

log "Installing build dependencies..."
"${PIP_BIN}" install --upgrade pip
"${PIP_BIN}" install -r requirements-build.txt

log "Building app package..."
"${PY_BIN}" scripts/build_app.py

log "Done. Artifacts:"
ls -1 dist/Pop-* 2>/dev/null || true
