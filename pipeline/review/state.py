"""Persistence layer for review progress.

Stores review decisions in a JSON file shared by every run, one entry per
answer, identified by the group's ``Output Key`` (grammar + QID + normalized
output). A verdict given in one run is therefore reused by any later run that
produces the same answer. Saves to disk on every confirmation so progress is
never lost.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ReviewState:
    """Load, query, update and persist the review_state.json file."""

    VERSION = 2

    def __init__(self, state_path: Path):
        self._path = state_path
        self._data: dict[str, Any] = {"version": self.VERSION, "reviews": {}}
        if self._path.exists():
            self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_reviewed(self, key: str) -> bool:
        """Return True if the group identified by *key* has been reviewed."""
        return key in self._data["reviews"]

    def get_review(self, key: str) -> dict[str, Any] | None:
        """Return the stored review dict for *key*, or None."""
        return self._data["reviews"].get(key)

    def mark_reviewed(
        self,
        key: str,
        *,
        human_correct: bool,
        human_hypotheses_covered: int,
        discrepancy: bool,
        discrepancy_reason: str = "",
        error_category: str = "",
        error_notes: str = "",
        run: str = "",
        grammar: str = "",
        qid: str = "",
    ) -> None:
        """Record a review decision and persist to disk immediately.

        ``run``, ``grammar`` and ``qid`` record where the verdict was given, so a
        later run reusing it can show its provenance.
        """
        self._data["reviews"][key] = {
            "run": run,
            "grammar": grammar,
            "qid": qid,
            "human_correct": human_correct,
            "human_hypotheses_covered": human_hypotheses_covered,
            "discrepancy": discrepancy,
            "discrepancy_reason": discrepancy_reason,
            "error_category": error_category,
            "error_notes": error_notes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._save()

    def get_progress(self, keys: list[str]) -> tuple[int, int]:
        """Return (reviewed_count, total_count) for the given list of keys."""
        reviewed = sum(1 for k in keys if self.is_reviewed(k))
        return reviewed, len(keys)

    @property
    def all_reviews(self) -> dict[str, dict[str, Any]]:
        """Return the full reviews dictionary."""
        return self._data["reviews"]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> None:
        # Fail loudly instead of starting fresh: this file holds the verdicts of
        # every run, and the next save would overwrite them.
        with open(self._path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("version") != self.VERSION:
            raise ValueError(
                f"{self._path} uses review state version {data.get('version')}, expected "
                f"{self.VERSION} (reviews keyed by Output Key). Move it aside to start a new one."
            )
        self._data = data
        logger.info(
            "Loaded review state with %d entries from %s",
            len(self._data["reviews"]),
            self._path,
        )

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
