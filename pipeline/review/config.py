"""Review module configuration loaded from a JSON file."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.evaluation.error_categories import ERROR_CATEGORIES  # noqa: F401 (re-exported)


@dataclass
class DatasetPaths:
    """Paths to the original dataset files for ground truth lookup."""

    ambrosia: str = "datasets/ambrosia/ambiguous_questions_own.json"
    grailqa: str = "datasets/GrailQA_v1.0/grailqa_v1.0_dev.json"

    @classmethod
    def from_dict(cls, data: dict) -> DatasetPaths:
        return cls(**{k: data[k] for k in ["ambrosia", "grailqa"] if k in data})


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
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        kwargs: dict[str, Any] = {}

        if "dataset_paths" in data:
            kwargs["dataset_paths"] = DatasetPaths.from_dict(data["dataset_paths"])

        optional_keys = ["evaluation_dir", "output_dir", "review_state_path", "ambrosia_qid_prefix"]
        kwargs.update({k: data[k] for k in optional_keys if k in data})

        return cls(**kwargs)
