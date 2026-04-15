import json
import re
import itertools
from pathlib import Path
from difflib import SequenceMatcher
from statistics import mean
from datetime import datetime
from typing import Any
import numpy as np
import pandas as pd
from scipy.stats import norm, t


def _extract_json_text(text: str) -> str:
    """Extract JSON content, preferring fenced ```json blocks when present."""
    match = re.search(
        r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL
    )
    if match:
        return match.group(1).strip()
    return text.strip()


def _format_json_response(text: str, indent: int = 2) -> str:
    """Parse and re-serialize JSON for consistent formatting."""
    raw_json = _extract_json_text(text)
    parsed = json.loads(raw_json)
    return json.dumps(parsed, ensure_ascii=False, indent=indent)


def canonicalize_response(text: str) -> str:
    """Normalize response text to compare semantic content consistently."""
    try:
        parsed = json.loads(_format_json_response(text))
        return json.dumps(parsed, sort_keys=True, separators=(",", ":"))
    except Exception:
        return " ".join(text.split())


def variability_percent(responses: list[str]) -> float:
    """Variability = (1 - average pairwise similarity) * 100."""
    if len(responses) < 2:
        return 0.0

    canonical = [canonicalize_response(r) for r in responses]
    pairs = list(itertools.combinations(canonical, 2))
    similarities = [SequenceMatcher(None, a, b).ratio() for a, b in pairs]
    return (1.0 - mean(similarities)) * 100.0


def unique_responses_percent(responses: list[str]) -> float:
    """Return percentage of unique canonicalized responses."""
    if not responses:
        return 0.0
    unique = len(set(canonicalize_response(r) for r in responses))
    return (unique / len(responses)) * 100.0


def select_closest_below_threshold(
    results: list[dict], threshold: float, variability_key: str = "variability_pct"
) -> dict | None:
    """Choose result with variability below threshold and closest to it."""
    valid = [r for r in results if r.get(variability_key, float("inf")) < threshold]
    if not valid:
        return None
    return min(valid, key=lambda r: threshold - float(r[variability_key]))


def build_chat_messages(system_prompt: str, query: str) -> list[dict[str, str]]:
    """Build standard system+user messages for a single query."""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query},
    ]


def call_ollama(
    ollama_client: Any,
    model_name: str,
    query: str,
    system_prompt: str,
    options: dict | None = None,
    thinking: bool = False,
    format_json: bool = False,
) -> str:
    """Generic Ollama server call used across the project."""
    response = ollama_client.chat(
        model=model_name,
        messages=build_chat_messages(system_prompt, query),
        options=dict(options or {}),
        think=thinking,
    )
    content = response["message"]["content"]
    return _format_json_response(content) if format_json else content


def run_ollama_once(
    ollama_client: Any,
    model_name: str,
    query: str,
    system_prompt: str,
    base_options: dict,
    temperature: float,
    thinking: bool = False,
) -> str:
    """Run one Ollama chat call and return raw message content."""
    options = dict(base_options)
    options["temperature"] = float(temperature)
    return call_ollama(
        ollama_client=ollama_client,
        model_name=model_name,
        query=query,
        system_prompt=system_prompt,
        options=options,
        thinking=thinking,
        format_json=False,
    )


def run_ollama_once_with_metadata(
    ollama_client: Any,
    model_name: str,
    query: str,
    system_prompt: str,
    base_options: dict,
    temperature: float,
    thinking: bool = False,
) -> tuple[str, float, dict]:
    """
    Run one Ollama chat call and return content with metadata-based duration.

    Duration is taken from Ollama response fields (no manual timing).
    """
    options = dict(base_options)
    options["temperature"] = float(temperature)
    response = ollama_client.chat(
        model=model_name,
        messages=build_chat_messages(system_prompt, query),
        options=options,
        think=thinking,
    )
    content = response["message"]["content"]

    total_ns = int(response.get("total_duration", 0) or 0)
    prompt_eval_ns = int(response.get("prompt_eval_duration", 0) or 0)
    eval_ns = int(response.get("eval_duration", 0) or 0)
    inference_ns = total_ns if total_ns > 0 else (prompt_eval_ns + eval_ns)
    inference_seconds = float(inference_ns) / 1_000_000_000.0

    return content, inference_seconds, response


