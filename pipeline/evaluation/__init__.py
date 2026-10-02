"""Evaluation Module — LLM-as-a-judge for grouped outputs."""

from .config import EvaluationConfig
from .runner import EvaluationRunner

__all__ = ["EvaluationConfig", "EvaluationRunner"]
