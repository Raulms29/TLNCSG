"""Metrics configuration loaded from a JSON file."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pipeline.config_utils import known_fields, read_json
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
        data = read_json(path)
        return cls(**{**known_fields(cls, data), "dataset_paths": DatasetPaths.from_dict(data.get("dataset_paths", {}))})
