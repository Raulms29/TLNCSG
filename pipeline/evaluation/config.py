"""Evaluation configuration loaded from a JSON file."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EvaluatorModelConfig:
    """Configuration for the LLM used as the evaluator judge."""

    name: str
    temperature: float = 0.0
    supports_thinking: bool = False
    ollama_options: dict[str, Any] = field(
        default_factory=lambda: {"num_predict": 4096, "num_ctx": 16384}
    )

    @classmethod
    def from_dict(cls, data: dict) -> EvaluatorModelConfig:
        kwargs = {"name": data["name"]}
        if "temperature" in data:
            kwargs["temperature"] = data["temperature"]
        if "supports_thinking" in data:
            kwargs["supports_thinking"] = data["supports_thinking"]
        if "ollama_options" in data:
            kwargs["ollama_options"] = data["ollama_options"]
        return cls(**kwargs)


@dataclass
class DatasetPaths:
    """Paths to the original dataset files for ground truth lookup."""

    ambrosia: str = "datasets/ambrosia/ambiguous_questions_own.json"
    grailqa: str = "datasets/GrailQA_v1.0/grailqa_v1.0_dev.json"

    @classmethod
    def from_dict(cls, data: dict) -> DatasetPaths:
        kwargs = {}
        if "ambrosia" in data:
            kwargs["ambrosia"] = data["ambrosia"]
        if "grailqa" in data:
            kwargs["grailqa"] = data["grailqa"]
        return cls(**kwargs)


@dataclass
class EvaluationConfig:
    """Top-level configuration for the Evaluation Module."""

    evaluator_model: EvaluatorModelConfig
    dataset_paths: DatasetPaths = field(default_factory=DatasetPaths)
    ollama_host: str = "http://localhost:11434"
    output_dir: str = "outputs/evaluation"
    prompts_dir: str = "prompts/evaluation"
    max_retries: int = 5
    retry_wait_seconds: int = 5
    # Configurable prefix for dataset detection
    ambrosia_qid_prefix: str = "AMB_"

    @classmethod
    def from_json(cls, path: str | Path) -> EvaluationConfig:
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        kwargs: dict[str, Any] = {
            "evaluator_model": EvaluatorModelConfig.from_dict(
                data.get("evaluator_model", {"name": "gemma4:26b"})
            ),
        }

        if "dataset_paths" in data:
            kwargs["dataset_paths"] = DatasetPaths.from_dict(data["dataset_paths"])

        optional_keys = [
            "ollama_host",
            "output_dir",
            "prompts_dir",
            "max_retries",
            "retry_wait_seconds",
            "ambrosia_qid_prefix",
        ]
        for key in optional_keys:
            if key in data:
                kwargs[key] = data[key]

        return cls(**kwargs)
