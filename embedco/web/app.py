"""Application assembly and server lifecycle."""

import logging
import signal
import threading
import webbrowser
from http.server import ThreadingHTTPServer

from .. import __version__
from ..generator import EmbedCoGenerator
from ..services.arduino import ArduinoService
from ..services.codegen import CodegenService
from ..services.projects import ProjectStore
from ..services.terminal import TerminalService
from .handler import make_handler
from .routes import Services, build_router

logger = logging.getLogger(__name__)


class Server(ThreadingHTTPServer):
    daemon_threads = True          # never block shutdown on a stuck request
    allow_reuse_address = True
    request_queue_size = 32

    def handle_error(self, request, client_address):
        logger.exception("Error while handling request from %s", client_address[0])


def build_services(settings):
    generator = EmbedCoGenerator(
        definitions=settings.blocks_dir,
        boards=settings.boards_file,
        plugins_dir=settings.plugins_dir,
    )
    codegen = CodegenService(generator)
    # The terminal is remote code execution: never expose it on a non-loopback bind.
    terminal_enabled = settings.terminal_enabled and settings.is_loopback
    if settings.terminal_enabled and not terminal_enabled:
        logger.warning("Terminal disabled: server is bound to non-loopback address %s", settings.host)
    return Services(
        settings=settings,
        codegen=codegen,
        projects=ProjectStore(settings.projects_dir),
        arduino=ArduinoService(codegen),
        terminal=TerminalService(settings.home, enabled=terminal_enabled),
    )


def create_server(settings, services=None):
    services = services or build_services(settings)
    handler = make_handler(build_router(services), services)
    return Server((settings.host, settings.port), handler)


def serve(settings, open_browser=True):
    """Run until Ctrl+C / SIGTERM, then shut down cleanly."""
    if not settings.is_loopback:
        logger.warning(
            "Binding to %s exposes the editor to your network. There is no authentication; "
            "only do this on a trusted network.", settings.host)

    server = create_server(settings)
    host, port = server.server_address[:2]
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '') else host}:{port}"
    logger.info("EmbedCo %s listening on %s (home=%s)", __version__, url, settings.home)
    print(f"EmbedCo editor running at {url}  (Ctrl+C to stop)", flush=True)

    def request_shutdown(signum, _frame):
        logger.info("Received signal %s, shutting down", signal.Signals(signum).name)
        threading.Thread(target=server.shutdown, name="shutdown", daemon=True).start()

    for sig in (signal.SIGINT, getattr(signal, "SIGTERM", None)):
        if sig is not None:
            try:
                signal.signal(sig, request_shutdown)
            except ValueError:   # not in main thread
                pass

    if open_browser:
        threading.Timer(0.6, webbrowser.open, args=[url]).start()

    try:
        server.serve_forever()
    finally:
        server.server_close()
        logger.info("Server stopped")
        print("\nStopped.", flush=True)
