"""Grouping configuration loaded from a JSON file."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GrouperModelConfig:
    """Configuration for the LLM used in Phase 2 Fallback Grouping."""

    name: str
    temperature: float = 0.0
    supports_thinking: bool = False
    ollama_options: dict[str, Any] = field(
        default_factory=lambda: {"num_predict": 3072, "num_ctx": 12288}
    )

    @classmethod
    def from_dict(cls, data: dict) -> GrouperModelConfig:
        kwargs = {"name": data["name"]}
        if "temperature" in data:
            kwargs["temperature"] = data["temperature"]
        if "supports_thinking" in data:
            kwargs["supports_thinking"] = data["supports_thinking"]
        if "ollama_options" in data:
            kwargs["ollama_options"] = data["ollama_options"]
        return cls(**kwargs)


@dataclass
class GroupingConfig:
    """Top-level configuration for the Grouping Module."""

    grouper_model: GrouperModelConfig
    ollama_host: str = "http://localhost:11434"
    enable_llm_fallback: bool = True
    output_dir: str = "outputs/grouping"
    max_retries: int = 5
    retry_wait_seconds: int = 5
    llm_fallback_max_group_size: int = 1

    @classmethod
    def from_json(cls, path: str | Path) -> GroupingConfig:
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        kwargs: dict[str, Any] = {
            "grouper_model": GrouperModelConfig.from_dict(
                data.get("grouper_model", {"name": "gemma4:26b"})
            )
        }

        optional_keys = [
            "ollama_host",
            "enable_llm_fallback",
            "output_dir",
            "max_retries",
            "retry_wait_seconds",
            "llm_fallback_max_group_size",
        ]
        for key in optional_keys:
            if key in data:
                kwargs[key] = data[key]

        return cls(**kwargs)
