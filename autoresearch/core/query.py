from typing import Any, List, Dict, Optional
import json


class Query:
    """
    Represents a validation query with its natural language text,
    expected SemGIR solution, and logical feature tags.
    """

    def __init__(self, query_id: str, text: str, solution: Any):
        self.id = query_id
        self.text = text
        self.solution = solution
        self.features = self._derive_features(solution)

    def _derive_features(self, solution: Any) -> List[str]:
        """
        Derives structural SemGIR feature tags programmatically from the solution object
        to help the optimizer understand the tested logic without seeing the raw query data.
        """
        features = []
        if not solution:
            return features

        # Parse solution if it is a JSON string
        sol_obj = solution
        if isinstance(solution, str):
            try:
                sol_obj = json.loads(solution)
            except json.JSONDecodeError:
                sol_obj = {}
                print(
                    f"Warning: Solution for query {self.id} is not valid JSON. Using empty dict for feature extraction."
                )

        # Safely traverse the dict or list structure to check for keys
        def check_keys(data: Any, found_features: List[str]):
            if isinstance(data, dict):
                # Check for paths
                if "paths" in data and data["paths"]:
                    if "paths" not in found_features:
                        found_features.append("paths")

                # Check for aggregations
                if "aggregate_kind" in data or "list" in data:
                    if "aggregations" not in found_features:
                        found_features.append("aggregations")

                # Check for quantifiers
                if "quantifier_kind" in data:
                    if "quantifiers" not in found_features:
                        found_features.append("quantifiers")

                # Check for modifiers
                if any(k in data for k in ["order_by", "limit", "skip"]):
                    if "modifiers" not in found_features:
                        found_features.append("modifiers")

                # Check for complex constraints
                if any(k in data for k in ["and_conditions", "or_conditions"]):
                    if "complex_constraints" not in found_features:
                        found_features.append("complex_constraints")

                # Recursive check
                for v in data.values():
                    check_keys(v, found_features)
            elif isinstance(data, list):
                for item in data:
                    check_keys(item, found_features)

        found_features: List[str] = []
        check_keys(sol_obj, found_features)

        # Default tags if nothing specific was found
        if not found_features:
            # Solution must be a bare array [QUERY, ...]
            if isinstance(sol_obj, list) and len(sol_obj) > 0:
                query_block = sol_obj[0]
                if "relationships" in query_block and query_block["relationships"]:
                    found_features.append("relationships")
                elif "entities" in query_block and query_block["entities"]:
                    found_features.append("entities")
            if not found_features:
                found_features.append("simple_structures")

        return found_features

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "solution": self.solution,
            "features": self.features,
        }

    def __repr__(self) -> str:
        return f"Query(id={self.id}, features={self.features})"
