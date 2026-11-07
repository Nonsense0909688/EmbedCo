"""Thread-safe facade over the generator (which keeps per-run state)."""

import logging
import threading
import time
from dataclasses import dataclass

from ..errors import BlockError, ValidationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GenerationResult:
    code: str
    warnings: tuple
    libraries: tuple


class CodegenService:
    def __init__(self, generator):
        self._generator = generator
        self._lock = threading.RLock()

    def generate(self, project):
        """Generate a sketch. Raises BlockError / ValidationError for bad input."""
        started = time.perf_counter()
        with self._lock:
            try:
                code = self._generator.generate_project(project)
            except BlockError as error:
                logger.info("Block error while generating: %s", error)
                raise
            except (KeyError, TypeError, AttributeError) as error:
                logger.warning("Malformed project payload: %r", error)
                raise ValidationError(f"Invalid project: {error!r}") from error
            result = GenerationResult(
                code=code,
                warnings=tuple(self._generator.warnings),
                libraries=tuple(sorted(self._generator.libraries)),
            )
        logger.info(
            "Generated sketch (board=%s, %d bytes, %d warning(s)) in %.1f ms",
            project.get("board", "arduino") if isinstance(project, dict) else "?",
            len(code), len(result.warnings), (time.perf_counter() - started) * 1000,
        )
        return result

    def palette(self):
        with self._lock:
            return self._generator.palette()

    def boards(self):
        with self._lock:
            return self._generator.boards.summary()

    def fqbn(self, board_id):
        with self._lock:
            return self._generator.boards.fqbn(board_id)

    def list_plugins(self):
        with self._lock:
            return self._generator.plugin_registry.listing()

    def install_plugin(self, data, filename="plugin"):
        with self._lock:
            return self._generator.plugin_registry.install(data, filename)

    def set_plugin_enabled(self, plugin_id, enabled):
        with self._lock:
            return self._generator.plugin_registry.set_enabled(plugin_id, enabled)
