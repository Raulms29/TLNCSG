"""Error categories shared by the evaluator judge and the human review."""

# Error categories for qualitative analysis. Keep in sync with the
# ERROR CATEGORIES section of the prompts in prompts/evaluation/
ERROR_CATEGORIES = [
    "Semantic omission",
    "Wrong relation",
    "Wrong variable binding",
    "Aggregation error",
    "Structural error",
    "Topology bypass",
    "Ambiguity/hypothesis error",
    "Hallucination",
    "Syntax/format error",
    "Other",
]


def canonical_category(value) -> str:
    """The canonical name of the error category a judge gave, matched without case; "Other" if unknown."""
    name = str(value or "").strip().lower()
    return next((category for category in ERROR_CATEGORIES if category.lower() == name), "Other")
