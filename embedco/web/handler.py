"""HTTP handler: request ids, access logs, guards, error mapping, dispatch."""

import json
import logging
import re
import secrets
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

from ..errors import BlockError, ForbiddenError, PayloadTooLargeError, ServiceError
from ..logging_config import request_id_var
from .router import Request, Response

logger = logging.getLogger(__name__)
access_log = logging.getLogger("embedco.access")

_REQUEST_ID_OK = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_MUTATING = ("POST", "PUT", "DELETE", "PATCH")
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def _host_only(value):
    """'localhost:8000' -> 'localhost', '[::1]:8000' -> '[::1]'."""
    value = (value or "").strip()
    if value.startswith("["):
        return value.split("]")[0] + "]"
    return value.split(":")[0]


def make_handler(router, services):
    """Build a handler class bound to a router and the service container."""
    settings = services.settings

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        timeout = settings.request_timeout   # socket timeout: slow clients can't pin a thread
        server_version = "EmbedCo"
        sys_version = ""

        # ---- plumbing ----

        def log_message(self, *args):
            pass   # replaced by structured access logging

        def log_error(self, fmt, *args):
            logger.warning("HTTP protocol error from %s: %s", self.client_address[0], fmt % args)

        def _send(self, status, body, content_type="application/json"):
            if isinstance(body, bytes):
                data = body
            else:
                data = json.dumps(body).encode("utf-8")
            self._status = status
            self.send_response(status)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Request-ID", self._request_id)
            if self.command in _MUTATING and not self._body_read:
                # An unread body would corrupt the next request on a keep-alive connection.
                self.close_connection = True
            if self.close_connection:
                self.send_header("Connection", "close")
            for key, value in SECURITY_HEADERS.items():
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def _error(self, status, message, **extra):
            self._send(status, {"error": message, "request_id": self._request_id, **extra})

        # ---- guards ----

        def _check_host_and_origin(self):
            host = _host_only(self.headers.get("Host"))
            if host not in settings.allowed_hosts:
                raise ForbiddenError("Host not allowed")
            origin = self.headers.get("Origin")
            if origin and origin != "null":
                if _host_only(urlparse(origin).netloc) not in settings.allowed_hosts:
                    raise ForbiddenError("Cross-origin requests are not allowed")
            elif origin == "null" and self.command in _MUTATING:
                raise ForbiddenError("Cross-origin requests are not allowed")

        def _read_body(self):
            if self.command not in _MUTATING:
                return b""
            self._body_read = True
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                raise ServiceError("Invalid Content-Length header") from None
            if length < 0:
                raise ServiceError("Invalid Content-Length header")
            if length > settings.max_body_bytes:
                # Close rather than read an oversized body.
                self.close_connection = True
                raise PayloadTooLargeError(f"Request body exceeds {settings.max_body_bytes} bytes")
            return self.rfile.read(length) if length else b""

        # ---- dispatch ----

        def _handle(self):
            started = time.perf_counter()
            self._status = 500
            self._body_read = False
            incoming = self.headers.get("X-Request-ID", "")
            self._request_id = incoming if _REQUEST_ID_OK.match(incoming) else secrets.token_hex(6)
            token = request_id_var.set(self._request_id)
            path = urlparse(self.path).path
            try:
                try:
                    self._check_host_and_origin()
                    handler, params, path_known = router.match(self.command, path)
                    if handler is None:
                        if path_known:
                            return self._error(405, "Method not allowed")
                        return self._error(404, "Not found")
                    request = Request(
                        method=self.command, path=path, headers=self.headers,
                        client=self.client_address[0], params=params,
                        raw_body=self._read_body(), request_id=self._request_id,
                    )
                    result = handler(request)
                    if isinstance(result, Response):
                        self._send(result.status, result.body, result.content_type)
                    else:
                        self._send(*result)
                except ServiceError as error:
                    level = logging.WARNING if error.status in (403, 413) else logging.INFO
                    logger.log(level, "%s %s -> %d: %s", self.command, path, error.status, error.message)
                    self._error(error.status, error.message)
                except BlockError as error:
                    logger.info("%s %s -> 400: %s", self.command, path, error)
                    self._error(400, str(error))
                except (BrokenPipeError, ConnectionResetError, TimeoutError):
                    self.close_connection = True
                    logger.info("Client disconnected during %s %s", self.command, path)
                except Exception:
                    logger.exception("Unhandled error in %s %s", self.command, path)
                    try:
                        self._error(500, "Internal server error")
                    except OSError:
                        self.close_connection = True
            finally:
                elapsed = (time.perf_counter() - started) * 1000
                access_log.info(
                    "%s %s %d %.1fms", self.command, self.path, self._status, elapsed,
                    extra={"method": self.command, "path": self.path, "status": self._status,
                           "duration_ms": round(elapsed, 1), "client": self.client_address[0]},
                )
                request_id_var.reset(token)

        do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = _handle

    return Handler
