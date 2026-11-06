"""Project store: one ``<id>.json`` file per project, written atomically."""

import json
import logging
import re
import threading
from urllib.parse import unquote

from ..errors import NotFoundError, ValidationError
from ..util import atomic_write_text, slugify

logger = logging.getLogger(__name__)

_PROJECT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,120}$")
MAX_NAME_LENGTH = 200


class ProjectStore:
    def __init__(self, directory):
        self.dir = directory.resolve()
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    # ---- paths ----

    def _path(self, project_id):
        """Resolve an id to a path inside the store, or None if the id is unsafe."""
        project_id = unquote(str(project_id or "")).strip()
        if not _PROJECT_ID.match(project_id):
            return None
        path = (self.dir / f"{project_id}.json").resolve()
        if path.parent != self.dir:
            return None
        return path

    def _existing(self, project_id):
        path = self._path(project_id)
        if path is None or not path.exists():
            raise NotFoundError("Project not found")
        return path

    @staticmethod
    def _read(path):
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write(path, data):
        atomic_write_text(path, json.dumps(data, indent=2))

    # ---- validation ----

    @staticmethod
    def _clean(project, name):
        if not isinstance(project, dict):
            raise ValidationError("Project must be a JSON object")
        setup, loop = project.get("setup", []), project.get("loop", [])
        if not isinstance(setup, list) or not isinstance(loop, list):
            raise ValidationError("'setup' and 'loop' must be lists of blocks")
        board = project.get("board", "arduino")
        if not isinstance(board, str):
            raise ValidationError("'board' must be a string")
        return {"name": name[:MAX_NAME_LENGTH], "board": board, "setup": setup, "loop": loop}

    @staticmethod
    def _name(value, default):
        name = str(value or "").strip()
        return name or default

    def _meta(self, path):
        try:
            data = self._read(path)
        except (OSError, ValueError) as error:
            logger.warning("Could not read project %s: %s", path.name, error)
            data = {}
        try:
            stat = path.stat()
            updated, size = stat.st_mtime, stat.st_size
        except OSError:
            updated, size = 0, 0
        return {
            "id": path.stem,
            "name": data.get("name") or path.stem,
            "board": data.get("board", "arduino"),
            "updated": updated,
            "size": size,
            "nodes": len(data.get("setup", [])) + len(data.get("loop", [])),
        }

    # ---- operations ----

    def list(self):
        with self._lock:
            return sorted((self._meta(p) for p in self.dir.glob("*.json")),
                          key=lambda m: m["updated"], reverse=True)

    def get(self, project_id):
        path = self._existing(project_id)
        try:
            return path.stem, self._read(path)
        except (OSError, ValueError) as error:
            logger.exception("Could not read project %s", path.name)
            raise NotFoundError("Could not read project") from error

    def create(self, project):
        with self._lock:
            name = self._name(project.get("name") if isinstance(project, dict) else None, "Project")
            clean = self._clean(project, name)
            base = slugify(name)
            candidate, n = base, 1
            while (self.dir / f"{candidate}.json").exists():
                n += 1
                candidate = f"{base}_{n}"
            path = self.dir / f"{candidate}.json"
            self._write(path, clean)
            logger.info("Created project %s", candidate)
            return self._meta(path), clean

    def save(self, project_id, project):
        with self._lock:
            path = self._existing(project_id)
            name = self._name(project.get("name") if isinstance(project, dict) else None, path.stem)
            clean = self._clean(project, name)
            self._write(path, clean)
            logger.info("Saved project %s (%d node(s))", path.stem,
                        len(clean["setup"]) + len(clean["loop"]))
            return self._meta(path), clean

    def rename(self, project_id, new_name):
        with self._lock:
            path = self._existing(project_id)
            new_name = str(new_name or "").strip()
            if not new_name:
                raise ValidationError("A project name is required")
            current_id = path.stem
            base = slugify(new_name)
            dest_id, n = base, 1
            while (self.dir / f"{dest_id}.json").exists() and dest_id != current_id:
                n += 1
                dest_id = f"{base}_{n}"
            if dest_id != current_id:
                dest = self.dir / f"{dest_id}.json"
                path.rename(dest)
                path = dest
            data = self._read(path)
            data["name"] = new_name[:MAX_NAME_LENGTH]
            self._write(path, data)
            logger.info("Renamed project %s -> %s", current_id, path.stem)
            return self._meta(path), data

    def duplicate(self, project_id):
        with self._lock:
            path = self._existing(project_id)
            data = self._read(path)
            data = {**data, "name": f"{data.get('name') or path.stem} copy"}
            result = self.create(data)
            logger.info("Duplicated project %s -> %s", path.stem, result[0]["id"])
            return result

    def delete(self, project_id):
        with self._lock:
            path = self._existing(project_id)
            path.unlink()
            logger.info("Deleted project %s", path.stem)
