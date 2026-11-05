"""Plugin registry: JSON files in plugins/ that add blocks to the catalog."""

import json
import logging
import re
from pathlib import Path

from ..errors import ConflictError, ServiceError, ValidationError
from ..util import atomic_write_text, slugify

logger = logging.getLogger(__name__)


class PluginRegistry:
    def __init__(self, plugins_dir, catalog):
        self.dir = Path(plugins_dir)
        self.disabled_file = self.dir / "_disabled.json"
        self.catalog = catalog
        self.plugins = []
        self.disabled = set()

    # ---- loading ----

    def load(self):
        """(Re)scan the plugin directory and merge any new plugin blocks. Idempotent."""
        if not self.dir.is_dir():
            logger.info("Plugin directory %s does not exist; no plugins loaded", self.dir)
            return
        self._load_disabled()
        known = {p["id"] for p in self.plugins}
        for path in sorted(self.dir.glob("*.json")):
            if path.stem.startswith("_"):
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                logger.warning("Skipping unreadable plugin %s: %s", path.name, error)
                continue
            if not isinstance(data, dict):
                logger.warning("Skipping plugin %s: top level must be a JSON object", path.name)
                continue
            categories = data.get("categories")
            if not isinstance(categories, dict):
                categories = data
            plugin_id = str(data.get("id") or path.stem)
            if plugin_id in known:
                continue
            block_ids = self._merge(plugin_id, categories)
            self.plugins.append({
                "id": plugin_id,
                "name": data.get("name") or plugin_id,
                "version": data.get("version") or "1.0",
                "description": data.get("description") or "",
                "file": path.name,
                "blocks": block_ids,
            })
            known.add(plugin_id)
            logger.info("Loaded plugin %s (%d block(s)) from %s", plugin_id, len(block_ids), path.name)

    def _merge(self, plugin_id, categories):
        block_ids = []
        for category, blocks in categories.items():
            if not isinstance(blocks, list):
                continue
            for block in blocks:
                if not isinstance(block, dict) or "id" not in block:
                    continue
                if block["id"] in self.catalog:
                    logger.warning("Plugin %s skipped duplicate block '%s'", plugin_id, block["id"])
                    continue
                self.catalog.add(block, category, plugin_id)
                block_ids.append(block["id"])
        return block_ids

    def _load_disabled(self):
        try:
            disabled = json.loads(self.disabled_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            disabled = []
        except (OSError, ValueError) as error:
            logger.warning("Could not read %s: %s", self.disabled_file, error)
            disabled = []
        self.disabled = set(disabled) if isinstance(disabled, list) else set()

    # ---- state ----

    def listing(self):
        return [{**p, "enabled": p["id"] not in self.disabled} for p in self.plugins]

    def set_enabled(self, plugin_id, enabled):
        if plugin_id not in {p["id"] for p in self.plugins}:
            return False
        if enabled:
            self.disabled.discard(plugin_id)
        else:
            self.disabled.add(plugin_id)
        try:
            self.dir.mkdir(exist_ok=True)
            atomic_write_text(self.disabled_file, json.dumps(sorted(self.disabled)))
        except OSError as error:
            logger.error("Could not persist plugin state to %s: %s", self.disabled_file, error)
        logger.info("Plugin %s %s", plugin_id, "enabled" if enabled else "disabled")
        return True

    def install(self, data, filename="plugin"):
        """Validate and write a new plugin file, then load it. Returns its metadata."""
        filename = re.sub(r"[^A-Za-z0-9_-]+", "_", str(filename or "plugin").replace(".json", "")) or "plugin"
        if not isinstance(data, dict) or not isinstance(data.get("categories"), dict):
            raise ValidationError("Plugin must be a JSON object with a 'categories' map (see plugins/extras.json).")

        plugin_id = str(data.get("id") or filename)
        if plugin_id in {p["id"] for p in self.plugins}:
            raise ConflictError(f"A plugin with id '{plugin_id}' already exists. Rename its 'id' to install another.")

        target = self.dir / f"{slugify(plugin_id, 'plugin')}.json"
        try:
            self.dir.mkdir(exist_ok=True)
            if target.exists():
                raise ConflictError(f"{target.name} already exists in plugins/.")
            atomic_write_text(target, json.dumps(data, indent=2))
        except OSError as error:
            logger.exception("Could not write plugin file %s", target)
            raise ServiceError("Could not write plugin file", status=500) from error

        self.load()
        meta = next((p for p in self.plugins if p["id"] == plugin_id), None)
        logger.info("Installed plugin %s -> %s", plugin_id, target.name)
        return meta
