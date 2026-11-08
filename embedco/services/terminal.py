"""In-browser terminal: runs one shell command at a time (local use only).

This is remote code execution by design. It is only reachable from the local
editor (loopback Host + custom header + same-origin check, enforced in the web
layer) and is disabled entirely when the server binds to a non-loopback
address. Every command is written to the ``embedco.terminal.audit`` log.
"""

import logging
import subprocess
import threading
from pathlib import Path

from ..errors import ForbiddenError

logger = logging.getLogger(__name__)
audit = logging.getLogger("embedco.terminal.audit")

MAX_OUTPUT_CHARS = 1_000_000
MAX_COMMAND_CHARS = 8_000
TIMEOUT_SECONDS = 60


class TerminalService:
    def __init__(self, start_dir, enabled=True):
        self.enabled = enabled
        self._cwd = Path(start_dir).resolve()
        self._lock = threading.Lock()   # one command at a time, cwd is shared state

    def run(self, cmd, client="-"):
        if not self.enabled:
            audit.warning("Rejected terminal command (terminal disabled) from %s", client)
            raise ForbiddenError("Terminal is disabled on this server")

        cmd = str(cmd or "").strip()[:MAX_COMMAND_CHARS]
        with self._lock:
            audit.info("terminal command from %s in %s: %s", client, self._cwd, cmd, extra={"cmd": cmd})
            out, code = "", 0

            if cmd == "cd" or cmd.startswith("cd "):
                target = cmd[2:].strip().strip('"') or str(Path.home())
                new = (self._cwd / Path(target).expanduser()).resolve()
                if new.is_dir():
                    self._cwd = new
                else:
                    out, code = f"cd: no such directory: {target}\n", 1
            elif cmd:
                try:
                    proc = subprocess.run(
                        cmd, shell=True, cwd=self._cwd, capture_output=True, text=True,
                        errors="replace", timeout=TIMEOUT_SECONDS, stdin=subprocess.DEVNULL,
                    )
                    out, code = (proc.stdout or "") + (proc.stderr or ""), proc.returncode
                except subprocess.TimeoutExpired:
                    logger.warning("Terminal command timed out after %ss", TIMEOUT_SECONDS)
                    out = f"Command stopped after {TIMEOUT_SECONDS} s. The terminal runs one command at a time.\n"
                    code = 124
                except OSError as error:
                    logger.exception("Terminal command could not be started")
                    out, code = f"Could not run command: {error}\n", 127

            if len(out) > MAX_OUTPUT_CHARS:
                out = out[:MAX_OUTPUT_CHARS] + "\n… output truncated …\n"
            if code:
                audit.info("terminal command exited with %s", code)
            return {"out": out, "code": code, "cwd": str(self._cwd)}
