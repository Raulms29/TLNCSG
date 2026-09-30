"""Execution configuration loaded from a JSON file."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


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
        kwargs: dict[str, Any] = {"name": name}
        if "display_name" in data:
            kwargs["display_name"] = data["display_name"]
        else:
            kwargs["display_name"] = name
        if "enabled" in data: kwargs["enabled"] = data["enabled"]
        if "supports_thinking" in data: kwargs["supports_thinking"] = data["supports_thinking"]
        if "temperature" in data: kwargs["temperature"] = data["temperature"]
        if "grammars" in data: kwargs["grammars"] = dict(data["grammars"])
        return cls(**kwargs)


@dataclass
class DatasetConfig:
    """Configuration for dataset selection and sampling."""

    type: str  # "grailqa" or "ambrosia"
    path: str
    n_queries: int = 200
    seed: int = 42

    @classmethod
    def from_dict(cls, data: dict) -> DatasetConfig:
        kwargs = {"type": data["type"], "path": data["path"]}
        if "n_queries" in data: kwargs["n_queries"] = data["n_queries"]
        if "seed" in data: kwargs["seed"] = data["seed"]
        return cls(**kwargs)


@dataclass
class ExecutionConfig:
    """Top-level execution configuration."""

    models: list[ModelConfig]
    dataset: DatasetConfig
    ollama_host: str = "http://localhost:11434"
    ollama_options: dict[str, Any] = field(
        default_factory=lambda: {"num_predict": 3072, "num_ctx": 32768}
    )
    runs_per_model: int = 30
    output_dir: str = "outputs/execution"
    max_retries: int = 5
    retry_wait_seconds: int = 5

    @classmethod
    def from_json(cls, path: str | Path) -> ExecutionConfig:
        """Load configuration from a JSON file."""
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        models = [
            ModelConfig.from_dict(name, cfg)
            for name, cfg in data.get("models", {}).items()
        ]
        
        kwargs = {
            "models": models,
            "dataset": DatasetConfig.from_dict(data["dataset"]),
        }
        
        optional_keys = [
            "ollama_host", "ollama_options", "runs_per_model", 
            "output_dir", "max_retries", "retry_wait_seconds"
        ]
        for key in optional_keys:
            if key in data:
                kwargs[key] = data[key]

        return cls(**kwargs)

    @property
    def enabled_models(self) -> list[ModelConfig]:
        """Return only models marked as enabled."""
        return [m for m in self.models if m.enabled]

    def to_dict(self) -> dict:
        """Serialize config to a JSON-safe dictionary for manifest storage."""
        return {
            "ollama_host": self.ollama_host,
            "ollama_options": self.ollama_options,
            "runs_per_model": self.runs_per_model,
            "output_dir": self.output_dir,
            "max_retries": self.max_retries,
            "retry_wait_seconds": self.retry_wait_seconds,
            "dataset": {
                "type": self.dataset.type,
                "path": self.dataset.path,
                "n_queries": self.dataset.n_queries,
                "seed": self.dataset.seed,
            },
            "models": {
                m.name: {
                    "display_name": m.display_name,
                    "enabled": m.enabled,
                    "supports_thinking": m.supports_thinking,
                    "temperature": m.temperature,
                    "grammars": m.grammars,
                }
                for m in self.models
            },
        }