def evaluate_temperature_candidates(
    ollama_client: Any,
    model_name: str,
    query: str,
    system_prompt: str,
    base_options: dict,
    temperature_candidates: list[float],
    runs_per_temperature: int,
    variability_threshold: float,
    thinking: bool = False,
) -> list[dict]:
    """Evaluate variability metrics for each candidate temperature."""
    results: list[dict] = []

    for temp in temperature_candidates:
        samples = [
            run_ollama_once(
                ollama_client=ollama_client,
                model_name=model_name,
                query=query,
                system_prompt=system_prompt,
                base_options=base_options,
                temperature=temp,
                thinking=thinking,
            )
            for _ in range(runs_per_temperature)
        ]

        var_pct = variability_percent(samples)
        unique_pct = unique_responses_percent(samples)

        results.append(
            {
                "temperature": temp,
                "variability_pct": round(var_pct, 2),
                "unique_responses_pct": round(unique_pct, 2),
                "meets_threshold": var_pct <= variability_threshold,
            }
        )

    return results


def print_temperature_evaluation(
    model_name: str, query: str, threshold: float, results: list[dict]
) -> None:
    """Pretty-print temperature evaluation metrics and recommendation."""
    print(build_temperature_evaluation_report(model_name, query, threshold, results))


def build_temperature_evaluation_report(
    model_name: str, query: str, threshold: float, results: list[dict]
) -> str:
    """Build a text report for one model's temperature evaluation."""
    lines = [
        f"Model: {model_name}",
        f"Query: {query}",
        f"Threshold: variability <= {threshold}%",
        "",
        "Results by temperature:",
    ]

    for result in results:
        status = "OK" if result["meets_threshold"] else "NO"
        lines.append(
            f"- T={result['temperature']}: variability={result['variability_pct']}% | "
            f"unique={result['unique_responses_pct']}% | under_threshold={status}"
        )

    recommended = select_closest_below_threshold(results, threshold)
    if recommended is not None:
        lines.append("")
        lines.append(
            "Recommended temperature (closest variability below threshold): "
            f"{recommended['temperature']} with variability={recommended['variability_pct']}%"
        )
    else:
        lines.append("")
        lines.append(
            "No candidate temperature achieved variability under the threshold."
        )

    return "\n".join(lines)


def save_temperature_report(output_dir: str, model_name: str, report_text: str) -> str:
    """Save one model temperature report and return the saved file path."""
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", model_name).strip("_")
    file_path = Path(output_dir) / f"{safe_name}.txt"
    file_path.write_text(report_text, encoding="utf-8")
    return str(file_path)


def confidence_interval(
    sample: np.ndarray, confidence_level: float = 0.95
) -> tuple[float, float]:
    """
    Compute the confidence interval for a given sample, with two distributions: normal and student.
    :param sample: The sample to compute the confidence interval.
    :param confidence_level: The confidence level (default is 0.95).
    :return: A tuple with the lower and upper bounds of the confidence interval.
    """
    alpha = 1 - confidence_level
    mean = np.mean(sample)
    std = np.std(sample)
    n = len(sample)
    if n > 30:
        # normal distribution
        z = norm.ppf(1 - alpha / 2)
        return mean - z * std / np.sqrt(n), mean + z * std / np.sqrt(n)
    else:
        # student distribution
        t_value = t.ppf(1 - alpha / 2, n - 1)
        return mean - t_value * std / np.sqrt(n), mean + t_value * std / np.sqrt(n)


