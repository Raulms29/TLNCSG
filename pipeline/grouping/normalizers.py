"""Deterministic normalizers for LLM outputs."""

from __future__ import annotations

import json
import re


def normalize_json_output(raw_text: str) -> str:
    """Extracts JSON and normalizes it to guarantee deterministic string grouping.

    - Strips markdown code blocks.
    - Parses to a Python dict.
    - Re-serializes with sort_keys=True and no whitespace.
    """
    if not isinstance(raw_text, str) or not raw_text.strip():
        return ""

    # 1. Extract JSON (ignores surrounding conversational text). Take the LAST match.
    matches = list(re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_text, re.IGNORECASE))
    extracted_text = matches[-1].group(1) if matches else raw_text.strip()

    try:
        # 2. Parse to Python object
        parsed_json = json.loads(extracted_text)

        # 3. Forced deterministic serialization
        return json.dumps(
            parsed_json,
            sort_keys=True,  # Alphabetical order: nullifies order variations
            ensure_ascii=False,  # Retains special characters without escaping
            separators=(",", ":"),  # Eliminates spaces after commas and colons
        )
    except json.JSONDecodeError:
        # Fallback in case the model returns broken JSON.
        # Do not apply .lower() to avoid destroying semantics (e.g. Apple vs apple).
        return re.sub(r"\s+", " ", extracted_text.strip())


def normalize_code_output(raw_text: str, language: str) -> str:
    """Extracts code blocks and normalizes whitespace for deterministic grouping.

    Used for formats like SQUALL or GraphQ_Tree.
    """
    if not isinstance(raw_text, str) or not raw_text.strip():
        return ""

    pattern = rf"```(?:{language})?\s*([\s\S]*?)\s*```"
    matches = list(re.finditer(pattern, raw_text, re.IGNORECASE))
    extracted_text = matches[-1].group(1) if matches else raw_text.strip()

    # Normalize consecutive whitespace but preserve the raw semantic text
    return re.sub(r"\s+", " ", extracted_text.strip())


def normalize_output(raw_text: str, grammar: str) -> str:
    """Routes the raw text to the appropriate normalizer based on grammar."""
    grammar = grammar.lower()
    if "sem_gir" in grammar or "semgir" in grammar:
        return normalize_json_output(raw_text)
    elif "squall" in grammar:
        return normalize_code_output(raw_text, "squall")
    elif "graphq" in grammar:
        return normalize_code_output(raw_text, "graphq_tree")
    else:
        # Fallback for unknown grammars
        return normalize_code_output(raw_text, "")
