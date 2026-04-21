from __future__ import annotations

from pathlib import Path
from typing import Any

from .defaults import DEFAULT_CRITERIA_CONFIG


def load_prompt_text(prompt_file: str | Path) -> str:
    path = Path(prompt_file)
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Prompt file is empty: {path}")
    return text


def normalize_criteria_config(
    criteria_config: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    config = criteria_config or DEFAULT_CRITERIA_CONFIG
    if not isinstance(config, dict):
        raise ValueError("criteria_config must be a dict")
    if not config:
        raise ValueError("criteria_config must define at least 1 criterion")

    normalized: dict[str, dict[str, Any]] = {}
    total_weight = 0.0

    for criterion_id, raw_cfg in config.items():
        if not isinstance(raw_cfg, dict):
            raise ValueError(f"Criterion {criterion_id} must be a dict")

        query_ids_raw = raw_cfg.get("query_ids")
        if not isinstance(query_ids_raw, (list, tuple, set)) or not query_ids_raw:
            raise ValueError(
                f"Criterion {criterion_id} must define a non-empty query_ids array"
            )
        query_ids = {
            str(query_id).strip() for query_id in query_ids_raw if str(query_id).strip()
        }
        if not query_ids:
            raise ValueError(
                f"Criterion {criterion_id} must define at least one non-empty query id"
            )

        weight = float(raw_cfg.get("weight", 0.0))
        if weight <= 0:
            raise ValueError(f"Criterion {criterion_id} must have weight > 0")
        total_weight += weight

        prompt_text = str(raw_cfg.get("system_prompt", "")).strip()
        prompt_file = str(raw_cfg.get("prompt_file", "")).strip()
        if prompt_file:
            prompt_text = load_prompt_text(prompt_file)
        if not prompt_text:
            raise ValueError(
                f"Criterion {criterion_id} must define non-empty system_prompt or prompt_file"
            )

        normalized[criterion_id] = {
            "id": criterion_id,
            "name": str(raw_cfg.get("name", criterion_id)).strip() or criterion_id,
            "weight": weight,
            "query_ids": query_ids,
            "system_prompt": prompt_text,
        }

    if total_weight <= 0:
        raise ValueError("Sum of criterion weights must be > 0")

    for criterion_id in normalized:
        normalized[criterion_id]["weight"] = (
            float(normalized[criterion_id]["weight"]) / total_weight
        )

    return normalized
