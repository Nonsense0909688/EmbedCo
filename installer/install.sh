#!/usr/bin/env bash
set -euo pipefail

# EmbedCo installer
# - Installs arduino-cli (for board compile/upload)
# - Installs EmbedCo Python dependencies
#
# Usage:
#   ./installer/install.sh [--prefix DIR] [--project-dir DIR] [--skip-arduino-cli] [--skip-python-deps]
#
# Options:
#   --prefix DIR        Where to install arduino-cli binary (default: $HOME/.local/bin)
#   --project-dir DIR   EmbedCo project directory containing requirements.txt (default: repo root)
#   --skip-arduino-cli  Skip installing arduino-cli
#   --skip-python-deps  Skip installing Python dependencies
#   -h, --help          Show this help

PREFIX="${HOME}/.local/bin"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
INSTALL_ARDUINO_CLI=1
INSTALL_PY_DEPS=1

usage() {
  sed -n '1,18p' "$0" | sed 's/^# \{0,1\}//'
}

log() { printf '[embedco-install] %s\n' "$*"; }
warn() { printf '[embedco-install] warning: %s\n' "$*" >&2; }
err() { printf '[embedco-install] error: %s\n' "$*" >&2; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || err "required command not found: $1"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix) PREFIX="${2:-}"; [[ -n "$PREFIX" ]] || err "--prefix requires a value"; shift 2 ;;
    --project-dir) PROJECT_DIR="${2:-}"; [[ -n "$PROJECT_DIR" ]] || err "--project-dir requires a value"; shift 2 ;;
    --skip-arduino-cli) INSTALL_ARDUINO_CLI=0; shift ;;
    --skip-python-deps) INSTALL_PY_DEPS=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) err "unknown option: $1 (use --help)" ;;
  esac
done

[[ -d "$PROJECT_DIR" ]] || err "project directory not found: $PROJECT_DIR"

install_arduino_cli() {
  need_cmd curl
  need_cmd sh
  mkdir -p "$PREFIX"
  log "Installing arduino-cli to ${PREFIX}..."
  # Official Arduino CLI install script
  curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR="$PREFIX" sh
  if command -v arduino-cli >/dev/null 2>&1; then
    log "arduino-cli installed: $(command -v arduino-cli)"
  elif [[ -x "${PREFIX}/arduino-cli" ]]; then
    log "arduino-cli installed at ${PREFIX}/arduino-cli"
    case ":$PATH:" in
      *":${PREFIX}:"*) ;;
      *) warn "${PREFIX} is not in PATH. Add it with: export PATH=\"${PREFIX}:\$PATH\"" ;;
    esac
  else
    err "arduino-cli installation did not complete successfully"
  fi
  "${PREFIX}/arduino-cli" version 2>/dev/null || arduino-cli version 2>/dev/null || true
}

install_python_deps() {
  local py=""
  if command -v python3 >/dev/null 2>&1; then py="python3";
  elif command -v python >/dev/null 2>&1; then py="python";
  else err "Python 3 is required but was not found (install python3 and pip)."; fi

  "$py" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,8) else 1)' \
    || err "Python 3.8+ is required (found: $("$py" --version 2>&1))"

  local req="${PROJECT_DIR}/requirements.txt"
  [[ -f "$req" ]] || err "requirements.txt not found in ${PROJECT_DIR}"

  log "Installing EmbedCo Python dependencies from ${req}..."
  if "$py" -m pip --version >/dev/null 2>&1; then
    "$py" -m pip install --upgrade pip >/dev/null 2>&1 || true
    "$py" -m pip install -r "$req"
  else
    err "pip is not available for $py. Install pip (e.g. python3 -m ensurepip --upgrade) and retry."
  fi
  log "Python dependencies installed."
}

log "EmbedCo installer"
log "Project directory: ${PROJECT_DIR}"

if [[ "$INSTALL_ARDUINO_CLI" -eq 1 ]]; then
  install_arduino_cli
else
  log "Skipping arduino-cli installation (--skip-arduino-cli)."
fi

if [[ "$INSTALL_PY_DEPS" -eq 1 ]]; then
  install_python_deps
else
  log "Skipping Python dependency installation (--skip-python-deps)."
fi

log "Done."
log "To start EmbedCo, run from the project directory:"
log "  python3 server.py    # or: python server.py"
if [[ "$INSTALL_ARDUINO_CLI" -eq 1 ]]; then
  log "Make sure '${PREFIX}' is in your PATH so 'arduino-cli' is available."
fi