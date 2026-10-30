from collections import defaultdict
from typing import Any, List, Dict, Iterator, Optional
from pipeline.evaluation.ground_truth import GroundTruth
import json


def _walk(data: Any) -> Iterator[Dict[str, Any]]:
    """Yields every dict nested anywhere inside a JSON-like structure."""
    if isinstance(data, dict):
        yield data
        for value in data.values():
            yield from _walk(value)
    elif isinstance(data, list):
        for item in data:
            yield from _walk(item)


def _max_hops_from_target(query: Dict[str, Any]) -> int:
    """Largest number of relationships between an entity and the nearest target of one query object."""
    relationships = [
        rel for rel in query.get("relationships") or [] if isinstance(rel, dict)
    ]
    neighbours = defaultdict(set)
    for rel in relationships:
        neighbours[rel.get("from")].add(rel.get("to"))
        neighbours[rel.get("to")].add(rel.get("from"))

    # A targeted relationship starts the search from both of its entities
    start = {target for target in query.get("target") or [] if isinstance(target, str)}
    start |= {
        end
        for rel in relationships
        if rel.get("id") in start
        for end in (rel.get("from"), rel.get("to"))
    }

    distance = {node: 0 for node in start}
    frontier = list(start)
    while frontier:
        next_frontier = []
        for node in frontier:
            for other in neighbours[node] - distance.keys():
                distance[other] = distance[node] + 1
                next_frontier.append(other)
        frontier = next_frontier
    return max(distance.values(), default=0)


def derive_features(solution: Any) -> List[str]:
    """
    Derives structural SemGIR feature tags programmatically from a solution object
    to help the optimizer understand the tested logic without seeing the raw query data.
    """
    if isinstance(solution, str):
        try:
            solution = json.loads(solution)
        except json.JSONDecodeError:
            return ["simple_structures"]
    if not solution:
        return ["simple_structures"]

    nodes = list(_walk(solution))
    relationship_ids = {
        rel["id"]
        for node in nodes
        for rel in node.get("relationships") or []
        if isinstance(rel, dict) and "id" in rel
    }

    checks = {
        "multi_hypothesis": isinstance(solution, list) and len(solution) > 1,
        "relationships": bool(relationship_ids),
        "multi_hop": any(
            _max_hops_from_target(node) >= 2 for node in nodes if "target" in node
        ),
        "relationship_attributes": any(
            node.get("of") in relationship_ids for node in nodes
        ),
        "paths": any(node.get("paths") for node in nodes),
        "aggregations": any(
            "aggregate_kind" in node or "count" in node for node in nodes
        ),
        "quantifiers": any("quantifier_kind" in node for node in nodes),
        "modifiers": any(
            k in node for node in nodes for k in ("order_by", "limit", "skip")
        ),
        "complex_constraints": any(
            k in node for node in nodes for k in ("and_conditions", "or_conditions")
        ),
        "negation": any(
            "not_condition" in node
            or node.get("operator") == "!="
            or node.get("quantifier_kind") == "NONE"
            for node in nodes
        ),
        "string_matching": any(
            node.get("operator") in ("CONTAINS", "MATCHES_REGEX") for node in nodes
        ),
    }
    features = [name for name, present in checks.items() if present]
    return features or ["simple_structures"]


class Query:
    """
    Represents a pool query: its natural language text, source dataset, split (train or val),
    ground truth for the judge, feature tags and rubric features.
    A hand-written query also keeps its SemGIR solution, from which its features are derived.
    """

    def __init__(
        self,
        query_id: str,
        text: str,
        source: str,
        split: str,
        ground_truth: GroundTruth,
        solution: Any = None,
        features: Optional[List[str]] = None,
        rubric_features: Optional[List[str]] = None,
    ):
        self.id = query_id
        self.text = text
        self.source = source
        self.split = split
        self.ground_truth = ground_truth
        self.solution = solution
        self.features = (
            derive_features(solution) if solution is not None else features or []
        )
        self.rubric_features = rubric_features or []

    def __repr__(self) -> str:
        return f"Query(id={self.id}, source={self.source}, split={self.split}, features={self.features})"
