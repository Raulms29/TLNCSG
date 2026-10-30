"""
Prints how many ground-truth queries cover each structural feature and each rubric feature,
and checks the ground truths for format problems and near-copies of the prompt examples.

Usage: python autoresearch/tools/coverage.py
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from autoresearch.core.constants import PROJECT_ROOT
from autoresearch.core.query import derive_features

MIN_QUERIES_PER_FEATURE = 8
SIMILARITY_THRESHOLD = 0.5
QUERY_FIELDS = {
    "target",
    "entities",
    "relationships",
    "paths",
    "constraint",
    "distinct",
    "order_by",
    "limit",
    "skip",
}


def content_words(text: str) -> set:
    return {word for word in re.findall(r"[a-z0-9']+", text.lower()) if len(word) > 3}


def similarity(a: str, b: str) -> float:
    """Jaccard similarity of the content words of two sentences."""
    words_a, words_b = content_words(a), content_words(b)
    return (
        len(words_a & words_b) / len(words_a | words_b) if words_a and words_b else 0.0
    )


def format_problems(solution) -> list:
    """Lists violations of the SemGIR root structure: a flat array of query objects with grammar fields only."""
    if not isinstance(solution, list) or not all(
        isinstance(query, dict) for query in solution
    ):
        return ["the solution must be a flat array of query objects"]
    problems = []
    for query in solution:
        unknown = set(query) - QUERY_FIELDS
        if unknown:
            problems.append(f"fields not in the grammar: {sorted(unknown)}")
        if "target" not in query or "entities" not in query:
            problems.append("missing 'target' or 'entities'")
    return problems


def print_counts(title: str, counts: Counter, check_minimum: bool):
    print(f"\n{title}")
    for name, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        flag = (
            "  <- below minimum"
            if check_minimum and count < MIN_QUERIES_PER_FEATURE
            else ""
        )
        print(f"  {count:4d}  {name}{flag}")


def main():
    config = json.loads(
        (PROJECT_ROOT / "autoresearch_config.json").read_text(encoding="utf-8")
    )
    ground_truths = json.loads(
        (PROJECT_ROOT / config["pool"]["sources"]["handwritten"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    prompt = (PROJECT_ROOT / config["paths"]["generator_prompt"]).read_text(
        encoding="utf-8"
    )
    examples = [
        line.strip().strip('"')
        for line in re.findall(r"^Input:\s*(.+)$", prompt, re.MULTILINE)
    ]

    features, rubric, problems = Counter(), Counter(), []
    for qid, entry in ground_truths.items():
        features.update(derive_features(entry.get("solution")))
        rubric.update(entry.get("rubric_features", []))
        problems += [
            f"{qid}: {problem}" for problem in format_problems(entry.get("solution"))
        ]
        if not entry.get("rubric_features"):
            problems.append(f"{qid}: no rubric_features")
        for example in examples:
            if similarity(entry.get("query", ""), example) >= SIMILARITY_THRESHOLD:
                problems.append(f'{qid}: close to the prompt example "{example}"')

    print(f"Ground truth queries: {len(ground_truths)}")
    print_counts(
        "Structural features (queries per feature):", features, check_minimum=True
    )
    print_counts("Rubric features (queries per feature):", rubric, check_minimum=False)
    print("\nChecks:")
    print(
        "\n".join(f"  {problem}" for problem in problems)
        if problems
        else "  No problems found."
    )


if __name__ == "__main__":
    main()