def compute_confidence_interval_adaptive(
    scores: np.ndarray,
    confidence_level: float = 0.95,
    method: str = "auto",
    verbose: bool = True,
) -> tuple[float, float]:
    """
    Compute confidence interval using appropriate method.

    Args:
        scores: array of scores
        confidence_level: confidence level (default 0.95)
        method: 'auto', 'parametric', or 'bootstrap'
        verbose: whether to print method selection info

    Returns:
        tuple: (lower_bound, upper_bound) of the confidence interval
    """
    from scipy.stats import shapiro

    scores = np.array(scores)

    if method == "auto":
        # Test for normality using Shapiro-Wilk test
        _, p_value = shapiro(scores)
        is_normal = p_value > 0.05
        method = "parametric" if is_normal else "bootstrap"
        if verbose:
            print(f"  Normality test p-value: {p_value:.4f} → Using {method} method")

    if method.lower() == "parametric":
        # Use t-distribution (existing method)
        return confidence_interval(scores, confidence_level)
    else:
        # Use bootstrap (percentile method)
        alpha = 1 - confidence_level
        lower_percentile = (alpha / 2) * 100
        upper_percentile = (1 - alpha / 2) * 100
        return (
            np.percentile(scores, lower_percentile),
            np.percentile(scores, upper_percentile),
        )


def select_ci_method_by_normality(
    scores: np.ndarray, alpha: float = 0.05
) -> tuple[str, float]:
    """Pick CI method based on Shapiro-Wilk normality test."""
    from scipy.stats import shapiro

    arr = np.array(scores)
    if arr.size < 3:
        return "parametric", float("nan")

    _, p_value = shapiro(arr)
    method = "parametric" if p_value > alpha else "bootstrap"
    return method, float(p_value)


def compute_confidence_interval_with_method(
    scores: np.ndarray,
    confidence_level: float = 0.95,
    alpha: float = 0.05,
) -> tuple[tuple[float, float], str, float]:
    """Compute CI after selecting method via Shapiro-Wilk normality test."""
    method, p_value = select_ci_method_by_normality(scores, alpha=alpha)
    ci = compute_confidence_interval_adaptive(
        scores=scores,
        confidence_level=confidence_level,
        method=method,
        verbose=False,
    )
    return ci, method, p_value


def do_intervals_overlap(
    interval1: tuple[float, float], interval2: tuple[float, float]
) -> bool:
    """
    Check if two intervals overlap.
    :param interval1: The first interval.
    :param interval2: The second interval.
    :return: Whether the intervals overlap or not.
    """
    return interval1[1] >= interval2[0] and interval1[0] <= interval2[1]


def is_valid_json_response(text: str) -> bool:
    """Return whether response text contains valid JSON payload."""
    try:
        json.loads(_extract_json_text(text))
        return True
    except Exception:
        return False


