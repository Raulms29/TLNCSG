import json
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from ollama import Client

import utils


EVALUATOR_SYSTEM_PROMPT = """You are an expert Semantic Parsing Evaluator. Your task is to evaluate the quality of a "Candidate JSON IR" (Intermediate Representation) against a "Ground Truth JSON IR", based on the original "Natural Language Query".

You must output a similarity score between 0.0 and 1.0 representing how semantically equivalent the Candidate is to the Ground Truth, while strictly adhering to the provided Grammar.

-------------------------
GRAMMAR
-------------------------
QUERY_SET := {
  hypotheses: [HYPOTHESIS, ...]
}

HYPOTHESIS := {
  id: ID,
  query: QUERY
}
QUERY := {
  target: TYPE,
  entities?: [ENTITY, ...],
  where?: CONDITION
}
ENTITY := {
  id: ID,
  type: TYPE,
  name?: STRING
}
CONDITION := AND | OR | NOT | REL | CMP | EXISTS
AND := { and: [CONDITION, ...] }
OR := { or: [CONDITION, ...] }
NOT := { not: CONDITION }
REL := {
  rel: ROLE,
  to: ENTITY_REF,
  where?: CONDITION
}
EXISTS := {
  exists: REL
}
CMP := {
  cmp: {
    left: VALUE_EXPR,
    op: OP,
    right: VALUE_EXPR
  }
}
VALUE_EXPR := COUNT | NUMBER | ATTRIBUTE
COUNT := {
  count: REL,
  of?: ENTITY_REF
}
ATTRIBUTE := {
  attr: NAME,
  of?: ENTITY_REF
}
ENTITY_REF := ID | META_VAR
META_VAR := STRING   // e.g., "x", "y" (free variable)
OP := "=" | "!=" | ">" | "<" | ">=" | "<="
TYPE := STRING
ROLE := STRING
NAME := STRING
ID := STRING

-------------------------
EVALUATION CRITERIA
-------------------------
1. JSON Validity & Grammar Compliance (CRITICAL FILTER):
     - The Candidate MUST be valid JSON.
     - The Candidate MUST strictly follow the GRAMMAR provided above. No hallucinated keys, incorrect nesting, or unsupported operators are allowed.

2. Semantic Equivalence over Structural Identity: 
     - DO NOT penalize for different ordering of elements.
     - DO NOT penalize for valid synonymous roles (e.g., "director" vs "directed_by").
     - DO NOT penalize for valid synonymous target types (e.g., "Film" vs "Movie").
     - DO NOT penalize for partial but valid entity names (e.g., "Eastwood" vs "Clint Eastwood").
     - DO NOT penalize if the exact free variable names differ (e.g., "x" vs "y"), as long as the relational logic holds.

3. Logical Consistency:
     - Check if the constraints (`where` clauses, `cmp`, `count`) apply the exact same mathematical or logical filtering as the Ground Truth. 

4. Handling Ambiguity & Multiple Hypotheses:
     - PERFECT MATCH (Score 1.0): Exact number of valid hypotheses as Ground Truth, matching semantically.
     - PARTIAL MATCH (Score 0.5 to 0.8): If ONLY ONE hypothesis matches the Ground Truth among multiple incorrect ones, apply a penalty (e.g., -0.25) for each extra hypothesis.
     - MISSING VALID HYPOTHESIS CAP: If the Candidate generates one correct hypothesis but fails to generate another correct hypothesis that exists in the Ground Truth, the maximum allowed score is 0.85 (never 1.0).

-------------------------
SPECIFIC PENALTIES (Score Reductions)
-------------------------
- Invalid JSON / Grammar Violation (Fatal Penalty): Score is 0.0.
- Omission (Moderate/High Penalty): Missing a filter or constraint explicitly mentioned in the query.
- Type Mismatch (Critical Penalty): Assigning a nonsensical type to a correctly extracted entity.
- Unconnected Variables (High Penalty): Introducing a free variable without applying constraints to it.
- Hallucinations (High Penalty): Adding unprompted constraints or entities.
- Incorrect Logic (High Penalty): Using "and" instead of "or", which changes the mathematical result.

-------------------------
EXAMPLES
-------------------------

=== EXAMPLE 1: PERFECT MATCH (Score: 1.0) ===
[ORIGINAL NATURAL LANGUAGE QUERY]
Give me the films directed by Eastwood and starring Meryl Streep

[GROUND TRUTH JSON]
{"hypotheses": [{"id": "h1", "query": {"target": "Movie", "entities": [{"id": "e1", "type": "Person", "name": "Clint Eastwood"}, {"id": "e2", "type": "Person", "name": "Meryl Streep"}], "where": {"and": [{"rel": "director", "to": "e1"}, {"rel": "actor", "to": "e2"}]}}}]}

[CANDIDATE JSON]
{"hypotheses": [{"id": "h1", "query": {"target": "Film", "entities": [{"id": "e1", "type": "Person", "name": "Eastwood"}, {"id": "e2", "type": "Person", "name": "Meryl Streep"}], "where": {"and": [{"rel": "director", "to": "e1"}, {"rel": "starring", "to": "e2"}]}}}]}

[EXPECTED OUTPUT]
{
    "rationale": "Perfect match. 'Film' is a valid synonym for 'Movie', 'Eastwood' resolves correctly, and 'starring' is semantically identical to 'actor'. The logic perfectly mirrors the Ground Truth.",
    "score": 1.0
}

=== EXAMPLE 2: MULTIPLE HYPOTHESES PENALTY (Score: 0.75) ===
[ORIGINAL NATURAL LANGUAGE QUERY]
Give me the movies directed by Eastwood

[GROUND TRUTH JSON]
{"hypotheses": [{"id": "h1", "query": {"target": "Movie", "entities": [{"id": "e1", "type": "Person", "name": "Eastwood"}], "where": {"rel": "director", "to": "e1"}}}]}

[CANDIDATE JSON]
{"hypotheses": [{"id": "h1", "query": {"target": "Movie", "entities": [{"id": "e1", "type": "Person", "name": "Eastwood"}], "where": {"rel": "director", "to": "e1"}}}, {"id": "h2", "query": {"target": "Movie", "entities": [{"id": "e1", "type": "Person", "name": "Eastwood"}], "where": {"rel": "actor", "to": "e1"}}}]}

[EXPECTED OUTPUT]
{
    "rationale": "The Candidate found the correct hypothesis (h1), but hallucinated a second valid-looking but unprompted hypothesis (h2) showing uncertainty. A -0.25 penalty is applied.",
    "score": 0.75
}

=== EXAMPLE 3: INCORRECT LOGICAL OPERATOR (Score: 0.5) ===
[ORIGINAL NATURAL LANGUAGE QUERY]
Give me movies directed by Spielberg OR starring Tom Hanks

[GROUND TRUTH JSON]
{"hypotheses": [{"id": "h1", "query": {"target": "Movie", "entities": [{"id": "e1", "type": "Person", "name": "Spielberg"}, {"id": "e2", "type": "Person", "name": "Tom Hanks"}], "where": {"or": [{"rel": "director", "to": "e1"}, {"rel": "actor", "to": "e2"}]}}}]}

[CANDIDATE JSON]
{"hypotheses": [{"id": "h1", "query": {"target": "Movie", "entities": [{"id": "e1", "type": "Person", "name": "Spielberg"}, {"id": "e2", "type": "Person", "name": "Tom Hanks"}], "where": {"and": [{"rel": "director", "to": "e1"}, {"rel": "actor", "to": "e2"}]}}}]}

[EXPECTED OUTPUT]
{
    "rationale": "Target and entities are perfectly extracted. However, the Candidate used an 'and' operator instead of an 'or'. This is a severe logical error that fundamentally changes the query from a union to an intersection. It receives partial credit for correct entities and roles.",
    "score": 0.5
}

=== EXAMPLE 4: OMISSION AND TYPE MISMATCH (Score: 0.2) ===
[ORIGINAL NATURAL LANGUAGE QUERY]
Give me the comedies directed by Clint Eastwood

[GROUND TRUTH JSON]
{"hypotheses": [{"id": "h1", "query": {"target": "Movie", "entities": [{"id": "e1", "type": "Person", "name": "Clint Eastwood"}, {"id": "e2", "type": "Genre", "name": "Comedy"}], "where": {"and": [{"rel": "director", "to": "e1"}, {"rel": "genre", "to": "e2"}]}}}]}

[CANDIDATE JSON]
{"hypotheses": [{"id": "h1", "query": {"target": "Comedy", "entities": [{"id": "e1", "type": "Location", "name": "Clint Eastwood"}], "where": {"rel": "directed_by", "to": "e1"}}}]}

[EXPECTED OUTPUT]
{
    "rationale": "Critical errors: Missed the genre constraint entirely and classified 'Clint Eastwood' as a 'Location'. Entity types must make logical sense. Heavily penalized for fatal structural and typing mistakes.",
    "score": 0.2
}

=== EXAMPLE 5: GRAMMAR VIOLATION & COMPLETE FAILURE (Score: 0.0) ===
[ORIGINAL NATURAL LANGUAGE QUERY]
Show me the hospitals in New York

[GROUND TRUTH JSON]
{"hypotheses": [{"id": "h1", "query": {"target": "Hospital", "entities": [{"id": "e1", "type": "Location", "name": "New York"}], "where": {"rel": "located_in", "to": "e1"}}}]}

[CANDIDATE JSON]
{"hypotheses": [{"id": "h1", "query": {"target": "Person", "entities": [{"id": "e1", "type": "Organization", "name": "Show"}], "filter": {"employed_by": "e1"}}}]}

[EXPECTED OUTPUT]
{
    "rationale": "Grammar Violation: Used an unsupported 'filter' key. Semantic Failure: Hallucinated 'Person' target, misidentified 'Show' as an Organization, and missed 'New York' entirely. Zero semantic overlap.",
    "score": 0.0
}

-------------------------
OUTPUT FORMAT
-------------------------
You must return ONLY a valid JSON object with the following structure, without markdown code blocks or any other text:
{
    "rationale": "A brief explanation of the evaluation, specifically mentioning syntax checks and applied penalties.",
    "score": [Float between 0.0 and 1.0]
}"""


