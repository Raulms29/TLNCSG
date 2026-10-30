"""Ambrosia dataset loader with stratified sampling."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .base import Query, QueryDataset, _stratified_sample

logger = logging.getLogger(__name__)

QID_PREFIX = "AMB_"


def load_ambrosia_questions(path: str | Path) -> list[dict]:
    """The ambiguous, non-vague questions of ``ambrosia.csv``, each with its unambiguous readings.

    The QID comes from the question's row in the CSV, so it doesn't depend on order or filtering.
    The readings are the unambiguous rows with the same question and database, as (question, SQL) pairs.
    """
    df = pd.read_csv(path, index_col=0)
    readings: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for row in df[df["question_type"] == "unambig"].itertuples():
        key = (str(row.ambig_question), str(row.db_file))
        readings.setdefault(key, []).append(
            (str(row.question), str(row.gold_queries).strip())
        )

    ambiguous = df[df["is_ambiguous"] & (df["ambig_type"] != "vague")]
    return [
        {
            "qid": f"{QID_PREFIX}{idx:04d}",
            "question": row.ambig_question,
            "ambig_type": row.ambig_type,
            "domain": row.domain,
            "split": row.split,
            "db_dump": row.db_dump,
            "readings": readings.get(
                (str(row.ambig_question), str(row.db_file)), []
            ),
        }
        for idx, row in zip(ambiguous.index, ambiguous.itertuples())
    ]


class AmbrosiaDataset(QueryDataset):
    """Loads the ambiguous, non-vague Ambrosia questions of one official split (``test`` or
    ``few_shot_examples``), and supports deterministic stratified sampling by
    ``(ambig_type, domain, num_interpretations)``.
    """

    def __init__(self, path: str | Path, split: str = "test"):
        super().__init__(path)
        self._split = split

    def load(self, seed: int = 42) -> list[Query]:
        """Load all non-vague queries of the split."""
        records = [
            r for r in load_ambrosia_questions(self._path) if r["split"] == self._split
        ]
        logger.info(
            "Ambrosia: %d ambiguous non-vague questions in split '%s'",
            len(records),
            self._split,
        )

        return [
            Query(
                id=r["qid"],
                text=r["question"],
                metadata={
                    "ambig_type": r["ambig_type"],
                    "domain": r["domain"],
                    "readings": r["readings"],
                },
            )
            for r in records
        ]

    def sample(self, n: int, seed: int = 42) -> list[Query]:
        """Stratified sample by ``(ambig_type, domain, num_interpretations)``
        using pandas groupby sampling.
        """
        all_queries = self.load(seed=seed)

        if n >= len(all_queries):
            logger.warning(
                "Requested %d queries but only %d available; returning all.",
                n,
                len(all_queries),
            )
            return all_queries

        # Build a DataFrame for stratified sampling
        df = pd.DataFrame(
            {
                "idx": range(len(all_queries)),
                "ambig_type": [q.metadata["ambig_type"] for q in all_queries],
                "domain": [q.metadata["domain"] for q in all_queries],
                "num_interpretations": [
                    len(q.metadata["readings"]) for q in all_queries
                ],
            }
        )
        strata_cols = ["ambig_type", "domain", "num_interpretations"]

        sampled_indices = _stratified_sample(df, strata_cols, n, seed)
        selected = [all_queries[i] for i in sampled_indices]

        n_strata = df.groupby(strata_cols).ngroups
        logger.info(
            "Ambrosia: sampled %d queries from %d strata",
            len(selected),
            n_strata,
        )
        return selected
