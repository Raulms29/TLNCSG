"""Evaluation configuration loaded from a JSON file."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.config_utils import known_fields, read_json
from project_config import get_ollama_host


@dataclass
class EvaluatorModelConfig:
    """Configuration for the LLM used as the evaluator judge."""

    name: str
    temperature: float = 0.0
    supports_thinking: bool = False
    ollama_options: dict[str, Any] = field(
        default_factory=lambda: {"num_predict": 4096, "num_ctx": 16384}
    )
    # Model that retries a call whose thinking ran out of tokens without an answer
    fallback_model: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> EvaluatorModelConfig:
        return cls(**known_fields(cls, data))


@dataclass
class DatasetPaths:
    """Paths to the original dataset files for ground truth lookup."""

    ambrosia: str = "datasets/ambrosia/ambrosia.csv"
    grailqa: str = "datasets/GrailQA_v1.0/grailqa_v1.0_dev.json"
    text2cypher: str = "datasets/text2cypher_2025v1/test.parquet"

    @classmethod
    def from_dict(cls, data: dict) -> DatasetPaths:
        return cls(**known_fields(cls, data))


@dataclass
class EvaluationConfig:
    """Top-level configuration for the Evaluation Module."""

    evaluator_model: EvaluatorModelConfig
    dataset_paths: DatasetPaths = field(default_factory=DatasetPaths)
    ollama_host: str = field(default_factory=get_ollama_host)
    output_dir: str = "outputs/evaluation"
    prompts_dir: str = "prompts/evaluation"
    max_retries: int = 5
    retry_wait_seconds: int = 5
    # Grouped files evaluated at once (needs OLLAMA_NUM_PARALLEL on the server)
    parallel_requests: int = 1

    @classmethod
    def from_json(cls, path: str | Path) -> EvaluationConfig:
        data = read_json(path)
        return cls(**{
            **known_fields(cls, data),
            "evaluator_model": EvaluatorModelConfig.from_dict(data.get("evaluator_model", {"name": "gemma4:26b"})),
            "dataset_paths": DatasetPaths.from_dict(data.get("dataset_paths", {})),
        })
