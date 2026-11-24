"""Runtime configuration, resolved once from defaults + environment variables.

Environment variables (all optional):

    EMBEDCO_HOME            writable data root (default: project root, or exe dir when frozen)
    EMBEDCO_HOST            bind address            (default 127.0.0.1)
    EMBEDCO_PORT            bind port               (default 8000)
    EMBEDCO_LOG_LEVEL       DEBUG|INFO|WARNING|ERROR (default INFO)
    EMBEDCO_LOG_FORMAT      text|json               (default text)
    EMBEDCO_LOG_DIR         log directory           (default <home>/logs)
    EMBEDCO_LOG_TO_FILE     1|0                     (default 1)
    EMBEDCO_TERMINAL        1|0 in-browser terminal (default 1, loopback only)
    EMBEDCO_MAX_BODY_BYTES  max request body        (default 5 MiB)
"""

import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path

LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def bundle_dir():
    """Read-only directory containing bundled application resources."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent


def default_home():
    """Writable directory for projects, plugins, and logs."""
    env = os.environ.get("EMBEDCO_HOME")
    if env:
        return Path(env).resolve()
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _env_bool(name, default):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name, default):
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None


@dataclass(frozen=True)
class Settings:
    home: Path
    resources: Path = None
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    log_format: str = "text"
    log_dir: Path = None
    log_to_file: bool = True
    terminal_enabled: bool = True
    max_body_bytes: int = 5 * 1024 * 1024
    request_timeout: float = 30.0

    def __post_init__(self):
        if self.resources is None:
            object.__setattr__(self, "resources", self.home)

    # ---- read-only bundled resources ----
    @property
    def blocks_dir(self):
        return self.resources / "blocks"

    @property
    def boards_file(self):
        return self.resources / "boards.yaml"

    @property
    def ui_file(self):
        return self.resources / "ui" / "index.html"

    @property
    def examples_dir(self):
        return self.resources / "examples"

    # ---- writable user data ----
    @property
    def plugins_dir(self):
        return self.home / "plugins"

    @property
    def projects_dir(self):
        return self.home / "projects"

    @property
    def is_loopback(self):
        return self.host in LOOPBACK_HOSTS

    @property
    def allowed_hosts(self):
        """Host headers we accept (DNS-rebinding / CSRF guard)."""
        hosts = {"127.0.0.1", "localhost", "[::1]", "::1"}
        hosts.add(self.host)
        return hosts

    @classmethod
    def from_env(cls, **overrides):
        home = default_home()
        resources = bundle_dir() if is_frozen() else home
        log_dir = Path(os.environ.get("EMBEDCO_LOG_DIR") or home / "logs")
        settings = cls(
            home=home,
            resources=resources,
            host=os.environ.get("EMBEDCO_HOST", "127.0.0.1"),
            port=_env_int("EMBEDCO_PORT", 8000),
            log_level=os.environ.get("EMBEDCO_LOG_LEVEL", "INFO").upper(),
            log_format=os.environ.get("EMBEDCO_LOG_FORMAT", "text").lower(),
            log_dir=log_dir,
            log_to_file=_env_bool("EMBEDCO_LOG_TO_FILE", True),
            terminal_enabled=_env_bool("EMBEDCO_TERMINAL", True),
            max_body_bytes=_env_int("EMBEDCO_MAX_BODY_BYTES", 5 * 1024 * 1024),
        )
        overrides = {k: v for k, v in overrides.items() if v is not None}
        return replace(settings, **overrides) if overrides else settings
