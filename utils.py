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
    mean = float(np.mean(sample))
    std = float(np.std(sample))
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


def _compute_latency_percentiles(sample: np.ndarray) -> dict[str, float]:
    """Compute latency percentiles for an inference-time sample."""
    if sample.size == 0:
        return {
            "P50 IT (s)": float("nan"),
            "P90 IT (s)": float("nan"),
            "P95 IT (s)": float("nan"),
        }

    return {
        "P50 IT (s)": float(np.percentile(sample, 50)),
        "P90 IT (s)": float(np.percentile(sample, 90)),
        "P95 IT (s)": float(np.percentile(sample, 95)),
    }


def _compute_throughput_tokens_per_second(
    total_tokens: float, total_seconds: float
) -> float:
    """Return throughput in tokens/sec from aggregate token and time totals."""
    return (total_tokens / total_seconds) if total_seconds > 0 else float("nan")


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
    eval_tokens_total = 0.0
    eval_seconds_total = 0.0

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

            prompt_eval_count = int(response_meta.get("prompt_eval_count", 0) or 0)
            eval_count = int(response_meta.get("eval_count", 0) or 0)
            prompt_eval_seconds = (
                float(int(response_meta.get("prompt_eval_duration", 0) or 0))
                / 1_000_000_000.0
            )
            eval_seconds = (
                float(int(response_meta.get("eval_duration", 0) or 0)) / 1_000_000_000.0
            )
            generation_tps = _compute_throughput_tokens_per_second(
                float(eval_count), eval_seconds
            )

            eval_tokens_total += float(eval_count)
            eval_seconds_total += eval_seconds

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
                    "Prompt Eval Count": prompt_eval_count,
                    "Prompt Eval Duration (s)": round(prompt_eval_seconds, 6),
                    "Eval Count": eval_count,
                    "Eval Duration (s)": round(eval_seconds, 6),
                    "Generation Throughput (tokens/s)": round(generation_tps, 4),
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

    latency_percentiles = _compute_latency_percentiles(sample)
    generation_throughput_tps = _compute_throughput_tokens_per_second(
        eval_tokens_total, eval_seconds_total
    )

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
        "P50 IT (s)": round(latency_percentiles["P50 IT (s)"], 4),
        "P90 IT (s)": round(latency_percentiles["P90 IT (s)"], 4),
        "P95 IT (s)": round(latency_percentiles["P95 IT (s)"], 4),
        "Generation Throughput (tokens/s)": round(generation_throughput_tps, 4),
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
        "Generation Throughput (tokens/s)",
        "G_Cypher",
        "G_Sparql",
        "P50 IT (s)",
        "P90 IT (s)",
        "P95 IT (s)",
    ]
    file_columns = ["Query ID", "Query Text", *table_columns[1:]]
    comparison_file_columns = [col for col in table_columns if col != "Query ID"]
    return table_columns, file_columns, comparison_file_columns


def _build_model_comparison_row(
    records: list[dict],
    model_name: str,
    model_config: dict,
    thinking_mode: bool,
    confidence_level: float = 0.95,
) -> dict:
    """Aggregate execution records into one model-level comparison row."""
    sample = np.array(
        [float(rec["Inference Time (s)"]) for rec in records], dtype=float
    )
    mean_time = float(np.mean(sample)) if sample.size else float("nan")
    std_time = float(np.std(sample, ddof=1)) if sample.size > 1 else 0.0

    if sample.size > 1:
        (ci_low, ci_high), _, _ = compute_confidence_interval_with_method(
            scores=sample,
            confidence_level=confidence_level,
            alpha=0.05,
        )
    else:
        ci_low, ci_high = (mean_time, mean_time)

    latency_percentiles = _compute_latency_percentiles(sample)

    valid_json_count = sum(1 for rec in records if bool(rec["Valid JSON"]))
    total_calls = len(records)
    valid_json_rate = (valid_json_count / total_calls) * 100 if total_calls else 0.0

    eval_tokens_total = sum(float(rec.get("Eval Count", 0) or 0) for rec in records)
    eval_seconds_total = sum(
        float(rec.get("Eval Duration (s)", 0) or 0) for rec in records
    )
    generation_throughput_tps = _compute_throughput_tokens_per_second(
        eval_tokens_total, eval_seconds_total
    )

    return {
        "Name": model_config.get("display_name", model_name),
        "Parameters": model_config.get("parameters", "N/A"),
        "Thinking": bool(thinking_mode),
        "Temperature": float(model_config["temperature"]),
        "Valid JSON Rate": round(valid_json_rate, 2),
        "Avg IT (s)": round(mean_time, 4),
        "Std Dev IT (s)": round(std_time, 4),
        "95% CI (IT)": f"[{ci_low:.4f}, {ci_high:.4f}]",
        "P50 IT (s)": round(latency_percentiles["P50 IT (s)"], 4),
        "P90 IT (s)": round(latency_percentiles["P90 IT (s)"], 4),
        "P95 IT (s)": round(latency_percentiles["P95 IT (s)"], 4),
        "Generation Throughput (tokens/s)": round(generation_throughput_tps, 4),
        "G_Cypher": model_config.get("g_cypher"),
        "G_Sparql": model_config.get("g_sparql"),
    }


