"""Metrics configuration loaded from a JSON file."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.evaluation.config import DatasetPaths

@dataclass
class MetricsConfig:
    """Configuration for the Metrics Module."""
    input_dir: str = "outputs/review"
    output_dir: str = "outputs/metrics"
    reference_grammar: str = "semgir"
    k_values: list[int] = field(default_factory=lambda: [1, 3, 5, 10, 30])
    dataset_paths: DatasetPaths = field(default_factory=DatasetPaths)

    @classmethod
    def from_json(cls, path: str | Path) -> MetricsConfig:
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        kwargs: dict[str, Any] = {}
        for key in ["input_dir", "output_dir", "reference_grammar", "k_values"]:
            if key in data:
                kwargs[key] = data[key]
                
        if "dataset_paths" in data:
            kwargs["dataset_paths"] = DatasetPaths.from_dict(data["dataset_paths"])

        return cls(**kwargs)
