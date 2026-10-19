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
