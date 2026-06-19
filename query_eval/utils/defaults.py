from __future__ import annotations

from typing import Any


EVALUATOR_USER_PROMPT_TEMPLATE = """Please evaluate the following Semantic Parsing result according to the previously defined method and criteria.

[ORIGINAL NATURAL LANGUAGE QUERY]
{query_text}

[{ground_truth_header}]
{ground_truth_content}

[{candidate_header}]
{candidate_content}

Carefully analyze the data and output your evaluation strictly in the requested JSON format
"""

DEFAULT_GROUND_TRUTHS: dict[str, dict[str, Any]] = {
    "Q01": {
        "hypotheses": [
            {
                "id": "h1",
                "query": {
                    "target": "Movie",
                    "entities": [{"id": "e1", "type": "Genre", "name": "Action"}],
                    "where": {
                        "and": [
                            {"rel": "genre", "to": "e1"},
                            {
                                "cmp": {
                                    "left": {"count": {"rel": "actor", "to": "a"}},
                                    "op": ">",
                                    "right": 3,
                                }
                            },
                            {
                                "exists": {
                                    "rel": "director",
                                    "to": "d",
                                    "where": {
                                        "cmp": {
                                            "left": {"attr": "birth_year", "of": "d"},
                                            "op": ">",
                                            "right": 1980,
                                        }
                                    },
                                }
                            },
                        ]
                    },
                },
            }
        ]
    },
    "Q02": {
        "hypotheses": [
            {
                "id": "h1",
                "query": {
                    "target": "Film",
                    "entities": [{"id": "e1", "type": "Award", "name": "Oscar"}],
                    "where": {
                        "exists": {
                            "rel": "actor",
                            "to": "x",
                            "where": {"rel": "won", "to": "e1"},
                        }
                    },
                },
            }
        ]
    },
    "Q03": {
        "hypotheses": [
            {
                "id": "h1",
                "query": {
                    "target": "Movie",
                    "where": {
                        "cmp": {
                            "left": {
                                "count": {
                                    "rel": "actor",
                                    "to": "x",
                                    "where": {
                                        "cmp": {
                                            "left": {"attr": "birth_year"},
                                            "op": ">",
                                            "right": 1980,
                                        }
                                    },
                                }
                            },
                            "op": ">",
                            "right": 3,
                        }
                    },
                },
            }
        ]
    },
    "Q04": {
        "hypotheses": [
            {
                "id": "h1",
                "query": {
                    "target": "Movie",
                    "where": {
                        "and": [
                            {"exists": {"rel": "director", "to": "d"}},
                            {"exists": {"rel": "actor", "to": "a"}},
                            {
                                "cmp": {
                                    "left": {"attr": "last_name", "of": "d"},
                                    "op": "=",
                                    "right": {"attr": "last_name", "of": "a"},
                                }
                            },
                        ]
                    },
                },
            }
        ]
    },
    "Q05": {
        "hypotheses": [
            {
                "id": "h1",
                "query": {
                    "target": "Movie",
                    "entities": [{"id": "e1", "type": "Country", "name": "USA"}],
                    "where": {
                        "and": [
                            {"exists": {"rel": "actor", "to": "a1"}},
                            {
                                "not": {
                                    "exists": {
                                        "rel": "actor",
                                        "to": "x",
                                        "where": {
                                            "not": {"rel": "nationality", "to": "e1"}
                                        },
                                    }
                                }
                            },
                        ]
                    },
                },
            }
        ]
    },
}


DEFAULT_CRITERIA_CONFIG: dict[str, dict[str, Any]] = {
    "A1_CS": {
        "name": "Syntactic Correctness (Well-formedness)",
        "weight": 1 / 6,
        "query_ids": ["Q01", "Q02", "Q03", "Q04", "Q05"],
        "prompt_file": "prompts/A1_CS.prompt.md",
    },
    "A2_FS": {
        "name": "Semantic Faithfulness",
        "weight": 1 / 6,
        "query_ids": ["Q01", "Q02", "Q03", "Q04", "Q05"],
        "prompt_file": "prompts/A2_FS.prompt.md",
    },
    "A3_SQ": {
        "name": "Structural Quality",
        "weight": 1 / 6,
        "query_ids": ["Q01", "Q02", "Q03", "Q04", "Q05"],
        "prompt_file": "prompts/A3_SQ.prompt.md",
    },
    "A4_HQ": {
        "name": "Hypothesis Quality",
        "weight": 1 / 6,
        "query_ids": ["Q01", "Q02", "Q03", "Q04", "Q05"],
        "prompt_file": "prompts/A4_HQ.prompt.md",
    },
    "A5_MR": {
        "name": "Minimality and Non-redundancy",
        "weight": 1 / 6,
        "query_ids": ["Q01", "Q02", "Q03", "Q04", "Q05"],
        "prompt_file": "prompts/A5_MR.prompt.md",
    },
    "A6_AP": {
        "name": "Aggregation and Projection Correctness",
        "weight": 1 / 6,
        "query_ids": ["Q01", "Q02", "Q03", "Q04", "Q05"],
        "prompt_file": "prompts/A6_AP.prompt.md",
    },
}
