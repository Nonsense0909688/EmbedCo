"""Production logging setup.

* Console handler (stderr): human-readable text or JSON lines.
* Rotating file handler ``embedco.log`` (10 MiB x 5) with every record.
* Rotating file handler ``error.log`` (WARNING and above only).
* Every record carries a ``request_id`` (set per HTTP request via a context
  variable) so one request can be followed across modules and threads.
* Uncaught exceptions (main thread and worker threads) are logged with
  tracebacks instead of vanishing on stderr.

Use ``logging.getLogger(__name__)`` in modules; never ``print`` for diagnostics.
"""

import contextvars
import json
import logging
import logging.handlers
import sys
import threading
from datetime import datetime, timezone

request_id_var = contextvars.ContextVar("request_id", default="-")

_STANDARD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime", "request_id", "taskName"}

TEXT_FORMAT = "%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s"


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line; extra={...} fields are merged in."""

    def format(self, record):
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "thread": record.threadName,
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def _formatter(fmt):
    return JsonFormatter() if fmt == "json" else logging.Formatter(TEXT_FORMAT)


def configure_logging(settings):
    """Configure the root logger. Safe to call more than once."""
    level = getattr(logging, str(settings.log_level).upper(), None)
    if not isinstance(level, int):
        level = logging.INFO

    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_embedco", False):
            root.removeHandler(handler)
            handler.close()
    root.setLevel(level)

    handlers = []
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(_formatter(settings.log_format))
    handlers.append(console)

    if settings.log_to_file:
        try:
            settings.log_dir.mkdir(parents=True, exist_ok=True)
            main_file = logging.handlers.RotatingFileHandler(
                settings.log_dir / "embedco.log",
                maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8",
            )
            main_file.setFormatter(_formatter(settings.log_format))
            handlers.append(main_file)

            error_file = logging.handlers.RotatingFileHandler(
                settings.log_dir / "error.log",
                maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
            )
            error_file.setLevel(logging.WARNING)
            error_file.setFormatter(_formatter(settings.log_format))
            handlers.append(error_file)
        except OSError as error:
            # Never refuse to start because the log directory is read-only.
            console.handle(logging.LogRecord(
                "embedco.logging", logging.WARNING, __file__, 0,
                f"File logging disabled ({settings.log_dir}): {error}", (), None,
            ))

    request_filter = RequestIdFilter()
    for handler in handlers:
        handler._embedco = True
        handler.addFilter(request_filter)
        root.addHandler(handler)

    logging.captureWarnings(True)
    _install_excepthooks()


def _install_excepthooks():
    log = logging.getLogger("embedco.uncaught")

    def main_hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log.critical("Uncaught exception", exc_info=(exc_type, exc, tb))

    def thread_hook(args):
        if args.exc_type is SystemExit:
            return
        log.critical(
            "Uncaught exception in thread %s",
            getattr(args.thread, "name", "?"),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = main_hook
    threading.excepthook = thread_hook
