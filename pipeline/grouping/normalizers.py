"""Deterministic normalizers for LLM outputs, and the answer identity built on them."""

from __future__ import annotations

import hashlib
import json
import re

from pipeline.grammars import is_semgir


def code_blocks(text: str, language: str = r"\w+") -> list[str]:
    """The contents of the fenced code blocks of *text*, in order. *language* is the optional tag after the fence."""
    return re.findall(rf"```(?:{language})?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)


def last_code_block(text: str, language: str = r"\w+") -> str:
    """The last fenced code block of *text* (a model may correct itself), or the whole text if there is none."""
    blocks = code_blocks(text, language)
    return blocks[-1] if blocks else text.strip()


def normalize_json_output(raw_text: str) -> str:
    """Extracts JSON and normalizes it to guarantee deterministic string grouping.

    - Strips markdown code blocks.
    - Parses to a Python dict.
    - Re-serializes with sort_keys=True and no whitespace.
    """
    if not isinstance(raw_text, str) or not raw_text.strip():
        return ""

    # 1. Extract JSON (ignores surrounding conversational text). Take the LAST block.
    extracted_text = last_code_block(raw_text, "json")

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

    Used for formats like SQUALL or GraphQ IR.
    """
    if not isinstance(raw_text, str) or not raw_text.strip():
        return ""

    extracted_text = last_code_block(raw_text, language or r"\w+")

    # Normalize consecutive whitespace but preserve the raw semantic text
    return re.sub(r"\s+", " ", extracted_text.strip())


def normalize_output(raw_text: str, grammar: str) -> str:
    """Routes the raw text to the appropriate normalizer based on grammar."""
    if is_semgir(grammar):
        return normalize_json_output(raw_text)
    else:
        # Default for any other code-like grammar (SQUALL, GraphQ IR, etc)
        return normalize_code_output(raw_text, "")


# --------------------------------------------------------------------------
# Answer identity
# --------------------------------------------------------------------------


def output_key(grammar: str, qid: str, normalized: str) -> str:
    """Stable identity of an answer: the same normalized output to the same query
    under the same grammar always gets the same key, across models and runs.

    Human review verdicts are stored under this key so they can be reused.
    """
    raw = f"{grammar}|{qid}|{normalized}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]
