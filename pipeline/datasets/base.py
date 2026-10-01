"""Base classes for dataset loading and query representation."""

from __future__ import annotations

import csv
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


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


@dataclass(frozen=True)
class Query:
    """A single natural language query for evaluation."""

    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class QueryDataset(ABC):
    """Abstract base for dataset loaders with deterministic sampling."""

    def __init__(self, path: str | Path):
        self._path = Path(path)
        if not self._path.exists():
            raise FileNotFoundError(f"Dataset not found: {self._path}")

    @abstractmethod
    def load(self, seed: int = 42) -> list[Query]:
        """Load and return all eligible queries from the dataset."""
        ...

    @abstractmethod
    def sample(self, n: int, seed: int = 42) -> list[Query]:
        """Return a deterministic sample of *n* queries."""
        ...

    @staticmethod
    def save_selected_queries(queries: list[Query], output_path: str | Path) -> Path:
        """Save selected queries to CSV for reproducibility reference."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "text"])
            writer.writeheader()
            for q in queries:
                writer.writerow({"id": q.id, "text": q.text})
        return path
