"""Pure text helpers used when emitting C++."""

import re

from ..errors import BlockError

_TOKEN = re.compile(r"\{\{|\}\}|\{([A-Za-z_]\w*)\}")
IDENT = re.compile(r"^[A-Za-z_]\w*$")


def as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def c_string(text):
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def indent(text, levels=1):
    pad = "    " * levels
    return "\n".join(pad + line if line.strip() else "" for line in text.splitlines())


def braces(header, body):
    body = body.strip("\n")
    if not body.strip():
        return f"{header} {{\n}}"
    return f"{header} {{\n{indent(body)}\n}}"


def render(template, values, where):
    """Substitute ``{name}`` tokens; ``{{`` / ``}}`` are literal braces."""

    def substitute(match):
        token = match.group(0)
        if token == "{{":
            return "{"
        if token == "}}":
            return "}"
        key = match.group(1)
        if key not in values:
            raise BlockError(f"'{where}': template needs '{key}' but it was not provided")
        return str(values[key])

    return _TOKEN.sub(substitute, template)
