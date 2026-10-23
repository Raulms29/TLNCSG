import random
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List

from autoresearch.core.query import Query

Results = Dict[str, Dict[str, Any]]


def net_change(champion: Results, candidate: Results, query_ids: Iterable[str]) -> int:
    """Queries that went from fail to pass minus queries that went from pass to fail."""
    net = 0
    for qid in query_ids:
        before, after = champion[qid]["passed"], candidate[qid]["passed"]
        net += int(after and not before) - int(before and not after)
    return net


def mean_rate(results: Results) -> float:
    """Average share of correct runs across all queries."""
    return sum(result["rate"] for result in results.values()) / len(results) if results else 0.0


def pick_hidden(queries: List[Query], fraction: float, seed: int) -> List[str]:
    """
    Picks the queries hidden from the optimizer in one iteration, stratified by
    each query's rarest feature tag so that rare features are spread across both sides.
    """
    tag_counts = Counter(tag for query in queries for tag in query.features)
    groups = defaultdict(list)
    for query in queries:
        rarest = min(query.features, key=lambda tag: tag_counts[tag])
        groups[rarest].append(query.id)

    rng = random.Random(seed)
    hidden = []
    for tag in sorted(groups):
        ids = sorted(groups[tag])
        rng.shuffle(ids)
        hidden += ids[: round(len(ids) * fraction)]
    return sorted(hidden)


def decide(net: int, net_hidden: int, shorter: bool, mode: str, min_net_gain: int) -> bool:
    """
    Keep/discard rule for a candidate prompt:
    - never keep a change that loses on the queries hidden from the optimizer;
    - in optimize mode, keep a change that fixes at least min_net_gain more queries than it breaks;
    - in any mode, keep a shorter prompt that breaks no more queries than it fixes.
    """
    if net_hidden < 0:
        return False
    if mode == "optimize" and net >= min_net_gain:
        return True
    return net >= 0 and shorter


def word_count(text: str) -> int:
    return len(text.split())
