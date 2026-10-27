"""Ground truths of the datasets, and how each kind is shown to the judge."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class GroundTruth:
    """A query's ground truth, of one kind: "grailqa", "ambrosia" or "semgir" (the ground-truth SemGIR set)."""

    dataset: str
    # GrailQA: the s-expression with Freebase IDs replaced by friendly names
    s_expression_friendly: str | None = None
    # Ambrosia: the unambiguous readings as (meaning, SQL) pairs, and the database dump (shown to the reviewer only)
    readings: list[tuple[str, str]] = field(default_factory=list)
    db_dump: str | None = None
    # Hand-written: the SemGIR solution as JSON text
    semgir_json: str | None = None

    @property
    def num_interpretations(self) -> int:
        """How many readings an answer can cover, for Ambrosia's Hypothesis Coverage; 1 for the other kinds,
        which don't list their readings."""
        return len(self.readings) if self.dataset == "ambrosia" else 1

    def judge_sections(self) -> str:
        """The ground-truth part of the judge's message.

        Ambrosia's schema and data are left out: SemGIR is schema-independent.
        """
        if self.dataset == "ambrosia":
            readings = "\n".join(
                f"Interpretation {i}:\nMeaning: {meaning}\nSQL: {sql}\n"
                for i, (meaning, sql) in enumerate(self.readings, start=1)
            )
            return f"[GROUND TRUTH SQL]\n{readings}\n"
        if self.dataset == "semgir":
            return f"[GROUND TRUTH JSON IR]\n{self.semgir_json}\n"
        return f"[GROUND TRUTH LISP]\n{self.s_expression_friendly}\n"


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

            # The readings are the unambiguous interpretations; the "ambig" one repeats the question with every SQL
            readings = [
                (interp.get("question", ""), interp.get("gold_queries", "").strip())
                for interp in entry.get("interpretations", [])
                if interp.get("question_type") == "unambig"
            ]
            self._ambrosia[qid] = GroundTruth(
                dataset="ambrosia",
                readings=readings,
                db_dump=entry.get("db_dump", ""),
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
            # Also map the class if it differs from id and this is actually a class node
            raw_class = node.get("class", "")
            if (
                raw_class
                and raw_class != raw_id
                and friendly
                and node.get("node_type") != "entity"
            ):
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
