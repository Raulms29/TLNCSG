"""Helpers shared by the module configurations."""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path
from typing import Any


def read_json(path: str | Path) -> dict[str, Any]:
    """Load a JSON configuration file."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    return json.loads(config_path.read_text(encoding="utf-8"))


def known_fields(cls: type, data: dict[str, Any]) -> dict[str, Any]:
    """The entries of *data* that are fields of the dataclass *cls*; missing fields keep their defaults."""
    names = {f.name for f in fields(cls)}
    return {key: value for key, value in data.items() if key in names}