def is_strict_json_only_response(text: str) -> bool:
    """Return whether response is JSON-only, raw or as a pure ```json fenced block."""
    payload = text.strip()
    if not payload:
        return False

    # Case 1: Raw JSON only.
    try:
        json.loads(payload)
        return True
    except Exception:
        pass

    # Case 2: Exactly one fenced json block and nothing else.
    fenced_match = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```", payload, flags=re.IGNORECASE | re.DOTALL
    )
    if not fenced_match:
        return False

    try:
        json.loads(fenced_match.group(1).strip())
        return True
    except Exception:
        return False


def _safe_name(name: str) -> str:
    """Build filesystem-safe name from model string."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")


def _safe_query_name(query: str, max_len: int = 40) -> str:
    """Build compact filesystem-safe slug for query text."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", query).strip("_")
    return safe[:max_len] if len(safe) > max_len else safe


def compute_model_mode_metrics(
    ollama_client: Any,
    model_name: str,
    model_config: dict,
    queries: list[str],
    system_prompt: str,
    base_options: dict,
    runs_per_model: int,
    thinking: bool,
    query_id: str | None = None,
    confidence_level: float = 0.95,
) -> tuple[dict, list[dict]]:
    """Compute summary metrics for one model and one run mode."""
    inference_times: list[float] = []
    valid_json_count = 0
    execution_records: list[dict] = []

    temperature = float(model_config["temperature"])
    for run_idx in range(1, runs_per_model + 1):
        for query in queries:
            response, inference_seconds, response_meta = run_ollama_once_with_metadata(
                ollama_client=ollama_client,
                model_name=model_name,
                query=query,
                system_prompt=system_prompt,
                base_options=base_options,
                temperature=temperature,
                thinking=thinking,
            )

            is_valid_json = is_valid_json_response(response)
            inference_times.append(inference_seconds)
            if is_valid_json:
                valid_json_count += 1

            execution_records.append(
                {
                    "Run": run_idx,
                    "Query ID": query_id,
                    "Query": query,
                    "Model": model_name,
                    "Thinking": bool(thinking),
                    "Temperature": temperature,
                    "Inference Time (s)": round(inference_seconds, 6),
                    "Valid JSON": is_valid_json,
                    "Done Reason": response_meta.get("done_reason"),
                    "Prompt Eval Count": response_meta.get("prompt_eval_count"),
                    "Eval Count": response_meta.get("eval_count"),
                    "Response": response,
                }
            )

    sample = np.array(inference_times, dtype=float)
    mean_time = float(np.mean(sample)) if sample.size else float("nan")
    # Use sample standard deviation (ddof=1) for better estimate with the samples and not the whole population
    std_time = float(np.std(sample, ddof=1)) if sample.size > 1 else 0.0

    if sample.size > 1:
        (ci_low, ci_high), _, _ = compute_confidence_interval_with_method(
            scores=sample,
            confidence_level=confidence_level,
            alpha=0.05,
        )
    else:
        ci_low, ci_high = (mean_time, mean_time)

    total_calls = runs_per_model * len(queries)
    valid_json_rate = (valid_json_count / total_calls) * 100 if total_calls else 0.0

    metrics_row = {
        "Query ID": query_id,
        "Name": model_config.get("display_name", model_name),
        "Parameters": model_config.get("parameters", "N/A"),
        "Thinking": bool(thinking),
        "Temperature": temperature,
        "Valid JSON Rate": round(valid_json_rate, 2),
        "Avg IT (s)": round(mean_time, 4),
        "Std Dev IT (s)": round(std_time, 4),
        "95% CI (IT)": f"[{ci_low:.4f}, {ci_high:.4f}]",
        "G_Cypher": model_config.get("g_cypher"),
        "G_Sparql": model_config.get("g_sparql"),
    }

    return metrics_row, execution_records


def _normalize_query_defs(queries: list[dict]) -> list[dict[str, str]]:
    """Validate and normalize incoming query definitions."""
    query_defs: list[dict[str, str]] = []
    for idx, query_item in enumerate(queries, start=1):
        if not isinstance(query_item, dict):
            raise ValueError(
                "Each query must be a dict with keys 'id' and 'text'. "
                f"Invalid entry at position {idx}: {query_item!r}"
            )

        query_id = str(query_item.get("id", "")).strip()
        query_text = str(query_item.get("text", "")).strip()
        if not query_id or not query_text:
            raise ValueError(
                "Each query dict must define non-empty 'id' and 'text'. "
                f"Invalid entry at position {idx}: {query_item!r}"
            )

        query_defs.append({"id": query_id, "text": query_text})

    return query_defs


def _build_summary_columns() -> tuple[list[str], list[str], list[str]]:
    """Return output column layouts used by the summary artifacts."""
    table_columns = [
        "Query ID",
        "Name",
        "Parameters",
        "Thinking",
        "Temperature",
        "Valid JSON Rate",
        "Avg IT (s)",
        "Std Dev IT (s)",
        "95% CI (IT)",
        "G_Cypher",
        "G_Sparql",
    ]
    file_columns = ["Query ID", "Query Text", *table_columns[1:]]
    comparison_file_columns = [
        col
        for col in file_columns
        if col not in ("Query ID", "Query Text", "95% CI (IT)")
    ]
    return table_columns, file_columns, comparison_file_columns


def _build_model_comparison_row(
    records: list[dict],
    model_name: str,
    model_config: dict,
    thinking_mode: bool,
) -> dict:
    """Aggregate execution records into one model-level comparison row."""
    sample = np.array(
        [float(rec["Inference Time (s)"]) for rec in records], dtype=float
    )
    mean_time = float(np.mean(sample)) if sample.size else float("nan")
    std_time = float(np.std(sample, ddof=1)) if sample.size > 1 else 0.0

    valid_json_count = sum(1 for rec in records if bool(rec["Valid JSON"]))
    total_calls = len(records)
    valid_json_rate = (valid_json_count / total_calls) * 100 if total_calls else 0.0

    return {
        "Name": model_config.get("display_name", model_name),
        "Parameters": model_config.get("parameters", "N/A"),
        "Thinking": bool(thinking_mode),
        "Temperature": float(model_config["temperature"]),
        "Valid JSON Rate": round(valid_json_rate, 2),
        "Avg IT (s)": round(mean_time, 4),
        "Std Dev IT (s)": round(std_time, 4),
        "G_Cypher": model_config.get("g_cypher"),
        "G_Sparql": model_config.get("g_sparql"),
    }


def _save_query_summary_files(
    output_path: Path,
    execution_id: str,
    query_defs: list[dict[str, str]],
    query_rows_map: dict[str, list[dict]],
    file_columns: list[str],
) -> list[str]:
    """Persist one summary CSV per query and return file paths."""
    query_file_paths: list[str] = []
    for query_def in query_defs:
        query_id = query_def["id"]
        query_text = query_def["text"]
        query_df = pd.DataFrame(query_rows_map[query_id], columns=file_columns)
        query_file = output_path / (
            f"query_summary_{_safe_name(query_id)}_"
            f"{_safe_query_name(query_text)}_{execution_id}.csv"
        )
        query_df.to_csv(query_file, index=False, encoding="utf-8")
        query_file_paths.append(str(query_file))
        print(f"Saved query file: {query_file}")
    return query_file_paths


def run_models_summary(
    ollama_client: Any,
    models: dict,
    queries: list[dict],
    system_prompt: str,
    base_options: dict,
    runs_per_model: int,
    output_dir: str,
    confidence_level: float = 0.95,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str], list[str], list[str], str, str]:
    """
    Run model summary benchmark and persist outputs.

    Returns:
      (
        all_results_df,
        model_comparison_df,
        model_file_paths,
        query_file_paths,
        execution_file_paths,
        all_results_file_path,
        model_comparison_file_path,
      )
    """
    execution_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / execution_id
    output_path.mkdir(parents=True, exist_ok=True)

    query_defs = _normalize_query_defs(queries)
    table_columns, file_columns, comparison_file_columns = _build_summary_columns()

    all_rows: list[dict] = []
    model_file_paths: list[str] = []
    query_rows_map: dict[str, list[dict]] = {
        query_def["id"]: [] for query_def in query_defs
    }
    query_file_paths: list[str] = []
    execution_file_paths: list[str] = []
    model_comparison_rows: list[dict] = []
    partial_all_results_file = (
        output_path / f"model_summary_all_partial_{execution_id}.csv"
    )

    enabled_models = [
        (name, cfg) for name, cfg in models.items() if cfg.get("enabled", True)
    ]

    for model_idx, (model_name, model_config) in enumerate(enabled_models, start=1):
        print(f"[{model_idx}/{len(enabled_models)}] Processing model: {model_name}")
        model_dir = output_path / _safe_name(model_name)
        model_dir.mkdir(parents=True, exist_ok=True)

        modes = [False]
        if model_config.get("supports_thinking", False):
            modes.append(True)

        model_rows: list[dict] = []
        mode_execution_records: dict[bool, list[dict]] = {mode: [] for mode in modes}
        for query_idx, query_def in enumerate(query_defs, start=1):
            query_id = query_def["id"]
            query_text = query_def["text"]
            print(f"  - Query {query_idx}/{len(query_defs)} ({query_id})")

            for thinking_mode in modes:
                print(f"    - Thinking={thinking_mode}")
                row, execution_records = compute_model_mode_metrics(
                    ollama_client=ollama_client,
                    model_name=model_name,
                    model_config=model_config,
                    queries=[query_text],
                    system_prompt=system_prompt,
                    base_options=base_options,
                    runs_per_model=runs_per_model,
                    thinking=thinking_mode,
                    query_id=query_id,
                    confidence_level=confidence_level,
                )
                row["Query Text"] = query_text
                model_rows.append(row)
                all_rows.append(row)
                query_rows_map[query_id].append(row)

                executions_df = pd.DataFrame(execution_records)
                mode_execution_records[thinking_mode].extend(execution_records)
                executions_file = model_dir / (
                    f"executions_{_safe_name(model_name)}_"
                    f"{_safe_name(query_id)}_{_safe_query_name(query_text)}_"
                    f"thinking_{str(thinking_mode).lower()}_{execution_id}.csv"
                )
                executions_df.to_csv(executions_file, index=False, encoding="utf-8")
                execution_file_paths.append(str(executions_file))
                print(f"    Saved executions file: {executions_file}")

        for thinking_mode, records in mode_execution_records.items():
            model_comparison_rows.append(
                _build_model_comparison_row(
                    records=records,
                    model_name=model_name,
                    model_config=model_config,
                    thinking_mode=thinking_mode,
                )
            )

        model_df = pd.DataFrame(model_rows, columns=file_columns)
        model_file = (
            model_dir / f"model_summary_{_safe_name(model_name)}_{execution_id}.csv"
        )
        model_df.to_csv(model_file, index=False, encoding="utf-8")
        model_file_paths.append(str(model_file))
        print(f"  Saved model file: {model_file}")

        # Persist cumulative progress after each model completes.
        pd.DataFrame(all_rows, columns=file_columns).to_csv(
            partial_all_results_file, index=False, encoding="utf-8"
        )
        print(f"  Updated partial combined file: {partial_all_results_file}")

    all_results_file_df = pd.DataFrame(all_rows, columns=file_columns)
    all_results_df = pd.DataFrame(all_rows, columns=table_columns)

    query_file_paths = _save_query_summary_files(
        output_path=output_path,
        execution_id=execution_id,
        query_defs=query_defs,
        query_rows_map=query_rows_map,
        file_columns=file_columns,
    )

    all_results_file = output_path / f"model_summary_all_{execution_id}.csv"
    all_results_file_df.to_csv(all_results_file, index=False, encoding="utf-8")

    model_comparison_file = (
        output_path / f"model_summary_models_comparison_{execution_id}.csv"
    )
    model_comparison_df = pd.DataFrame(
        model_comparison_rows, columns=comparison_file_columns
    )
    model_comparison_df.to_csv(model_comparison_file, index=False, encoding="utf-8")
    print(f"Saved model comparison file: {model_comparison_file}")

    return (
        all_results_df,
        model_comparison_df,
        model_file_paths,
        query_file_paths,
        execution_file_paths,
        str(all_results_file),
        str(model_comparison_file),
    )


SYSTEM_PROMPT = """
You are a semantic parser that converts natural language into a structured, schema-independent intermediate representation (IR) for graph queries.
The IR must be:
- Independent of any specific database schema
- Based only on the meaning of the input text
- Internally consistent and unambiguous
- Valid JSON
-------------------------

INSTRUCTIONS

-------------------------
**Step 1.** Identify the main target entity type (what the user is asking for). 
**Step 2.** Identify all mentioned entities:
- Assign each an id (e.g., "e1", "e2").
- Assign a generic type (e.g., Person, Movie, Organization, Location, Event).
**Step 3.** Extract semantic relationships using ROLE-BASED labels:
- Use intuitive, natural roles (e.g., director, actor, author, located_in).
- DO NOT invent database-specific relation names.
- Roles must be lowercase and descriptive.
**Step 4.** Handle Free Variables:
- When a query implies an unknown intermediate entity (e.g., "someone who", "a director that"), assign it a free variable string (e.g., "x", "y") instead of an entity ID.
**Step 5.** Build constraints:
- Each constraint links the target entity to another entity or variable via a role.
- Combine constraints using "and" by default, or "or" only if explicitly required by the text.
**Step 6.** Handle Universal Quantifiers ("All", "Every"):
- Translate universal requirements using double negation: `not` -> `exists` -> `where` -> `not` (or the mathematical inverse of a comparison).
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

EXAMPLES

-------------------------
Input: "Give me the Movies directed by Eastwood or Spielberg and starring Meryl Streep."
Output:
```json
{
  "hypotheses": [
    {
      "id": "h1",
      "query": {
        "target": "Movie",
        "entities": [
          { "id": "e1", "type": "Person", "name": "Eastwood" },
          { "id": "e2", "type": "Person", "name": "Spielberg" },
          { "id": "e3", "type": "Person", "name": "Meryl Streep" }
        ],
        "where": {
          "or": [
            {
              "rel": "director",
              "to": "e1"
            },
            {
              "and": [
                { "rel": "director", "to": "e2" },
                { "rel": "actor", "to": "e3" }
              ]
            }
          ]
        }
      }
    },
    {
      "id": "h2",
      "query": {
        "target": "Movie",
        "entities": [
          { "id": "e1", "type": "Person", "name": "Eastwood" },
          { "id": "e2", "type": "Person", "name": "Spielberg" },
          { "id": "e3", "type": "Person", "name": "Meryl Streep" }
        ],
        "where": {
          "and": [
            {
              "or": [
                { "rel": "director", "to": "e1" },
                { "rel": "director", "to": "e2" }
              ]
            },
            { "rel": "actor", "to": "e3" }
          ]
        }
      }
    }
  ]
}
```
Input: "Give me the movies whose director has won more awards than Meryl Streep"
Output:
```json
{
  "hypotheses": [
    {
      "id": "h1",
      "query": {
        "target": "Movie",
        "entities": [
          { "id": "e1", "type": "Person", "name": "Meryl Streep" }
        ],
        "where": {
          "rel": "director",
          "to": "x",
          "where": {
            "cmp": {
              "left": {
                "count": {
                  "rel": "won",
                  "to": "award"
                }
              },
              "op": ">",
              "right": {
                "count": {
                  "rel": "won",
                  "to": "x",
                  "of": "e1"
                }
              }
            }
          }
        }
      }
    }
  ]
}
```
Input: "Flights where every passenger is an adult."
Output:
```json
{
  "hypotheses": [
    {
      "id": "h1",
      "query": {
        "target": "Flight",
        "where": {
          "not": {
            "exists": {
              "rel": "passenger",
              "to": "x",
              "where": {
                "cmp": {
                  "left": { "attr": "age", "of": "x" },
                  "op": "<",
                  "right": 18
                }
              }
            }
          }
        }
      }
    }
  ]
}
```
Input: "Authors who have written at least 5 books published after 2010."
Output:
```json
{
  "hypotheses": [
    {
      "id": "h1",
      "query": {
        "target": "Author",
        "where": {
          "cmp": {
            "left": {
              "count": {
                "rel": "author_of",
                "to": "x",
                "where": {
                  "cmp": {
                    "left": { "attr": "publish_year", "of": "x" },
                    "op": ">",
                    "right": 2010
                  }
                }
              }
            },
            "op": ">=",
            "right": 5
          }
        }
      }
    }
  ]
}
```
-------------------------

RULES

-------------------------
- Output ONLY valid JSON enclosed in standard markdown blocks (```json ... ```).
- Do NOT output any conversational text, pleasantries, or explanations.
- Do NOT include comments in the JSON output (// or /* */).
- Be consistent with entity ids across hypotheses.
- Do NOT assume any database schema.
- Follow the Grammar strictly.
- Prefer simple structures over complex nesting.
- Generate more than one hypothesis in the array ONLY if there are multiple syntactically valid interpretations.
"""