def _resolve_model_modes(model_config: dict) -> list[bool]:
    """Return run modes for one model: standard and optional thinking mode."""
    modes = [False]
    if model_config.get("supports_thinking", False):
        modes.append(True)
    return modes


def _warmup_model(
    ollama_client: Any,
    model_name: str,
    model_config: dict,
    warmup_query: str,
    system_prompt: str,
    base_options: dict,
) -> None:
    """Run a single non-measured call to force model loading in Ollama."""
    run_ollama_once_with_metadata(
        ollama_client=ollama_client,
        model_name=model_name,
        query=warmup_query,
        system_prompt=system_prompt,
        base_options=base_options,
        temperature=float(model_config["temperature"]),
        thinking=False,
    )


def _save_execution_records_file(
    model_dir: Path,
    model_name: str,
    query_id: str,
    query_text: str,
    thinking_mode: bool,
    execution_id: str,
    execution_records: list[dict],
) -> str:
    """Save detailed execution records for one model/query/mode and return path."""
    execution_file = model_dir / (
        f"executions_{_safe_name(model_name)}_"
        f"{_safe_name(query_id)}_{_safe_query_name(query_text)}_"
        f"thinking_{str(thinking_mode).lower()}_{execution_id}.csv"
    )
    pd.DataFrame(execution_records).to_csv(
        execution_file, index=False, encoding="utf-8"
    )
    print(f"    Saved executions file: {execution_file}")
    return str(execution_file)


