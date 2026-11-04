"""Per-run generation state (one fresh instance per ``generate`` call)."""

import logging
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class GenerationState:
    includes: set = field(default_factory=set)
    libraries: set = field(default_factory=set)
    declarations: dict = field(default_factory=dict)   # ordered set of globals
    setup_map: dict = field(default_factory=dict)      # hardware init, keyed so duplicates collapse
    variables: dict = field(default_factory=dict)      # name -> type
    instances: dict = field(default_factory=dict)      # (prefix, *key) -> object name
    instance_counts: dict = field(default_factory=lambda: defaultdict(int))
    warnings: list = field(default_factory=list)
    counter: int = 0
    # board context, filled by the generator
    board: dict = field(default_factory=dict)
    board_label: str = ""
    builtins: dict = field(default_factory=dict)

    def next_id(self):
        self.counter += 1
        return self.counter

    def warn(self, message):
        if message not in self.warnings:
            logger.debug("generator warning: %s", message)
            self.warnings.append(message)
