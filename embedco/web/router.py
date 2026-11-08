"""Minimal method + path router with ``<name>`` path parameters."""

import re
from dataclasses import dataclass, field


@dataclass
class Request:
    method: str
    path: str
    headers: object
    client: str
    params: dict = field(default_factory=dict)
    raw_body: bytes = b""
    request_id: str = "-"

    def json(self, default=None):
        """Parse the body as JSON; raises ValidationError if malformed."""
        from ..errors import ValidationError
        import json
        if not self.raw_body.strip():
            return {} if default is None else default
        try:
            return json.loads(self.raw_body)
        except ValueError:
            raise ValidationError("Request was not valid JSON") from None


@dataclass
class Response:
    status: int
    body: object
    content_type: str = "application/json"


class Router:
    def __init__(self):
        self._routes = []   # (method, compiled regex, handler)

    def add(self, method, pattern, handler):
        regex = re.sub(r"<(\w+)>", r"(?P<\1>[^/]+)", pattern)
        self._routes.append((method.upper(), re.compile(f"^{regex}$"), handler))

    def route(self, method, pattern):
        def decorator(func):
            self.add(method, pattern, func)
            return func
        return decorator

    def match(self, method, path):
        """Return (handler, params, path_known). ``path_known`` distinguishes 404 from 405."""
        path_known = False
        for route_method, regex, handler in self._routes:
            found = regex.match(path)
            if found:
                path_known = True
                if route_method == method:
                    return handler, found.groupdict(), True
        return None, {}, path_known
