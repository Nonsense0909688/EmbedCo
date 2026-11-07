"""arduino-cli integration: serial ports, compile and upload."""

import logging
import re
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from ..errors import BlockError, ValidationError

logger = logging.getLogger(__name__)

_SAFE_PORT = re.compile(r"^[A-Za-z0-9_./:\\-]+$")
_SAFE_LIBRARY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.+@:-]*$")


@dataclass(frozen=True)
class BuildResult:
    ok: bool
    stage: str       # generate | compile | upload | done
    log: str
    code: str = ""

    def as_dict(self):
        return {"ok": self.ok, "stage": self.stage, "log": self.log, "code": self.code}


class ArduinoService:
    def __init__(self, codegen):
        self._codegen = codegen
        self._board_lock = threading.Lock()   # one board operation at a time

    # ---- serial ports ----

    @staticmethod
    def list_ports():
        try:
            from serial.tools import list_ports
        except ImportError:
            logger.warning("pyserial is not installed; serial ports cannot be listed")
            return []
        try:
            return [{"device": p.device, "description": p.description, "hwid": p.hwid}
                    for p in list_ports.comports()]
        except Exception:
            logger.exception("Serial port enumeration failed")
            return []

    # ---- arduino-cli ----

    @staticmethod
    def cli_path():
        return shutil.which("arduino-cli")

    def run_cli(self, args, timeout=120):
        """Run arduino-cli. Returns (ok, combined output)."""
        cli = self.cli_path()
        if not cli:
            logger.error("arduino-cli not found on PATH")
            return False, ("arduino-cli not found on PATH. Install it "
                           "(https://arduino.github.io/arduino-cli/) and restart the server.")
        started = time.perf_counter()
        try:
            proc = subprocess.run([cli, *args], capture_output=True, text=True,
                                  errors="replace", timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.error("arduino-cli %s timed out after %ss", args[0], timeout)
            return False, f"arduino-cli timed out after {timeout}s: arduino-cli {' '.join(args)}"
        except OSError as error:
            logger.exception("arduino-cli could not be started")
            return False, f"arduino-cli failed: {error!r}"
        output = ((proc.stdout or "") + (proc.stderr or "")).strip()
        logger.info("arduino-cli %s exited %d in %.1fs", args[0], proc.returncode,
                    time.perf_counter() - started)
        if proc.returncode != 0:
            logger.debug("arduino-cli %s output:\n%s", args[0], output)
        return proc.returncode == 0, output

    # ---- build ----

    def build(self, project, port=None):
        """Generate, compile and (if ``port``) upload. Never raises for expected failures."""
        board = project.get("board", "arduino") if isinstance(project, dict) else "arduino"
        fqbn = self._codegen.fqbn(board)
        if not fqbn:
            return BuildResult(False, "generate",
                               f"Board '{board}' has no FQBN in boards.yaml — cannot compile/upload for it.")
        if port is not None and (port.startswith("-") or not _SAFE_PORT.match(port)):
            logger.warning("Rejected unsafe serial port value: %r", port)
            return BuildResult(False, "upload", f"Invalid serial port: {port!r}")

        try:
            generated = self._codegen.generate(project)
        except BlockError as error:
            return BuildResult(False, "generate", str(error))
        except ValidationError as error:
            return BuildResult(False, "generate", error.message)

        code = generated.code
        log = [f"Board: {board}  ({fqbn})"]
        logger.info("Build started: board=%s fqbn=%s port=%s", board, fqbn, port or "-")
        started = time.perf_counter()

        with self._board_lock, tempfile.TemporaryDirectory(prefix="embedco_") as tmp:
            sketch_dir = Path(tmp)
            # arduino-cli requires the .ino filename to match its folder name.
            (sketch_dir / f"{sketch_dir.name}.ino").write_text(code, encoding="utf-8")

            for lib in generated.libraries:
                if not _SAFE_LIBRARY.match(lib):
                    logger.warning("Skipping library with unsafe name: %r", lib)
                    log.append(f"Skipped library with invalid name: {lib!r}")
                    continue
                ok, out = self.run_cli(["lib", "install", lib], timeout=90)
                log.append(f"$ arduino-cli lib install {lib}\n{out or 'ok'}")
                if not ok:
                    logger.warning("Library install failed for %s", lib)

            log.append(f"$ arduino-cli compile --fqbn {fqbn} …")
            ok, out = self.run_cli(["compile", "--fqbn", fqbn, str(sketch_dir)], timeout=180)
            log.append(out or ("compiled ok" if ok else "compile failed"))
            if not ok:
                return BuildResult(False, "compile", "\n".join(log), code)

            if port is None:
                logger.info("Compile finished in %.1fs", time.perf_counter() - started)
                return BuildResult(True, "done",
                                   "\n".join(log) + "\nCompiled ok (no port — nothing uploaded).", code)

            log.append(f"$ arduino-cli upload --port {port} --fqbn {fqbn} …")
            ok, out = self.run_cli(["upload", "--port", port, "--fqbn", fqbn, str(sketch_dir)], timeout=120)
            log.append(out or ("uploaded ok" if ok else "upload failed"))
            if not ok:
                return BuildResult(False, "upload", "\n".join(log), code)

        logger.info("Upload to %s finished in %.1fs", port, time.perf_counter() - started)
        return BuildResult(True, "done", "\n".join(log) + f"\nDone — sketch uploaded to {port}.", code)
