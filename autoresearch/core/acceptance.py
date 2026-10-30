from typing import Any, Dict, Iterable, List

Results = Dict[str, Dict[str, Any]]


def net_change(champion: Results, candidate: Results, query_ids: Iterable[str]) -> int:
    """Queries that went from fail to pass minus queries that went from pass to fail."""
    net = 0
    for qid in query_ids:
        before, after = champion[qid]["passed"], candidate[qid]["passed"]
        net += int(after and not before) - int(before and not after)
    return net


def mean_rate(results: Results, query_ids: List[str]) -> float:
    """Average share of correct runs across the given queries."""
    return sum(results[qid]["rate"] for qid in query_ids) / len(query_ids) if query_ids else 0.0


def word_count(text: str) -> int:
    return len(text.split())
