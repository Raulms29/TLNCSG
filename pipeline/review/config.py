"""Review module configuration loaded from a JSON file."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pipeline.config_utils import known_fields, read_json
from pipeline.evaluation.config import DatasetPaths


@dataclass
class ReviewConfig:
    """Top-level configuration for the Review Module."""

    evaluation_dir: str = "outputs/evaluation"
    output_dir: str = "outputs/review"
    # One review state shared by every run, so verdicts carry over between runs
    review_state_path: str = "outputs/review/review_state.json"
    dataset_paths: DatasetPaths = field(default_factory=DatasetPaths)
    ambrosia_qid_prefix: str = "AMB_"

    @classmethod
    def from_json(cls, path: str | Path) -> ReviewConfig:
        data = read_json(path)
        return cls(**{**known_fields(cls, data), "dataset_paths": DatasetPaths.from_dict(data.get("dataset_paths", {}))})
