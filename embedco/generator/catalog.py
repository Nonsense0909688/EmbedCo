"""The block catalog: every known block, its category and owning plugin."""

import logging
from collections import defaultdict
from pathlib import Path

import yaml

from ..errors import DefinitionError

logger = logging.getLogger(__name__)

PALETTE_KEYS = ("id", "name", "description", "inputs", "defaults", "output", "control", "unit")


class BlockCatalog:
    def __init__(self):
        self.blocks = {}      # id -> definition
        self.category = {}    # id -> category name
        self.plugin = {}      # id -> plugin id ("" for built-ins)

    def add(self, block, category, plugin_id=""):
        block_id = block["id"]
        if block_id in self.blocks:
            raise DefinitionError(f"Duplicate block id: {block_id}")
        self.blocks[block_id] = block
        self.category[block_id] = category
        self.plugin[block_id] = plugin_id

    def __contains__(self, block_id):
        return block_id in self.blocks

    @classmethod
    def from_definitions(cls, path):
        """Load blocks/categories/*.yaml (or a legacy single blocks.yaml)."""
        path = Path(path)
        catalog = cls()
        if path.is_dir():
            seen = set()
            for category_file in sorted(path.glob("categories/*.yaml")):
                try:
                    data = yaml.safe_load(category_file.read_text(encoding="utf-8")) or {}
                except yaml.YAMLError as error:
                    raise DefinitionError(f"{category_file}: invalid YAML: {error}") from error
                category = data.get("category") or category_file.stem
                blocks = data.get("blocks", [])
                if not isinstance(blocks, list):
                    raise DefinitionError(f"{category_file}: 'blocks' must be a list")
                if category in seen:
                    raise DefinitionError(f"Duplicate block category: {category}")
                seen.add(category)
                for block in blocks:
                    catalog.add(block, category)
        else:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for category, blocks in data["categories"].items():
                for block in blocks:
                    catalog.add(block, category)
        logger.info("Loaded %d built-in block(s) from %s", len(catalog.blocks), path)
        return catalog

    def palette(self, disabled_plugins=()):
        """Blocks grouped by category, ready for JSON.

        Hidden blocks and blocks of disabled plugins are omitted; generation
        still accepts them so old projects keep building.
        """
        palette = defaultdict(list)
        for block_id, block in self.blocks.items():
            if block.get("hidden"):
                continue
            plugin = self.plugin.get(block_id, "")
            if plugin and plugin in disabled_plugins:
                continue
            palette[self.category[block_id]].append({k: block[k] for k in PALETTE_KEYS if k in block})
        return dict(palette)
