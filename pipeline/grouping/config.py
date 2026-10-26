"""Grouping configuration loaded from a JSON file."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.config_utils import known_fields, read_json
from project_config import get_ollama_host


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
        return cls(**known_fields(cls, data))


@dataclass
class GroupingConfig:
    """Top-level configuration for the Grouping Module."""

    grouper_model: GrouperModelConfig
    ollama_host: str = field(default_factory=get_ollama_host)
    enable_llm_fallback: bool = True
    output_dir: str = "outputs/grouping"
    max_retries: int = 5
    retry_wait_seconds: int = 5
    llm_fallback_max_group_size: int = 1

    @classmethod
    def from_json(cls, path: str | Path) -> GroupingConfig:
        data = read_json(path)
        return cls(**{
            **known_fields(cls, data),
            "grouper_model": GrouperModelConfig.from_dict(data.get("grouper_model", {"name": "gemma4:26b"})),
        })
