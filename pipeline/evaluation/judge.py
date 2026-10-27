"""The LLM judge shared by the pipeline's evaluation and autoresearch: one verdict per candidate answer."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from pipeline.clients.ollama_client import OllamaClient
from pipeline.grouping.normalizers import code_blocks
from .error_categories import canonical_category
from .ground_truth import GroundTruth

logger = logging.getLogger(__name__)

CLOSING_LINE = "Return the verdict in strict JSON format:"


@dataclass
class Verdict:
    """The judge's decision on one candidate answer."""

    correct: bool
    error_category: str  # "" when correct or when the judge failed
    rationale: str
    hypotheses_covered: int = 1
    # The judge's answer could not be read: this is not a verdict on the candidate
    judge_failed: bool = False
    # The judge model got stuck, so the fallback model gave the verdict
    used_fallback: bool = False


def build_message(question: str, ground_truth: GroundTruth, candidate: str) -> str:
    """The judge's user message. *candidate* is the extracted answer (``normalizers.extract_answer``)."""
    return "\n".join([
        f"[ORIGINAL NATURAL LANGUAGE QUERY]\n{question}\n",
        ground_truth.judge_sections(),
        f"[CANDIDATE OUTPUT]\n{candidate}\n",
        CLOSING_LINE,
    ])


class Judge:
    """Asks the judge model for a verdict on a candidate answer against its ground truth.

    The system prompt is chosen by the caller (it depends on the grammar and the dataset).
    Raises RuntimeError from the client when Ollama cannot be reached.
    """

    def __init__(
        self,
        client: OllamaClient,
        model: str,
        options: dict[str, Any],
        temperature: float,
        thinking: bool,
        fallback_model: str | None = None,
    ):
        self.client = client
        self.model = model
        self.options = options
        self.temperature = temperature
        self.thinking = thinking
        self.fallback_model = fallback_model

    def judge(self, system_prompt: str, question: str, ground_truth: GroundTruth, candidate: str) -> Verdict:
        message = build_message(question, ground_truth, candidate)
        content, done_reason = self._chat(self.model, system_prompt, message)
        # The thinking looped until num_predict: the same model at temperature 0 usually loops again
        stuck = done_reason == "length" and not content.strip()
        if stuck and self.fallback_model:
            content, _ = self._chat(self.fallback_model, system_prompt, message)
        verdict = parse_verdict(content)
        verdict.used_fallback = bool(stuck and self.fallback_model)
        return verdict

    def _chat(self, model: str, system_prompt: str, message: str) -> tuple[str, str | None]:
        content, _, _, meta = self.client.chat_with_metadata(
            model, message, system_prompt, self.options, self.temperature, self.thinking
        )
        return content, meta.get("done_reason")


# ----------------------------------------------------------------------
# Reading the judge's answer
# ----------------------------------------------------------------------


def parse_verdict(content: str) -> Verdict:
    """Reads the judge's JSON answer leniently. An unreadable answer is a judge failure, not a verdict."""
    data = _read_verdict(content)
    if data is None:
        logger.warning("Judge returned an unreadable answer. Raw: %r", content)
        return Verdict(False, "", f"Unparseable judge response: {content[:200]}", judge_failed=True)

    # The string form ("true") is accepted too
    correct = str(data.get("correct")).strip().lower() == "true"
    return Verdict(
        correct=correct,
        error_category="" if correct else _error_category(data.get("error_category")),
        rationale=str(data.get("rationale") or "").strip(),
        hypotheses_covered=_hypotheses(data.get("hypotheses_covered")),
    )


def _read_verdict(content: str) -> dict | None:
    """The verdict object, the one with "correct": the last ```json block that has it, else the whole text
    or its {...} span; as a last resort, the fields found by regex."""
    blocks = code_blocks(content, "json")
    text = content.strip()
    candidates = [*reversed(blocks), text, text[text.find("{"):text.rfind("}") + 1]]
    for candidate in candidates:
        try:
            # strict=False accepts raw newlines inside strings
            data = json.loads(candidate, strict=False)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "correct" in data:
            return data
    return _regex_fields(blocks[-1] if blocks else text)


def _regex_fields(text: str) -> dict | None:
    correct = re.search(r'"correct"\s*:\s*"?(true|false)', text, re.IGNORECASE)
    if not correct:
        return None
    category = re.search(r'"error_category"\s*:\s*"([^"]*)"', text)
    rationale = re.search(r'"rationale"\s*:\s*"(.*?)"\s*,', text, re.DOTALL)
    hypotheses = re.search(r'"hypotheses_covered"\s*:\s*(\d+)', text)
    return {
        "correct": correct.group(1),
        "error_category": category.group(1) if category else None,
        "rationale": rationale.group(1) if rationale else text,
        "hypotheses_covered": hypotheses.group(1) if hypotheses else None,
    }


def _error_category(value: Any) -> str:
    category = canonical_category(value)
    if category == "Other" and str(value or "").strip().lower() != "other":
        logger.warning("Judge returned unknown error category %r, using 'Other'.", value)
    return category


def _hypotheses(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1
