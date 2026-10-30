"""Ground truths of the datasets, and how each kind is shown to the judge."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.datasets.ambrosia import QID_PREFIX as AMBROSIA_QID_PREFIX, load_ambrosia_questions
from pipeline.datasets.text2cypher import QID_PREFIX as TEXT2CYPHER_QID_PREFIX, load_text2cypher_questions

logger = logging.getLogger(__name__)


@dataclass
class GroundTruth:
    """A query's ground truth, of one kind: "grailqa", "ambrosia", "text2cypher" or "semgir" (the ground-truth
    SemGIR set)."""

    dataset: str
    # GrailQA: the s-expression with Freebase IDs replaced by friendly names
    s_expression_friendly: str | None = None
    # Ambrosia: the unambiguous readings as (meaning, SQL) pairs, and the database dump (shown to the reviewer only)
    readings: list[tuple[str, str]] = field(default_factory=list)
    db_dump: str | None = None
    # Hand-written: the SemGIR solution as JSON text
    semgir_json: str | None = None
    # Text2Cypher: the Cypher query
    cypher: str | None = None

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
        if self.dataset == "text2cypher":
            return f"[GROUND TRUTH CYPHER]\n{self.cypher}\n"
        return f"[GROUND TRUTH LISP]\n{self.s_expression_friendly}\n"


class GroundTruthStore:
    """Pre-loads the datasets and provides ground truth lookup by QID."""

    def __init__(
        self,
        ambrosia_path: str | Path,
        grailqa_path: str | Path,
        text2cypher_path: str | Path | None = None,
    ):
        self._ground_truths: dict[str, dict[str, GroundTruth]] = {"ambrosia": {}, "grailqa": {}, "text2cypher": {}}

        self._load_ambrosia(Path(ambrosia_path))
        self._load_grailqa(Path(grailqa_path))
        if text2cypher_path:
            self._load_text2cypher(Path(text2cypher_path))

    def get(self, qid: str) -> GroundTruth | None:
        """Look up ground truth by QID."""
        return self._ground_truths[self.detect_dataset(qid)].get(qid)

    def detect_dataset(self, qid: str) -> str:
        """Return 'ambrosia', 'text2cypher' or 'grailqa' based on QID prefix."""
        if qid.startswith(AMBROSIA_QID_PREFIX):
            return "ambrosia"
        if qid.startswith(TEXT2CYPHER_QID_PREFIX):
            return "text2cypher"
        return "grailqa"

    # ------------------------------------------------------------------
    # Ambrosia loading
    # ------------------------------------------------------------------

    def _load_ambrosia(self, path: Path) -> None:
        if not path.exists():
            logger.warning("Ambrosia dataset not found at %s", path)
            return

        # Every split, so the store serves both the pipeline (test) and autoresearch (few_shot_examples)
        for record in load_ambrosia_questions(path):
            self._ground_truths["ambrosia"][record["qid"]] = GroundTruth(
                dataset="ambrosia",
                readings=record["readings"],
                db_dump=record["db_dump"],
            )

        logger.info("Loaded %d Ambrosia ground truth entries", len(self._ground_truths["ambrosia"]))

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
            self._ground_truths["grailqa"][str(entry["qid"])] = self.grailqa_ground_truth(entry)

        logger.info("Loaded %d GrailQA ground truth entries", len(self._ground_truths["grailqa"]))

    @classmethod
    def grailqa_ground_truth(cls, entry: dict) -> GroundTruth:
        """The ground truth of one GrailQA entry: its s-expression with Freebase IDs replaced by friendly names."""
        id_map = cls._build_id_map(entry.get("graph_query", {}))
        return GroundTruth(
            dataset="grailqa",
            s_expression_friendly=cls._replace_ids(entry.get("s_expression", ""), id_map),
        )

    @staticmethod
    def _build_id_map(graph_query: dict) -> dict[str, str]:
        """Extract a mapping of raw Freebase IDs → friendly names from nodes and edges.

        Spaces in the names become underscores, so each name stays one token of the s-expression. Literals keep
        their value without the datatype, as some dates' friendly names are spelled out ("Nov. the 30th, 2013").
        """
        id_map: dict[str, str] = {}

        for node in graph_query.get("nodes", []):
            raw_id = node.get("id", "")
            if node.get("node_type") == "literal":
                friendly = raw_id.split("^^")[0]
            else:
                friendly = node.get("friendly_name", "").replace(" ", "_")
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
            friendly = edge.get("friendly_name", "").replace(" ", "_")
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

    # ------------------------------------------------------------------
    # Text2Cypher loading
    # ------------------------------------------------------------------

    def _load_text2cypher(self, path: Path) -> None:
        if not path.exists():
            logger.warning("Text2Cypher dataset not found at %s", path)
            return

        for record in load_text2cypher_questions(path):
            self._ground_truths["text2cypher"][record["qid"]] = self.text2cypher_ground_truth(record)

        logger.info("Loaded %d Text2Cypher ground truth entries", len(self._ground_truths["text2cypher"]))

    @staticmethod
    def text2cypher_ground_truth(record: dict) -> GroundTruth:
        """The ground truth of one Text2Cypher record: its Cypher query."""
        return GroundTruth(dataset="text2cypher", cypher=record["cypher"])
