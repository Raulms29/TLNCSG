"""Review module configuration loaded from a JSON file."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DatasetPaths:
    """Paths to the original dataset files for ground truth lookup."""

    ambrosia: str = "datasets/ambrosia/ambiguous_questions_own.json"
    grailqa: str = "datasets/GrailQA_v1.0/grailqa_v1.0_dev.json"

    @classmethod
    def from_dict(cls, data: dict) -> DatasetPaths:
        return cls(**{k: data[k] for k in ["ambrosia", "grailqa"] if k in data})


# Error categories for qualitative analysis
ERROR_CATEGORIES = [
    "Semantic omission",
    "Wrong relation",
    "Wrong variable binding",
    "Aggregation error",
    "Structural error",
    "Ambiguity/hypothesis error",
    "Hallucination",
    "Syntax/format error",
    "Other",
]


@dataclass
class ReviewConfig:
    """Top-level configuration for the Review Module."""

    evaluation_dir: str = "outputs/evaluation"
    output_dir: str = "outputs/review"
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

        optional_keys = ["evaluation_dir", "output_dir", "ambrosia_qid_prefix"]
        kwargs.update({k: data[k] for k in optional_keys if k in data})

        return cls(**kwargs)
