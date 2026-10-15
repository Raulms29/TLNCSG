"""Loading evaluated groups and organising them as query -> answers for the Review Module."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import streamlit as st


def is_true(value: Any) -> bool:
    return str(value).strip().lower() == "true"


@dataclass
class Answer:
    """One distinct answer to a query: every group (any model / mode) sharing an Output Key.

    The reviewer judges it once; the verdict applies to all its groups.
    """

    key: str
    groups: list[dict] = field(default_factory=list)  # evaluated rows + _model, _run

    @property
    def rep(self) -> dict:
        """Representative group: the largest one."""
        return max(self.groups, key=lambda g: int(g.get("Group Size") or 0))

    @property
    def runs(self) -> int:
        return sum(int(g.get("Group Size") or 0) for g in self.groups)

    @property
    def judge_verdicts(self) -> set[bool]:
        return {is_true(g.get("Correct")) for g in self.groups}


@dataclass
class Query:
    qid: str
    text: str
    answers: list[Answer] = field(default_factory=list)


@st.cache_data(show_spinner=False)
def find_evaluated_csvs(eval_dir: str) -> list[Path]:
    """All evaluated CSVs under <eval_dir>: <run>/<GRAMMAR>/<model>/Q*_evaluated.csv."""
    p = Path(eval_dir)
    if not p.is_dir():
        return []
    return sorted(p.rglob("*_evaluated.csv"))


@st.cache_data(show_spinner=False)
def _read_rows(csv_path: Path) -> list[dict[str, Any]]:
    with open(csv_path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def grammars_in(csv_files: list[Path]) -> list[str]:
    return sorted({p.parent.parent.name for p in csv_files})


def load_queries(csv_files: list[Path], grammar: str) -> list[Query]:
    """Every query of a grammar with its answers, pooled over models and thinking modes.

    Answers are ordered by number of runs (largest first).
    """
    queries: dict[str, Query] = {}
    answers: dict[tuple[str, str], Answer] = {}
    for path in csv_files:
        if path.parent.parent.name != grammar:
            continue
        for row in _read_rows(path):
            group = {**row, "_model": path.parent.name, "_run": path.parent.parent.parent.name}
            qid = row.get("QID", "")
            query = queries.setdefault(qid, Query(qid=qid, text=row.get("Query", "")))
            answer = answers.get((qid, row["Output Key"]))
            if answer is None:
                answer = answers[(qid, row["Output Key"])] = Answer(key=row["Output Key"])
                query.answers.append(answer)
            answer.groups.append(group)
    for query in queries.values():
        query.answers.sort(key=lambda a: a.runs, reverse=True)
    return list(queries.values())
