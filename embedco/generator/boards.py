"""Board profiles (boards.yaml)."""

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

from ..errors import DefinitionError
from .text import as_list

logger = logging.getLogger(__name__)

GENERIC_BOARD = {
    "name": "Generic Arduino",
    "adc_max": 1023,
    "pwm_max": 255,
    "vref": 5.0,
    "default_baud": 9600,
}


@dataclass(frozen=True)
class BoardSelection:
    profile: dict
    label: str
    builtins: dict
    warning: str = ""


class BoardRegistry:
    def __init__(self, path):
        self.path = Path(path)
        self.profiles = {}
        if self.path.exists():
            try:
                data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError as error:
                raise DefinitionError(f"{self.path}: invalid YAML: {error}") from error
            self.profiles = data.get("boards", {}) or {}
        else:
            logger.warning("Board file %s not found; only the generic board is available", self.path)
        logger.info("Loaded %d board profile(s) from %s", len(self.profiles), self.path)

    def resolve(self, board):
        wanted = str(board).strip().lower()
        profile = None
        for key, candidate in self.profiles.items():
            fqbns = [f.lower() for f in as_list(candidate.get("fqbn"))]
            if wanted == key.lower() or wanted in fqbns:
                profile = candidate
                break

        warning = ""
        if profile is None:
            label = str(board)
            profile = GENERIC_BOARD
            if wanted not in ("", "arduino"):
                warning = f"Unknown board '{board}', using generic Arduino defaults"
        else:
            label = f"{profile.get('name', board)} ({board})"

        builtins = {
            "adc_max": profile.get("adc_max", 1023),
            "pwm_max": profile.get("pwm_max", 255),
            "vref": profile.get("vref", 5.0),
            "default_baud": profile.get("default_baud", 9600),
        }
        return BoardSelection(profile, label, builtins, warning)

    def fqbn(self, board_id):
        """arduino-cli FQBN for a board id (first entry if the profile lists several)."""
        profile = self.profiles.get(board_id)
        if not profile:
            return None
        fqbn = profile.get("fqbn")
        if isinstance(fqbn, list):
            return fqbn[0] if fqbn else None
        return fqbn

    def summary(self):
        return [
            {"id": key, "name": p.get("name", key), "default_baud": p.get("default_baud", 9600)}
            for key, p in self.profiles.items()
        ]
