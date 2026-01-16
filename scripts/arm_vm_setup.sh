#!/usr/bin/env bash
set -euo pipefail

log() {
  printf "[setup] %s\n" "$*"
}

DESKTOP="${HOME}/Desktop"
TOOLS_DIR="${HOME}/Tools"

mkdir -p "${DESKTOP}" "${TOOLS_DIR}"

log "Updating apt..."
sudo apt update

log "Installing base packages..."
sudo apt install -y \
  git curl wget ca-certificates unzip p7zip-full \
  python3 python3-venv python3-pip \
  gdb strace ltrace \
  binwalk dirsearch \
  golang-go \
  libreoffice || true

log "Installing Java (prefer 21, fallback 17)..."
sudo apt install -y openjdk-21-jre || sudo apt install -y openjdk-17-jre

log "Installing Ghidra (apt if available)..."
sudo apt install -y ghidra || log "ghidra not available via apt; install manually if needed."

log "Installing edb (if available)..."
sudo apt install -y edb-debugger || log "edb-debugger not available on this arch."

log "Python tools..."
python3 -m pip install --user --upgrade pip
python3 -m pip install --user pwntools pybase64 sympy

log "GDB extensions..."
if [ ! -d "${HOME}/pwndbg" ]; then
  git clone https://github.com/pwndbg/pwndbg.git "${HOME}/pwndbg"
fi
if [ ! -d "${HOME}/gef" ]; then
  git clone https://github.com/hugsy/gef.git "${HOME}/gef"
fi

GDBINIT="${HOME}/.gdbinit"
if [ ! -f "${GDBINIT}" ]; then
  cat > "${GDBINIT}" <<'EOF'
# pwndbg (default)
source ~/pwndbg/gdbinit.py

# gef (uncomment to enable, then comment pwndbg line above)
# source ~/gef/gef.py
EOF
fi

log "Docs repositories..."
if [ ! -d "${DESKTOP}/hacktricks" ]; then
  git clone https://github.com/HackTricks-wiki/hacktricks.git "${DESKTOP}/hacktricks"
fi
if [ ! -d "${DESKTOP}/CheatSheetSeries" ]; then
  git clone https://github.com/OWASP/CheatSheetSeries.git "${DESKTOP}/CheatSheetSeries"
fi
if [ ! -d "${DESKTOP}/PayloadsAllTheThings" ]; then
  git clone https://github.com/swisskyrepo/PayloadsAllTheThings.git "${DESKTOP}/PayloadsAllTheThings"
fi

log "Volatility3..."
if [ ! -d "${HOME}/volatility3" ]; then
  git clone https://github.com/volatilityfoundation/volatility3.git "${HOME}/volatility3"
fi
if [ ! -d "${HOME}/volatility3/venv" ]; then
  python3 -m venv "${HOME}/volatility3/venv"
  "${HOME}/volatility3/venv/bin/pip" install --upgrade pip
  "${HOME}/volatility3/venv/bin/pip" install -r "${HOME}/volatility3/requirements.txt"
fi

log "Wordlist (rockyou)..."
if [ -f /usr/share/wordlists/rockyou.txt.gz ] && [ ! -f /usr/share/wordlists/rockyou.txt ]; then
  sudo gzip -dk /usr/share/wordlists/rockyou.txt.gz
fi

log "Optional: Obsidian (manual download required for arm64 AppImage)."
log "Optional: IDA Freeware (no official arm64 build; use x86_64 VM if needed)."
log "Optional: Burp JWT Editor (install via BApp Store inside Burp)."

log "Done."
