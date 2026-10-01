"""GrailQA dataset loader with stratified sampling."""

from __future__ import annotations

import json
import logging
import random
from collections import defaultdict
from pathlib import Path

import pandas as pd

from .base import Query, QueryDataset, _stratified_sample

logger = logging.getLogger(__name__)


class GrailQADataset(QueryDataset):
    """Loads GrailQA, filters *compositional-generalization* entries,
    deduplicates by canonical ``qid[:8]``, and performs stratified sampling
    by ``(function, num_node, num_edge)``.
    """

    def load(self, seed: int = 42) -> list[Query]:
        """Load all queries, deduplicated by canonical qid randomly with a seed."""
        with open(self._path, "r", encoding="utf-8") as f:
            raw: list[dict] = json.load(f)

        logger.info(
            "GrailQA: %d total entries",
            len(raw),
        )

        # 2. Group by canonical qid[:8]
        canonical_groups = defaultdict(list)
        for entry in raw:
            canonical = str(entry["qid"])[:8]
            canonical_groups[canonical].append(entry)

        # 3. Select one paraphrase per canonical cluster
        rng = random.Random(seed)
        unique = [rng.choice(group) for group in canonical_groups.values()]

        logger.info(
            "GrailQA: %d unique canonical forms after deduplication",
            len(unique),
        )

        return [
            Query(
                id=str(entry["qid"]),
                text=entry["question"],
                metadata={
                    "function": entry.get("function", "none"),
                    "num_node": entry.get("num_node", 0),
                    "num_edge": entry.get("num_edge", 0),
                    "level": entry.get("level"),
                    "domains": entry.get("domains", []),
                },
            )
            for entry in unique
        ]

    def sample(self, n: int, seed: int = 42) -> list[Query]:
        """Stratified sample by ``(function, num_node, num_edge)``
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
                "function": [q.metadata["function"] for q in all_queries],
                "num_node": [q.metadata["num_node"] for q in all_queries],
                "num_edge": [q.metadata["num_edge"] for q in all_queries],
            }
        )
        strata_cols = ["function", "num_node", "num_edge"]

        sampled_indices = _stratified_sample(df, strata_cols, n, seed)
        selected = [all_queries[i] for i in sampled_indices]

        n_strata = df.groupby(strata_cols).ngroups
        logger.info(
            "GrailQA: sampled %d queries from %d strata", len(selected), n_strata
        )
        return selected

