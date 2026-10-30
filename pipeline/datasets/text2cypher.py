"""Text2Cypher (Neo4j, 2025v1) dataset loader with stratified sampling."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from .base import Query, QueryDataset, _stratified_sample

logger = logging.getLogger(__name__)

QID_PREFIX = "T2C_"

# Sources left out: write-operation how-tos, cyspider translations labelled incorrect, and templates with
# placeholders such as %country%
EXCLUDED_SOURCES = {
    "20250307_datacleanup",
    "cyspider_t5base_incorrect",
    "cyspider_t5base_prefix_incorrect",
    "cyspider_t5base_finetune_incorrect",
    "hf_vedana17_train",
}
WRITE_CLAUSE = re.compile(
    r"\b(CREATE|DELETE|DETACH|MERGE|SET|REMOVE|DROP)\b", re.IGNORECASE
)

# Construct tags of a Cypher query: (tag, pattern)
CYPHER_FEATURES = [
    ("aggregation", r"\b(count|sum|avg|min|max|stdev|percentile\w*)\s*\("),
    ("order_by", r"\bORDER\s+BY\b"),
    ("limit", r"\bLIMIT\b"),
    ("skip", r"\bSKIP\b"),
    ("distinct", r"\bDISTINCT\b"),
    ("var_length_path", r"\[[^\]]*\*[^\]]*\]"),
    ("shortest_path", r"\b(all)?shortestPath\s*\("),
    ("path_variable", r"\b\w+\s*=\s*(\(|(all)?shortestPath)"),
    ("optional_match", r"\bOPTIONAL\s+MATCH\b"),
    ("collect", r"\bcollect\s*\("),
    ("unwind", r"\bUNWIND\b"),
    (
        "list_index_slice",
        r"\]\s*\[\s*-?\d*\s*(\.\.\s*-?\d*)?\s*\]|\)\s*\[\s*-?\d+\s*\]|\w\[\s*-?\d+\s*(\.\.\s*-?\d*)?\s*\]",
    ),
    ("negation", r"\bNOT\b|<>"),
    ("union", r"\bUNION\b"),
    ("exists_or_subquery", r"\bEXISTS\s*[\{\(]|\bCALL\s*\{|\bCOUNT\s*\{"),
    ("with_stage", r"\bWITH\b"),
]


def cypher_features(cypher: str) -> list[str]:
    """The constructs a Cypher query uses, as tags."""
    tags = [
        tag
        for tag, pattern in CYPHER_FEATURES
        if re.search(pattern, cypher, re.IGNORECASE)
    ]
    if len(re.findall(r"\bMATCH\b", cypher, re.IGNORECASE)) >= 2:
        tags.append("multiple_match")
    # A relationship variable (e.g. [r:ACTED_IN]) named on its own in the RETURN clause
    rel_vars = set(re.findall(r"\[\s*(\w+)\s*[:\]\*]", cypher))
    returned = re.split(r"\bRETURN\b", cypher, flags=re.IGNORECASE)
    if len(returned) > 1 and any(
        re.search(rf"(?<![\w.]){re.escape(v)}(?![\w.(])", returned[-1])
        for v in rel_vars
    ):
        tags.append("relationship_returned")
    return tags


def normalize_question(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).strip().lower())


def load_text2cypher_questions(path: str | Path) -> list[dict]:
    """Every row of one Text2Cypher split file, with its Cypher's literal ``\\n`` turned into newlines.

    The QID is ``T2C_`` plus the number of the row's ``instance_id``, unique across splits.
    """
    df = pd.read_parquet(
        path,
        columns=[
            "question",
            "cypher",
            "data_source",
            "instance_id",
            "database_reference_alias",
        ],
    )
    return [
        {
            "qid": f"{QID_PREFIX}{str(row.instance_id).removeprefix('instance_id_')}",
            "question": row.question,
            "cypher": str(row.cypher).replace("\\n", "\n"),
            "data_source": row.data_source,
            "database": row.database_reference_alias,
        }
        for row in df.itertuples()
    ]


class Text2CypherDataset(QueryDataset):
    """Loads one Text2Cypher split file without the excluded sources and write queries, keeps one row per
    question, and performs stratified sampling by ``data_source``.

    ``exclude_questions_from`` names another split file whose questions are left out, so a sample from train
    shares no question with test.
    """

    def __init__(
        self, path: str | Path, exclude_questions_from: str | Path | None = None
    ):
        super().__init__(path)
        self._exclude_path = (
            Path(exclude_questions_from) if exclude_questions_from else None
        )

    def load(self, seed: int = 42) -> list[Query]:
        """Load the eligible queries, one per normalized question, chosen with a seed."""
        records = [
            r
            for r in load_text2cypher_questions(self._path)
            if r["data_source"] not in EXCLUDED_SOURCES
            and not WRITE_CLAUSE.search(r["cypher"])
        ]
        logger.info(
            "Text2Cypher: %d rows without the excluded sources and write queries",
            len(records),
        )

        if self._exclude_path:
            excluded = {
                normalize_question(r["question"])
                for r in load_text2cypher_questions(self._exclude_path)
            }
            records = [
                r for r in records if normalize_question(r["question"]) not in excluded
            ]
            logger.info(
                "Text2Cypher: %d rows after excluding the questions of %s",
                len(records),
                self._exclude_path.name,
            )

        df = pd.DataFrame(records).sample(frac=1, random_state=seed)
        df = df[~df["question"].map(normalize_question).duplicated()]
        logger.info("Text2Cypher: %d unique questions after deduplication", len(df))

        return [
            Query(
                id=str(row.qid),
                text=str(row.question),
                metadata={"data_source": row.data_source, "cypher": row.cypher},
            )
            for row in df.itertuples()
        ]

    def sample(self, n: int, seed: int = 42) -> list[Query]:
        """Stratified sample by ``data_source`` using pandas groupby sampling."""
        all_queries = self.load(seed=seed)

        if n >= len(all_queries):
            logger.warning(
                "Requested %d queries but only %d available; returning all.",
                n,
                len(all_queries),
            )
            return all_queries

        df = pd.DataFrame(
            {
                "idx": range(len(all_queries)),
                "data_source": [q.metadata["data_source"] for q in all_queries],
            }
        )
        sampled_indices = _stratified_sample(df, ["data_source"], n, seed)
        selected = [all_queries[i] for i in sampled_indices]

        logger.info(
            "Text2Cypher: sampled %d queries from %d sources",
            len(selected),
            df["data_source"].nunique(),
        )
        return selected