EVALUATOR_USER_PROMPT_TEMPLATE = """Please evaluate the following Semantic Parsing result.

[ORIGINAL NATURAL LANGUAGE QUERY]
{query_text}

[GROUND TRUTH JSON]
{ground_truth_json}

[CANDIDATE JSON]
{candidate_json}

Carefully analyze the differences, consider valid semantic variations and ambiguity in the original query, and output your evaluation strictly in the requested JSON format."""


DEFAULT_GROUND_TRUTHS = {
    "Q01": {
        "hypotheses": [
            {
                "id": "h1",
                "query": {
                    "target": "Movie",
                    "entities": [
                        {"id": "e1", "type": "Person", "name": "Clint Eastwood"},
                        {"id": "e2", "type": "Person", "name": "Meryl Streep"},
                    ],
                    "where": {
                        "and": [
                            {"rel": "director", "to": "e1"},
                            {"rel": "actor", "to": "e2"},
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


def clean_json_response(raw_text: str) -> str:
    """Normalize possible markdown-wrapped JSON from evaluator/model outputs."""
    if raw_text is None:
        return ""
    return utils._extract_json_text(str(raw_text))


safe_name = utils._safe_name


def load_ground_truths(ground_truths_path: str | None = None) -> dict[str, dict]:
    """
    Load ground truths from disk and merge with defaults.

    Expected file format:
    {
      "Q01": { ...query set... },
      "Q02": { ...query set... }
    }
    """
    merged = dict(DEFAULT_GROUND_TRUTHS)

    if not ground_truths_path:
        return merged

    path = Path(ground_truths_path)
    if not path.exists():
        raise FileNotFoundError(f"Ground truth file not found: {ground_truths_path}")

    file_data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(file_data, dict):
        raise ValueError(
            "Ground truth file must contain a JSON object keyed by query id"
        )

    for key, value in file_data.items():
        merged[str(key)] = value

    return merged


def ground_truth_to_json_text(ground_truth_obj: dict | None) -> str:
    """Serialize one ground-truth object to canonical text for prompt insertion."""
    if not ground_truth_obj:
        return "{}"
    return json.dumps(ground_truth_obj, ensure_ascii=False, indent=2)


def _find_execution_files(summary_root: str | Path) -> list[Path]:
    """Return all executions_*.csv files under a summary run folder."""
    root = Path(summary_root)
    if not root.exists():
        raise FileNotFoundError(f"Summary folder does not exist: {root}")
    return sorted(root.rglob("executions_*.csv"))


def _parse_eval_response(raw_response: str) -> tuple[float, str, str]:
    """Parse evaluator output and return (score, rationale, error)."""
    try:
        parsed = json.loads(clean_json_response(raw_response))
        score = float(parsed.get("score", 0.0))
        score = max(0.0, min(1.0, score))
        rationale = str(parsed.get("rationale", "")).strip()
        return score, rationale, ""
    except Exception as exc:
        return 0.0, "ERROR: evaluator did not return valid JSON.", str(exc)


def _evaluate_candidate(
    ollama_client: Client,
    evaluator_model: str,
    evaluator_system_prompt: str,
    query_text: str,
    ground_truth_json: str,
    candidate_json: str,
    evaluator_options: dict | None,
    evaluator_thinking: bool,
) -> tuple[float, str, str, str]:
    """Call evaluator model and parse score/rationale."""
    user_prompt = EVALUATOR_USER_PROMPT_TEMPLATE.format(
        query_text=query_text,
        ground_truth_json=ground_truth_json,
        candidate_json=candidate_json,
    )

    response = ollama_client.chat(
        model=evaluator_model,
        messages=[
            {"role": "system", "content": evaluator_system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        options=dict(evaluator_options or {}),
        think=bool(evaluator_thinking),
    )

    raw_response = response["message"]["content"]
    score, rationale, error = _parse_eval_response(raw_response)
    return score, rationale, error, raw_response


def evaluate_execution_file(
    execution_csv: str | Path,
    ollama_client: Client,
    evaluator_model: str,
    evaluator_system_prompt: str,
    ground_truths: dict[str, dict],
    evaluator_options: dict | None = None,
    evaluator_thinking: bool = False,
    test_query_ids: str | list[str] | tuple[str, ...] | set[str] | None = None,
    test_model: str | None = None,
) -> pd.DataFrame:
    """Evaluate all rows in one executions_*.csv file."""
    input_path = Path(execution_csv)
    df = pd.read_csv(input_path)

    selected_query_ids: set[str] | None = None
    if test_query_ids:
        if isinstance(test_query_ids, str):
            selected_query_ids = {test_query_ids.strip()}
        else:
            selected_query_ids = {
                str(query_id).strip()
                for query_id in test_query_ids
                if str(query_id).strip()
            }

    required_cols = {"Query ID", "Query", "Response", "Model", "Thinking"}
    missing = required_cols.difference(df.columns)
    if missing:
        raise ValueError(
            f"File {input_path} is missing required columns: {sorted(missing)}"
        )

    evaluated_rows: list[dict] = []
    for _, row in df.iterrows():
        query_id = str(row.get("Query ID", "")).strip()
        query_text = str(row.get("Query", "")).strip()
        row_model = str(row.get("Model", "")).strip()

        if selected_query_ids and query_id not in selected_query_ids:
            continue
        if test_model and row_model != str(test_model).strip():
            continue

        candidate_raw = str(row.get("Response", ""))
        candidate_json = clean_json_response(candidate_raw)

        ground_truth_obj = ground_truths.get(query_id)
        ground_truth_json = ground_truth_to_json_text(ground_truth_obj)

        score, rationale, error, eval_raw = _evaluate_candidate(
            ollama_client=ollama_client,
            evaluator_model=evaluator_model,
            evaluator_system_prompt=evaluator_system_prompt,
            query_text=query_text,
            ground_truth_json=ground_truth_json,
            candidate_json=candidate_json,
            evaluator_options=evaluator_options,
            evaluator_thinking=evaluator_thinking,
        )

        row_data = row.to_dict()
        row_data.update(
            {
                "Eval Score": score,
                "Eval Rationale": rationale,
                "Eval Error": error,
                "Eval Raw": eval_raw,
                "Ground Truth JSON": ground_truth_json,
                "Candidate JSON": candidate_json,
                "Source File": str(input_path),
            }
        )
        evaluated_rows.append(row_data)

    return pd.DataFrame(evaluated_rows)


def _aggregate_outputs(
    evaluated_df: pd.DataFrame,
    confidence_level: float = 0.95,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build grouped summaries by model/mode/query, model/mode, and query."""

    def _build_ci_frame(group_cols: list[str]) -> pd.DataFrame:
        ci_rows: list[dict] = []
        grouped = evaluated_df.groupby(group_cols, dropna=False)

        for group_key, group_df in grouped:
            if not isinstance(group_key, tuple):
                group_key = (group_key,)

            sample = np.array(group_df["Eval Score"], dtype=float)
            mean_score = float(np.mean(sample)) if sample.size else float("nan")

            if sample.size > 1:
                (ci_low, ci_high), _, _ = utils.compute_confidence_interval_with_method(
                    scores=sample,
                    confidence_level=confidence_level,
                    alpha=0.05,
                )
            else:
                ci_low, ci_high = (mean_score, mean_score)

            row = {
                col: value for col, value in zip(group_cols, group_key, strict=False)
            }
            row["95% CI (Score)"] = f"[{ci_low:.4f}, {ci_high:.4f}]"
            ci_rows.append(row)

        return pd.DataFrame(ci_rows)

    by_model_mode_query = (
        evaluated_df.groupby(["Model", "Thinking", "Query ID", "Query"], dropna=False)
        .agg(
            Runs=("Eval Score", "count"),
            Mean_Score=("Eval Score", "mean"),
            Std_Score=("Eval Score", "std"),
            Min_Score=("Eval Score", "min"),
            Max_Score=("Eval Score", "max"),
            Avg_Inference_Time_s=("Inference Time (s)", "mean"),
        )
        .reset_index()
    )

    ci_model_mode_query = _build_ci_frame(["Model", "Thinking", "Query ID", "Query"])
    by_model_mode_query = by_model_mode_query.merge(
        ci_model_mode_query,
        on=["Model", "Thinking", "Query ID", "Query"],
        how="left",
    )

    by_model_mode = (
        evaluated_df.groupby(["Model", "Thinking"], dropna=False)
        .agg(
            Total_Runs=("Eval Score", "count"),
            Overall_Score=("Eval Score", "mean"),
            Std_Score=("Eval Score", "std"),
            Min_Score=("Eval Score", "min"),
            Max_Score=("Eval Score", "max"),
            Queries_Evaluated=("Query ID", "nunique"),
        )
        .reset_index()
    )

    ci_model_mode = _build_ci_frame(["Model", "Thinking"])
    by_model_mode = by_model_mode.merge(
        ci_model_mode,
        on=["Model", "Thinking"],
        how="left",
    )

    by_query = (
        evaluated_df.groupby(["Query ID", "Query"], dropna=False)
        .agg(
            Total_Runs=("Eval Score", "count"),
            Overall_Score=("Eval Score", "mean"),
            Std_Score=("Eval Score", "std"),
            Min_Score=("Eval Score", "min"),
            Max_Score=("Eval Score", "max"),
            Models_Evaluated=("Model", "nunique"),
        )
        .reset_index()
    )

    ci_query = _build_ci_frame(["Query ID", "Query"])
    by_query = by_query.merge(
        ci_query,
        on=["Query ID", "Query"],
        how="left",
    )

    ci_col = "95% CI (Score)"
    std_col = "Std_Score"

    if ci_col in by_model_mode_query.columns and std_col in by_model_mode_query.columns:
        cols = [col for col in by_model_mode_query.columns if col != ci_col]
        cols.insert(cols.index(std_col) + 1, ci_col)
        by_model_mode_query = by_model_mode_query[cols]

    if ci_col in by_model_mode.columns and std_col in by_model_mode.columns:
        cols = [col for col in by_model_mode.columns if col != ci_col]
        cols.insert(cols.index(std_col) + 1, ci_col)
        by_model_mode = by_model_mode[cols]

    if ci_col in by_query.columns and std_col in by_query.columns:
        cols = [col for col in by_query.columns if col != ci_col]
        cols.insert(cols.index(std_col) + 1, ci_col)
        by_query = by_query[cols]

    for frame in (by_model_mode_query, by_model_mode, by_query):
        numeric_cols = frame.select_dtypes(include=["number"]).columns
        frame[numeric_cols] = frame[numeric_cols].round(4)

    return by_model_mode_query, by_model_mode, by_query


def evaluate_summary_folder(
    summary_root: str,
    evaluator_model: str,
    ollama_server: str,
    output_root: str = "outputs/query_eval",
    evaluator_options: dict | None = None,
    evaluator_thinking: bool = False,
    evaluator_system_prompt: str = EVALUATOR_SYSTEM_PROMPT,
    ground_truths_path: str | None = None,
    test_query_ids: str | list[str] | tuple[str, ...] | set[str] | None = None,
    test_query_id: str | None = None,
    test_model: str | None = None,
) -> dict[str, str | list[str] | pd.DataFrame]:
    """
    Evaluate all execution files under one summary run folder.

    Returns paths and dataframes for downstream inspection in notebook/scripts.
    """
    summary_path = Path(summary_root)
    execution_files = _find_execution_files(summary_path)

    if test_model:
        target_dir = safe_name(str(test_model))
        execution_files = [f for f in execution_files if f.parent.name == target_dir]

    if not execution_files:
        raise ValueError(
            f"No executions_*.csv files found under {summary_path} for the selected filters"
        )

    ground_truths = load_ground_truths(ground_truths_path)
    ollama_client = Client(ollama_server)

    execution_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(output_root) / execution_id
    output_dir.mkdir(parents=True, exist_ok=True)

    per_file_paths: list[str] = []
    all_frames: list[pd.DataFrame] = []
    announced_models: set[str] = set()

    for file_idx, execution_file in enumerate(execution_files, start=1):
        source_model = execution_file.parent.name
        if source_model not in announced_models:
            print(
                f"\nStarting source model: {source_model} | "
                f"Evaluator: {evaluator_model}"
            )
            announced_models.add(source_model)

        print(
            f"  - [{file_idx}/{len(execution_files)}] "
            f"Evaluating {execution_file.name}"
        )
        selected_queries = test_query_ids
        if selected_queries is None and test_query_id is not None:
            selected_queries = [test_query_id]

        evaluated_df = evaluate_execution_file(
            execution_csv=execution_file,
            ollama_client=ollama_client,
            evaluator_model=evaluator_model,
            evaluator_system_prompt=evaluator_system_prompt,
            ground_truths=ground_truths,
            evaluator_options=evaluator_options,
            evaluator_thinking=evaluator_thinking,
            test_query_ids=selected_queries,
            test_model=test_model,
        )

        if evaluated_df.empty:
            continue

        model_group = safe_name(execution_file.parent.name)
        model_output_dir = output_dir / model_group
        model_output_dir.mkdir(parents=True, exist_ok=True)

        file_out = model_output_dir / f"evaluated_{execution_file.name}"
        evaluated_df.to_csv(file_out, index=False, encoding="utf-8")
        per_file_paths.append(str(file_out))

        all_frames.append(evaluated_df)

    if not all_frames:
        raise ValueError("No rows matched the selected test filters")

    all_evaluated_df = pd.concat(all_frames, ignore_index=True)
    by_model_mode_query, by_model_mode, by_query = _aggregate_outputs(all_evaluated_df)

    all_file = output_dir / f"evaluation_all_runs_{execution_id}.csv"
    model_mode_query_file = (
        output_dir / f"evaluation_model_mode_query_{execution_id}.csv"
    )
    model_mode_file = output_dir / f"evaluation_model_mode_overall_{execution_id}.csv"
    query_file = output_dir / f"evaluation_query_overall_{execution_id}.csv"

    all_evaluated_df.to_csv(all_file, index=False, encoding="utf-8")
    by_model_mode_query.to_csv(model_mode_query_file, index=False, encoding="utf-8")
    by_model_mode.to_csv(model_mode_file, index=False, encoding="utf-8")
    by_query.to_csv(query_file, index=False, encoding="utf-8")

    # Keep full query text in CSV outputs, but return ID-focused summary tables for display.
    display_model_mode_query = by_model_mode_query.drop(
        columns=["Query"], errors="ignore"
    )
    display_query = by_query.drop(columns=["Query"], errors="ignore")

    print(f"Saved output folder: {output_dir}")

    return {
        "output_dir": str(output_dir),
        "per_file_outputs": per_file_paths,
        "all_rows_file": str(all_file),
        "model_mode_query_file": str(model_mode_query_file),
        "model_mode_file": str(model_mode_file),
        "query_file": str(query_file),
        "all_rows_df": all_evaluated_df,
        "model_mode_query_df": display_model_mode_query,
        "model_mode_df": by_model_mode,
        "query_df": display_query,
    }
