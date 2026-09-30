"""Base classes for dataset loading and query representation."""

from __future__ import annotations

import csv
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
    def load(self) -> list[Query]:
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
