"""GrailQA dataset loader with stratified sampling."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from .base import Query, QueryDataset

logger = logging.getLogger(__name__)


class GrailQADataset(QueryDataset):
    """Loads GrailQA, filters *compositional-generalization* entries,
    deduplicates by canonical ``qid[:8]``, and performs stratified sampling
    by ``(function, num_node, num_edge)``.
    """

    def load(self) -> list[Query]:
        """Load all compositional queries, deduplicated by canonical qid."""
        with open(self._path, "r", encoding="utf-8") as f:
            raw: list[dict] = json.load(f)

        # 1. Filter compositional-generalization subset
        compositional = [e for e in raw if e.get("level") == "compositional"]
        logger.info(
            "GrailQA: %d total entries, %d compositional",
            len(raw),
            len(compositional),
        )

        # 2. Deduplicate by first 8 digits of qid (canonical logical form)
        seen_canonical: set[str] = set()
        unique: list[dict] = []
        for entry in compositional:
            canonical = str(entry["qid"])[:8]
            if canonical not in seen_canonical:
                seen_canonical.add(canonical)
                unique.append(entry)

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
        all_queries = self.load()

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


def _stratified_sample(
    df: pd.DataFrame,
    strata_cols: list[str],
    n: int,
    seed: int,
) -> list[int]:
    """Proportional stratified sampling, returning row indices from *df*.

    Each stratum gets ``max(1, round(stratum_size / total * n))`` samples.
    A final adjustment pass ensures we return exactly *n* items.
    """
    frac = n / len(df)

    sampled_groups = [
        group.sample(
            n=max(1, min(len(group), round(len(group) * frac))),
            random_state=seed,
        )
        for _, group in df.groupby(strata_cols, group_keys=False)
    ]
    sampled = pd.concat(sampled_groups) if sampled_groups else df.iloc[0:0]

    # Adjust to exactly n
    if len(sampled) > n:
        sampled = sampled.sample(n=n, random_state=seed)
    elif len(sampled) < n:
        remaining = df.drop(sampled.index)
        extra = remaining.sample(
            n=min(n - len(sampled), len(remaining)),
            random_state=seed,
        )
        sampled = pd.concat([sampled, extra])

    return sampled["idx"].tolist()
