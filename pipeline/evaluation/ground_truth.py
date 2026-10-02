"""Ground truth loading and LISP preprocessing for GrailQA."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class GroundTruth:
    """Container for a single query's ground truth data."""

    dataset: str  # "ambrosia" or "grailqa"
    # GrailQA fields
    s_expression_friendly: str | None = None
    # Ambrosia fields
    db_dump: str | None = None
    gold_queries: str | None = None
    num_interpretations: int = 1


class GroundTruthStore:
    """Pre-loads both datasets and provides ground truth lookup by QID."""

    def __init__(
        self,
        ambrosia_path: str | Path,
        grailqa_path: str | Path,
        ambrosia_qid_prefix: str = "AMB_",
    ):
        self._ambrosia_qid_prefix = ambrosia_qid_prefix
        self._ambrosia: dict[str, GroundTruth] = {}
        self._grailqa: dict[str, GroundTruth] = {}

        self._load_ambrosia(Path(ambrosia_path))
        self._load_grailqa(Path(grailqa_path))

    def get(self, qid: str) -> GroundTruth | None:
        """Look up ground truth by QID."""
        if qid.startswith(self._ambrosia_qid_prefix):
            return self._ambrosia.get(qid)
        return self._grailqa.get(qid)

    def detect_dataset(self, qid: str) -> str:
        """Return 'ambrosia' or 'grailqa' based on QID prefix."""
        if qid.startswith(self._ambrosia_qid_prefix):
            return "ambrosia"
        return "grailqa"

    # ------------------------------------------------------------------
    # Ambrosia loading
    # ------------------------------------------------------------------

    def _load_ambrosia(self, path: Path) -> None:
        if not path.exists():
            logger.warning("Ambrosia dataset not found at %s", path)
            return

        with open(path, "r", encoding="utf-8") as f:
            raw: list[dict] = json.load(f)

        # Filter out vague entries (same logic as the dataset loader)
        filtered = [e for e in raw if e.get("ambig_type") != "vague"]

        for idx, entry in enumerate(filtered, start=1):
            qid = f"{self._ambrosia_qid_prefix}{idx:04d}"
            self._ambrosia[qid] = GroundTruth(
                dataset="ambrosia",
                db_dump=entry.get("db_dump", ""),
                gold_queries=entry.get("ambig_queries", ""),
                num_interpretations=len(entry.get("interpretations", [])),
            )

        logger.info("Loaded %d Ambrosia ground truth entries", len(self._ambrosia))

    # ------------------------------------------------------------------
    # GrailQA loading + LISP preprocessing
    # ------------------------------------------------------------------

    def _load_grailqa(self, path: Path) -> None:
        if not path.exists():
            logger.warning("GrailQA dataset not found at %s", path)
            return

        with open(path, "r", encoding="utf-8") as f:
            raw: list[dict] = json.load(f)

        for entry in raw:
            qid = str(entry["qid"])
            s_expr = entry.get("s_expression", "")
            graph_query = entry.get("graph_query", {})

            # Build the ID → friendly_name mapping
            id_map = self._build_id_map(graph_query)

            # Replace Freebase IDs with friendly names
            friendly_expr = self._replace_ids(s_expr, id_map)

            self._grailqa[qid] = GroundTruth(
                dataset="grailqa",
                s_expression_friendly=friendly_expr,
            )

        logger.info("Loaded %d GrailQA ground truth entries", len(self._grailqa))

    @staticmethod
    def _build_id_map(graph_query: dict) -> dict[str, str]:
        """Extract a mapping of raw Freebase IDs → friendly names from nodes and edges."""
        id_map: dict[str, str] = {}

        for node in graph_query.get("nodes", []):
            raw_id = node.get("id", "")
            friendly = node.get("friendly_name", "")
            if raw_id and friendly:
                id_map[raw_id] = friendly
            # Also map the class if it differs from id
            raw_class = node.get("class", "")
            if raw_class and raw_class != raw_id and friendly:
                id_map[raw_class] = friendly

        for edge in graph_query.get("edges", []):
            raw_relation = edge.get("relation", "")
            friendly = edge.get("friendly_name", "")
            if raw_relation and friendly:
                id_map[raw_relation] = friendly

        return id_map

    @staticmethod
    def _replace_ids(s_expression: str, id_map: dict[str, str]) -> str:
        """Replace all Freebase IDs in a LISP s-expression with their friendly names.

        Sorts by key length (longest first) to avoid partial replacements
        (e.g., replacing 'opera.opera_designer' before 'opera.opera_designer_gig').
        """
        result = s_expression
        for raw_id in sorted(id_map.keys(), key=len, reverse=True):
            result = result.replace(raw_id, id_map[raw_id])
        return result
