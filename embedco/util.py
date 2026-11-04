"""Small shared helpers."""

import os
import re
import tempfile
from pathlib import Path


def slugify(name, default="project"):
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", str(name or "").strip()).strip("_")
    return slug or default


def atomic_write_text(path, text, encoding="utf-8"):
    """Write ``text`` to ``path`` so readers never see a half-written file."""
    path = Path(path)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
