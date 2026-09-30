"""Ambrosia dataset loader with stratified sampling."""

from __future__ import annotations

import json
import logging
import pandas as pd

from .base import Query, QueryDataset

logger = logging.getLogger(__name__)


class AmbrosiaDataset(QueryDataset):
    """Loads the Ambrosia dataset, filters out *vague* entries,
    and supports deterministic stratified sampling by ``(ambig_type, domain)``.
    """

    def load(self) -> list[Query]:
        """Load all non-vague queries from Ambrosia."""
        with open(self._path, "r", encoding="utf-8") as f:
            raw: list[dict] = json.load(f)

        # Filter out vague entries (ambiguity based on DB content, not syntax)
        filtered = [e for e in raw if e.get("ambig_type") != "vague"]
        logger.info(
            "Ambrosia: %d total entries, %d after filtering out vague",
            len(raw),
            len(filtered),
        )

        queries: list[Query] = []
        for idx, entry in enumerate(filtered, start=1):
            qid = f"AMB_{idx:04d}"
            queries.append(
                Query(
                    id=qid,
                    text=entry["ambig_question"],
                    metadata={
                        "ambig_type": entry.get("ambig_type"),
                        "domain": entry.get("domain"),
                        "interpretations": entry.get("interpretations", []),
                    },
                )
            )

        return queries

    def sample(self, n: int, seed: int = 42) -> list[Query]:
        """Stratified sample by ``(ambig_type, domain, num_interpretations)``
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
                "ambig_type": [q.metadata["ambig_type"] for q in all_queries],
                "domain": [q.metadata["domain"] for q in all_queries],
                "num_interpretations": [
                    len(q.metadata["interpretations"]) for q in all_queries
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