def _save_model_summary_file(
    model_dir: Path,
    model_name: str,
    execution_id: str,
    model_rows: list[dict],
    file_columns: list[str],
) -> str:
    """Save one model-level summary CSV and return path."""
    model_file = (
        model_dir / f"model_summary_{_safe_name(model_name)}_{execution_id}.csv"
    )
    pd.DataFrame(model_rows, columns=file_columns).to_csv(
        model_file, index=False, encoding="utf-8"
    )
    print(f"  Saved model file: {model_file}")
    return str(model_file)


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

    summary_rows: list[dict] = []
    model_file_paths: list[str] = []
    summary_rows_by_query: dict[str, list[dict]] = {
        query_def["id"]: [] for query_def in query_defs
    }
    query_file_paths: list[str] = []
    execution_file_paths: list[str] = []
    model_comparison_rows: list[dict] = []
    partial_summary_file = output_path / f"model_summary_all_partial_{execution_id}.csv"
    partial_model_comparison_file = (
        output_path / f"model_summary_models_comparison_partial_{execution_id}.csv"
    )

    enabled_models = [
        (name, cfg) for name, cfg in models.items() if cfg.get("enabled", True)
    ]

    for model_idx, (model_name, model_config) in enumerate(enabled_models, start=1):
        print(f"[{model_idx}/{len(enabled_models)}] Processing model: {model_name}")
        model_dir = output_path / _safe_name(model_name)
        model_dir.mkdir(parents=True, exist_ok=True)

        _warmup_model(
            ollama_client=ollama_client,
            model_name=model_name,
            model_config=model_config,
            warmup_query=query_defs[0]["text"],
            system_prompt=system_prompt,
            base_options=base_options,
        )

        modes = _resolve_model_modes(model_config)
        model_rows: list[dict] = []
        execution_records_by_mode: dict[bool, list[dict]] = {mode: [] for mode in modes}

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
                summary_rows.append(row)
                summary_rows_by_query[query_id].append(row)

                execution_records_by_mode[thinking_mode].extend(execution_records)
                execution_file_paths.append(
                    _save_execution_records_file(
                        model_dir=model_dir,
                        model_name=model_name,
                        query_id=query_id,
                        query_text=query_text,
                        thinking_mode=thinking_mode,
                        execution_id=execution_id,
                        execution_records=execution_records,
                    )
                )

        for thinking_mode, records in execution_records_by_mode.items():
            model_comparison_rows.append(
                _build_model_comparison_row(
                    records=records,
                    model_name=model_name,
                    model_config=model_config,
                    thinking_mode=thinking_mode,
                    confidence_level=confidence_level,
                )
            )

        model_file_paths.append(
            _save_model_summary_file(
                model_dir=model_dir,
                model_name=model_name,
                execution_id=execution_id,
                model_rows=model_rows,
                file_columns=file_columns,
            )
        )

        # Persist cumulative progress after each model completes.
        pd.DataFrame(summary_rows, columns=file_columns).to_csv(
            partial_summary_file, index=False, encoding="utf-8"
        )
        print(f"  Updated partial combined file: {partial_summary_file}")

        pd.DataFrame(model_comparison_rows, columns=comparison_file_columns).to_csv(
            partial_model_comparison_file, index=False, encoding="utf-8"
        )
        print(
            "  Updated partial model comparison file: "
            f"{partial_model_comparison_file}"
        )

    all_results_file_df = pd.DataFrame(summary_rows, columns=file_columns)
    all_results_df = pd.DataFrame(summary_rows, columns=table_columns)

    query_file_paths = _save_query_summary_files(
        output_path=output_path,
        execution_id=execution_id,
        query_defs=query_defs,
        query_rows_map=summary_rows_by_query,
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
**Step 1.** Identify the main target(s) and projections:
- Populate the `target` array with the `id` of the primary entities, relationships, or expressions the user wants to resolve.
- **When to use `projection`:** If the user explicitly asks for specific properties (e.g., "Give me the names and surnames of...", "List the titles of..."), extract those using the `projection` array with `ATTRIBUTE` expressions. Keep the `target` array focused only on the underlying entity/relationship IDs. If no specific fields are requested, omit the `projection` array to return the full entities.

**Step 2.** Identify entities and their topology:
- Declare all `entities` (nodes) with unique `id`s and generic semantic `type`s (e.g., "Person", "Movie").
- Declare all `relationships` (edges) connecting the entities. Assign unique `id`s, intuitive `role`s, and explicit `from` / `to` directions.

**Step 3.** Handle Attributes and Filtering:
- Use `COMPARISON` objects within the `constraint` to define specific properties. For example, to match a name, use an `ATTRIBUTE` expression: `left: {attribute_name: "name", of: "entity_id"}, operator: "=", right: "Target Name"`.

**Step 4.** Build Constraints (Filters):
- Combine conditions using `and_conditions` and `or_conditions`.
- Handle complex logic natively using `COMPARISON` operations.
- When validating an element set (like applying a COUNT or ALL), anchor the relationship inside an `and_conditions` block to ensure topological validity.

**Step 5.** Handle Quantifiers & Aggregations:
- **"All/Every"**: Use the `ALL` operator to enforce a condition across an entire set.
- **"Exists/Some"**: Use the `EXISTS` operator.
- **Counts/Metrics**: Use `COUNT`, `MAX`, `MIN`, or `SUMMATION` expressions directly in comparisons (e.g., counting a specific relationship).

**Step 6.** Query Composition (If Needed):
- The root output is a JSON object containing a `hypotheses_set` array: `{ "hypotheses_set": [HYPOTHESIS, ...] }`.
- If a natural language prompt implies multi-step execution (querying over a previous query's result), generate sequentially ordered queries using the `input` field to chain them. For standard queries, a single-element hypothesis array is sufficient.

-------------------------
GRAMMAR (treat the following as a formal specification, not prose)
-------------------------
HYPOTHESES_SET := { "hypotheses_set": [HYPOTHESIS, ...] }
// A JSON object containing a list of independent hypotheses (no relationships between them)

HYPOTHESIS := [QUERY, ...] 
// Ordered sequence of queries.
// Each QUERY can consume results from previous ones using `input`.

QUERY := {
  id: QUERY_ID, // one new fresh ID per query
  // Unique identifier of the query

  input?: QUERY_ID,  // existing ID in the JSON document
  // If present, this query operates on the result of a previous query.
  // Queries can refer directly to target IDs of the input queries
  // Enables query composition (query over query)

  target: [ENTITY_ID | RELATIONSHIP_ID | ADDRESSABLE_EXPRESSION, ...],  // ENTITY_ID and RELATIONSHIP_ID are existing IDs in the JSON document
  // Elements that define the output of the query.
  // Can include:
  // - entities
  // - relationships
  // - expressions (scalar values)

  entities: [ENTITY, ...], 
  // Entities (graph nodes) involved in the query

  relationships: [RELATIONSHIP, ...], 
  // Relationships (graph edges) connecting the entities

  constraint?: CONDITION,
  // Logical filter over entities and/or relationships

  projection?: [EXPRESSION, ...],
  // Explicit definition of output columns

  distinct?: BOOLEAN,
  // If true, removes duplicate results, otherwise duplicates are allowed

  order_by?: [ORDER_CRITERION, ...],
  // Defines how results should be sorted

  limit?: NUMBER
  // Limits the number of results (TOP-N behavior)
}

ENTITY := {
  id: ENTITY_ID, // new fresh unique ID of the entity 

  type: TYPE
  // Semantic type (e.g., "Person", "Movie", "Author"). This is domain dependent.
}

RELATIONSHIP := {
  id: RELATIONSHIP_ID,   // new fresh unique ID of the relationship

  role: ROLE, // Type of relationship (e.g., "FRIEND", "ACTED_IN"). It depends on the domain (not in a set of predefined roles)

  from: ENTITY_ID,   // existing ID of an entity in the JSON document; it represents the origin of the relationship
  
  to: ENTITY_ID    // existing ID of an entity in the JSON document; it represents the target of the relationship
}

ATTRIBUTE := {
  attribute_name: NAME,
  of: ENTITY_ID | RELATIONSHIP_ID    // existing entity or relationship ID in the JSON document
}

COUNT := {
  count_id: ENTITY_ID | RELATIONSHIP_ID, // existing ID in the JSON document
  condition?: CONDITION
  // Counts occurrences (optionally filtered)
}

SUMMATION := {
  summation_id: ENTITY_ID | RELATIONSHIP_ID,   // existing ID in the JSON document
  expression: EXPRESSION,  // expression that computes the values to be summed
  condition?: CONDITION  // condition of the elements to be summed
}

MAX := {
  max_id: ENTITY_ID | RELATIONSHIP_ID,  // existing ID in the JSON document
  expression: EXPRESSION, // expression that computes the values to get the maximum
  condition?: CONDITION
  // Maximum value of an expression
}

MIN := {
  min_id: ENTITY_ID | RELATIONSHIP_ID,  // existing ID in the JSON document
  expression: EXPRESSION, // expression that computes the values to get the minimum
  condition?: CONDITION
  // Minimum value of an expression
}

ORDER_CRITERION := {
  expression: EXPRESSION,  // expression that computes the values to be ordered
  direction?: "ASC" | "DESC"  // Sorting criterion
}

EXISTS := {
  exists_id: ENTITY_ID | RELATIONSHIP_ID,  // existing ID in the JSON document
  condition: CONDITION   // True if at least one element satisfies the condition
}

ALL := {
  all_id: ENTITY_ID | RELATIONSHIP_ID,  // existing ID in the JSON document
  condition: CONDITION  // True if all elements satisfy the condition
}

CONDITION := AND | OR | NOT | COMPARISON | EXISTS | ALL | RELATIONSHIP_ID
// Logical expressions used for filtering

AND := { and_conditions: [CONDITION, ...] }
// All conditions must hold

OR := { or_conditions: [CONDITION, ...] }
// At least one condition must hold

NOT := { not_condition: CONDITION }
// Logical negation

COMPARISON := {
  left: EXPRESSION,
  operator: COMPARISON_OPERATOR,
  right: EXPRESSION
}
// Binary comparison

COMPARISON_OPERATOR := "=" | "!=" | ">" | "<" | "<=" | ">=" 

ADDRESSABLE_EXPRESSION := { 
  expression_ID: EXPRESSION_ID, // new fresh unique ID of the expression
  expression: EXPRESSION // expression to be referenced
}
// Expression that can be referenced by using its expression_ID

EXPRESSION := 
    NUMBER 
  | STRING 
  | ATTRIBUTE 
  | COUNT 
  | SUMMATION 
  | MAX 
  | MIN
  | EXPRESSION_ID  // existing expression ID in the JSON document

TYPE := STRING
ROLE := STRING
NAME := STRING
NUMBER := FLOAT | INTEGER
BOOLEAN := true | false

-------------------------
EXAMPLES
-------------------------
Input: "Give me the names of the Authors who have written at least 5 books published after 2010."
Output:
```json
{
  "hypotheses_set": [
    [
      {
        "id": "q1",
        "target": ["e_author"],
        "entities": [
          { "id": "e_author", "type": "Author" },
          { "id": "e_book", "type": "Book" }
        ],
        "relationships": [
          { "id": "r_wrote", "role": "author_of", "from": "e_author", "to": "e_book" }
        ],
        "constraint": {
          "and_conditions": [
            "r_wrote",
            {
              "left": {
                "count_id": "e_book",
                "condition": {
                  "and_conditions": [
                    {
                      "left": { "attribute_name": "publish_year", "of": "e_book" },
                      "operator": ">",
                      "right": 2010
                    }
                  ]
                }
              },
              "operator": ">=",
              "right": 5
            }
          ]
        },
        "projection": [
          { "attribute_name": "name", "of": "e_author" }
        ]
      }
    ]
  ]
}
```

Input: "Give me the names of the customers and the score they gave in their review of the iPhone 15."
Output:
```json
{
  "hypotheses_set": [
    [
      {
        "id": "q1",
        "target": ["e_customer"],
        "entities": [
          { "id": "e_customer", "type": "Customer" },
          { "id": "e_product", "type": "Product" }
        ],
        "relationships": [
          { "id": "r_review", "role": "reviewed", "from": "e_customer", "to": "e_product" }
        ],
        "constraint": {
          "and_conditions": [
            "r_review",
            {
              "left": { "attribute_name": "name", "of": "e_product" },
              "operator": "=",
              "right": "iPhone 15"
            }
          ]
        },
        "projection": [
          { "attribute_name": "name", "of": "e_customer" },
          { "attribute_name": "score", "of": "r_review" }
        ]
      }
    ]
  ]
}
```

Input: "Give me the Movies directed by Eastwood or Spielberg and starring Meryl Streep."
Output:
```json
{
  "hypotheses_set": [
    [
      {
        "id": "q1",
        "target": ["e_movie"],
        "entities": [
          { "id": "e_movie", "type": "Movie" },
          { "id": "e_director", "type": "Person" },
          { "id": "e_actor", "type": "Person" }
        ],
        "relationships": [
          { "id": "r_dir", "role": "director", "from": "e_director", "to": "e_movie" },
          { "id": "r_act", "role": "actor", "from": "e_actor", "to": "e_movie" }
        ],
        "constraint": {
          "or_conditions": [
            {
              "left": { "attribute_name": "name", "of": "e_director" },
              "operator": "=",
              "right": "Eastwood"
            },
            {
              "and_conditions": [
                {
                  "left": { "attribute_name": "name", "of": "e_director" },
                  "operator": "=",
                  "right": "Spielberg"
                },
                {
                  "left": { "attribute_name": "name", "of": "e_actor" },
                  "operator": "=",
                  "right": "Meryl Streep"
                }
              ]
            }
          ]
        }
      }
    ],
    [
      {
        "id": "q2",
        "target": ["e_movie"],
        "entities": [
          { "id": "e_movie", "type": "Movie" },
          { "id": "e_director", "type": "Person" },
          { "id": "e_actor", "type": "Person" }
        ],
        "relationships": [
          { "id": "r_dir", "role": "director", "from": "e_director", "to": "e_movie" },
          { "id": "r_act", "role": "actor", "from": "e_actor", "to": "e_movie" }
        ],
        "constraint": {
          "and_conditions": [
            {
              "or_conditions": [
                {
                  "left": { "attribute_name": "name", "of": "e_director" },
                  "operator": "=",
                  "right": "Eastwood"
                },
                {
                  "left": { "attribute_name": "name", "of": "e_director" },
                  "operator": "=",
                  "right": "Spielberg"
                }
              ]
            },
            {
              "left": { "attribute_name": "name", "of": "e_actor" },
              "operator": "=",
              "right": "Meryl Streep"
            }
          ]
        }
      }
    ]
  ]
}
```

Input: "Give me the movies whose director has won more awards than Meryl Streep"
Output:
```json
{
  "hypotheses_set": [
    [
      {
        "id": "q1",
        "target": ["e_movie"],
        "entities": [
          { "id": "e_movie", "type": "Movie" },
          { "id": "e_director", "type": "Person" },
          { "id": "e_streep", "type": "Person" },
          { "id": "e_dir_award", "type": "Award" },
          { "id": "e_streep_award", "type": "Award" }
        ],
        "relationships": [
          { "id": "r_dir", "role": "director", "from": "e_director", "to": "e_movie" },
          { "id": "r_dir_won", "role": "won", "from": "e_director", "to": "e_dir_award" },
          { "id": "r_streep_won", "role": "won", "from": "e_streep", "to": "e_streep_award" }
        ],
        "constraint": {
          "and_conditions": [
            {
              "left": { "attribute_name": "name", "of": "e_streep" },
              "operator": "=",
              "right": "Meryl Streep"
            },
            {
              "left": { "count_id": "r_dir_won" },
              "operator": ">",
              "right": { "count_id": "r_streep_won" }
            }
          ]
        }
      }
    ]
  ]
}
```

Input: "Flights where every passenger is an adult."
Output:
```json
{
  "hypotheses_set": [
    [
      {
        "id": "q1",
        "target": ["e_flight"],
        "entities": [
          { "id": "e_flight", "type": "Flight" },
          { "id": "e_passenger", "type": "Person" }
        ],
        "relationships": [
          { "id": "r_pass", "role": "passenger", "from": "e_passenger", "to": "e_flight" }
        ],
        "constraint": {
          "and_conditions": [
            "r_pass",
            {
              "all_id": "e_passenger",
              "condition": {
                "left": { "attribute_name": "age", "of": "e_passenger" },
                "operator": ">=",
                "right": 18
              }
            }
          ]
        }
      }
    ]
  ]
}
```

-------------------------
RULES
-------------------------
- Output ONLY valid JSON enclosed in standard markdown blocks (```json ... ```).
- The root of the output MUST be a JSON object: `{ "hypotheses_set": [HYPOTHESIS, ...] }`.
- Do NOT output any conversational text, pleasantries, or explanations.
- Do NOT include comments in the JSON output (`//` or `/* */`).
- Be consistent with entity/relationship IDs across the query.
- Do NOT assume any specific database schema. Use broad semantics.
- Follow the Grammar strictly. `HYPOTHESIS` is always an *array* of `QUERY` objects.
- Prefer simple structures over complex nesting where logical equivalences exist.
- Generate more than one hypothesis in the `hypotheses_set` array ONLY if there are multiple syntactically valid semantic interpretations of the input text.
"""
