"""Execution configuration loaded from a JSON file."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pipeline.config_utils import known_fields, read_json
from project_config import get_ollama_host


@dataclass
class ModelConfig:
    """Configuration for a single LLM under evaluation."""

    name: str
    display_name: str
    enabled: bool = True
    supports_thinking: bool = False
    temperature: float = 0.0
    grammars: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, name: str, data: dict) -> ModelConfig:
        return cls(**{"display_name": name, **known_fields(cls, data), "name": name})


@dataclass
class DatasetConfig:
    """Configuration for dataset selection and sampling."""

    type: str  # "grailqa" or "ambrosia"
    path: str
    n_queries: int = 200
    seed: int = 42

    @classmethod
    def from_dict(cls, data: dict) -> DatasetConfig:
        return cls(**known_fields(cls, data))


@dataclass
class ExecutionConfig:
    """Top-level execution configuration."""

    models: list[ModelConfig]
    dataset: DatasetConfig
    ollama_host: str = field(default_factory=get_ollama_host)
    ollama_options: dict[str, Any] = field(
        default_factory=lambda: {"num_predict": 3072, "num_ctx": 32768}
    )
    runs_per_model: int = 30
    # Repetitions of a query sent to Ollama at once (needs OLLAMA_NUM_PARALLEL on the server).
    # Values > 1 raise the recorded per-request inference time: compare only runs with the same value.
    parallel_requests: int = 1
    output_dir: str = "outputs/execution"
    max_retries: int = 5
    retry_wait_seconds: int = 5

    @classmethod
    def from_json(cls, path: str | Path) -> ExecutionConfig:
        """Load configuration from a JSON file."""
        data = read_json(path)
        return cls(**{
            **known_fields(cls, data),
            "models": [ModelConfig.from_dict(name, cfg) for name, cfg in data.get("models", {}).items()],
            "dataset": DatasetConfig.from_dict(data["dataset"]),
        })

    @property
    def enabled_models(self) -> list[ModelConfig]:
        """Return only models marked as enabled."""
        return [m for m in self.models if m.enabled]

    def to_dict(self) -> dict:
        """Serialize config to a JSON-safe dictionary for manifest storage, models keyed by name."""
        data = asdict(self)
        data["models"] = {model.pop("name"): model for model in data["models"]}
        return data
