from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
from ollama import Client

import utils
from .config import normalize_criteria_config
from .defaults import DEFAULT_GROUND_TRUTHS, EVALUATOR_USER_PROMPT_TEMPLATE

safe_name = utils._safe_name


def clean_json_response(raw_text: str) -> str:
    if raw_text is None:
        return ""
    return utils._extract_json_text(str(raw_text))


def load_ground_truths(ground_truths_path: str | None = None) -> dict[str, dict]:
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


def export_default_ground_truths(output_path: str | Path) -> Path:
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(DEFAULT_GROUND_TRUTHS, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path


def ground_truth_to_json_text(ground_truth_obj: dict | None) -> str:
    if not ground_truth_obj:
        return "{}"
    return json.dumps(ground_truth_obj, ensure_ascii=False, indent=2)


def _find_execution_files(summary_root: str | Path) -> list[Path]:
    root = Path(summary_root)
    if not root.exists():
        raise FileNotFoundError(f"Summary folder does not exist: {root}")
    files = list(root.rglob("executions_*.csv")) + list(root.rglob("trace_*.csv"))
    return sorted(files)


def _parse_eval_response(raw_response: str) -> tuple[float, str, str]:
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
    expect_json_response: bool = True,
) -> tuple[float, str, str, str]:
    ground_truth_header = (
        "GROUND TRUTH JSON" if expect_json_response else "GROUND TRUTH"
    )
    candidate_header = "CANDIDATE JSON" if expect_json_response else "CANDIDATE"

    user_prompt = EVALUATOR_USER_PROMPT_TEMPLATE.format(
        query_text=query_text,
        ground_truth_header=ground_truth_header,
        ground_truth_content=ground_truth_json,
        candidate_header=candidate_header,
        candidate_content=candidate_json,
    )

    response = utils._call_ollama_with_retry(
        ollama_client=ollama_client,
        model=evaluator_model,
        messages=[
            {"role": "system", "content": evaluator_system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        options=dict(evaluator_options or {}),
        think=bool(evaluator_thinking),
    )

    raw_response = response.get("message", {}).get("content", "")
    score, rationale, error = _parse_eval_response(raw_response)
    return score, rationale, error, raw_response


def _save_evaluated_execution(
    evaluated_df: pd.DataFrame,
    execution_file: Path,
    evaluator_model: str,
    output_dir: Path,
) -> Path:
    model_group = safe_name(execution_file.parent.name)
    model_output_dir = output_dir / model_group
    model_output_dir.mkdir(parents=True, exist_ok=True)

    file_out = model_output_dir / f"evaluated_{execution_file.name}"
    evaluated_df.to_csv(file_out, index=False, encoding="utf-8")
    return file_out


def evaluate_execution_file(
    execution_csv: str | Path,
    ollama_client: Client,
    evaluator_model: str,
    criteria_config: dict[str, dict[str, Any]],
    ground_truths: dict[str, dict],
    evaluator_options: dict | None = None,
    evaluator_thinking: bool = False,
    test_query_ids: str | list[str] | tuple[str, ...] | set[str] | None = None,
    test_model: str | None = None,
    use_representation_weights: bool = True,
    expect_json_response: bool = True,
) -> pd.DataFrame:
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

    evaluated_rows: list[dict[str, Any]] = []

    valid_rows = []
    for _, row in df.iterrows():
        query_id = str(row.get("Query ID", "")).strip()
        row_model = str(row.get("Model", "")).strip()

        if selected_query_ids and query_id not in selected_query_ids:
            continue
        if test_model and row_model != str(test_model).strip():
            continue

        valid_rows.append(row)

    for criteria_idx, (criterion_id, criterion_cfg) in enumerate(
        criteria_config.items(), start=1
    ):
        applicable_rows = [
            r
            for r in valid_rows
            if str(r.get("Query ID", "")).strip() in criterion_cfg["query_ids"]
        ]
        total_runs = len(applicable_rows)

        if total_runs == 0:
            continue

        print(
            f"    - Evaluating Criterion {criterion_id} [{criteria_idx}/{len(criteria_config)}]"
        )

        for run_idx, row in enumerate(applicable_rows, start=1):
            if run_idx % 5 == 0 or run_idx == 1 or run_idx == total_runs:
                print(f"      - Run [{run_idx}/{total_runs}]")

            query_id = str(row.get("Query ID", "")).strip()
            query_text = str(row.get("Query", "")).strip()

            candidate_raw = str(row.get("Response", ""))
            if expect_json_response:
                candidate_json = clean_json_response(candidate_raw)
            else:
                candidate_json = utils.clean_code_response(candidate_raw)

            ground_truth_obj = ground_truths.get(query_id)
            if ground_truth_obj and "solution" in ground_truth_obj:
                solution_val = ground_truth_obj["solution"]
                if isinstance(solution_val, str):
                    ground_truth_json = solution_val
                else:
                    ground_truth_json = json.dumps(
                        solution_val, ensure_ascii=False, indent=2
                    )
            else:
                ground_truth_json = ground_truth_to_json_text(ground_truth_obj)

            if use_representation_weights:
                representation_weight = (
                    float(ground_truth_obj.get("representation_weight", 1.0))
                    if ground_truth_obj
                    else 1.0
                )
            else:
                representation_weight = 1.0

            if representation_weight == 0:
                score = 0.0
                rationale = "Skipped evaluation: representation weight is 0."
                error = None
                eval_raw = ""
            else:
                score, rationale, error, eval_raw = _evaluate_candidate(
                    ollama_client=ollama_client,
                    evaluator_model=evaluator_model,
                    evaluator_system_prompt=str(criterion_cfg["system_prompt"]),
                    query_text=query_text,
                    ground_truth_json=ground_truth_json,
                    candidate_json=candidate_json,
                    evaluator_options=evaluator_options,
                    evaluator_thinking=evaluator_thinking,
                    expect_json_response=expect_json_response,
                )
                score = score * representation_weight

            row_data = cast(dict[str, Any], row.to_dict())
            row_data.update(
                {
                    "Criterion ID": criterion_id,
                    "Criterion": str(criterion_cfg["name"]),
                    "Criterion Weight": float(criterion_cfg["weight"]),
                    "Eval Score": score,
                    "Supported_Score": score if representation_weight > 0 else np.nan,
                    "Supported_Query_ID": (
                        query_id if representation_weight > 0 else np.nan
                    ),
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


def _build_ci_frame(
    evaluated_df: pd.DataFrame,
    group_cols: list[str],
    confidence_level: float = 0.95,
) -> pd.DataFrame:
    """Build a DataFrame with 95% CI (Score) for each group."""
    ci_rows: list[dict[str, Any]] = []
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

        row = {col: value for col, value in zip(group_cols, group_key, strict=False)}
        row["95% CI (Score)"] = f"[{ci_low:.4f}, {ci_high:.4f}]"
        ci_rows.append(row)

    return pd.DataFrame(ci_rows)


def _compute_weighted_overall(
    frame: pd.DataFrame,
    criterion_ids: list[str],
    criterion_weights: dict[str, float],
) -> pd.Series:
    """Return a Series of weighted-average scores for each row of *frame*."""

    def _row_weighted(row: pd.Series) -> float:
        valid_criteria = [
            cid for cid in criterion_ids if cid in row.index and pd.notna(row[cid])
        ]
        if not valid_criteria:
            return float("nan")

        weight_sum = sum(criterion_weights[cid] for cid in valid_criteria)
        if weight_sum <= 0:
            return float("nan")

        return float(
            sum(float(row[cid]) * criterion_weights[cid] for cid in valid_criteria)
            / weight_sum
        )

    return frame.apply(_row_weighted, axis=1)


def _ensure_ci_after_std(frame: pd.DataFrame) -> pd.DataFrame:
    """Re-order columns so that '95% CI (Score)' immediately follows 'Std_Score'."""
    ci_col = "95% CI (Score)"
    std_col = "Std_Score"
    if ci_col in frame.columns and std_col in frame.columns:
        cols = [col for col in frame.columns if col != ci_col]
        cols.insert(cols.index(std_col) + 1, ci_col)
        return frame[cols]
    return frame


def _build_aspect_columns(
    evaluated_df: pd.DataFrame,
    base_group_cols: list[str],
    criterion_ids: list[str],
) -> pd.DataFrame:
    """Pivot mean Eval Score per criterion into one column per criterion ID."""
    aspect_df = (
        evaluated_df.groupby(base_group_cols + ["Criterion ID"], dropna=False)
        .agg(Aspect_Score=("Eval Score", "mean"))
        .reset_index()
    )

    pivot_df = aspect_df.pivot_table(
        index=base_group_cols,
        columns="Criterion ID",
        values="Aspect_Score",
        aggfunc="first",
    ).reset_index()

    pivot_df.columns.name = None
    for criterion_id in criterion_ids:
        if criterion_id not in pivot_df.columns:
            pivot_df[criterion_id] = np.nan

    ordered_cols = base_group_cols + criterion_ids
    return pivot_df[ordered_cols]


def _aggregate_outputs(
    evaluated_df: pd.DataFrame,
    criteria_config: dict[str, dict[str, Any]],
    group_has_grammar: bool = False,
    confidence_level: float | None = 0.95,
) -> dict[str, pd.DataFrame]:
    """
    Build all aggregation tables.

    When ``group_has_grammar=True`` the ``Grammar`` column is prepended to
    every grouping key, enabling cross-grammar comparison in a single table.
    """
    criterion_ids = list(criteria_config.keys())
    criterion_weights = {
        cid: float(criteria_config[cid]["weight"]) for cid in criterion_ids
    }

    g = ["Grammar"] if group_has_grammar else []

    def _agg(group_cols: list[str], agg_spec: dict) -> pd.DataFrame:
        return (
            evaluated_df.groupby(group_cols, dropna=False).agg(**agg_spec).reset_index()
        )

    def _merge_ci(frame: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
        if confidence_level is None:
            return frame
        ci = _build_ci_frame(evaluated_df, group_cols, confidence_level)
        return frame.merge(ci, on=group_cols, how="left")

    common_agg = dict(
        Runs=("Eval Score", "count"),
        Mean_Score=("Eval Score", "mean"),
        Supported_Mean_Score=("Supported_Score", "mean"),
        Std_Score=("Eval Score", "std"),
        Min_Score=("Eval Score", "min"),
        Max_Score=("Eval Score", "max"),
    )
    summary_agg = dict(
        Total_Runs=("Eval Score", "count"),
        Overall_Score=("Eval Score", "mean"),
        Supported_Overall_Score=("Supported_Score", "mean"),
        Std_Score=("Eval Score", "std"),
        Min_Score=("Eval Score", "min"),
        Max_Score=("Eval Score", "max"),
    )

    # model × mode × query × criterion
    mmqc = g + ["Model", "Thinking", "Query ID", "Query", "Criterion ID", "Criterion"]
    by_mmqc = _merge_ci(
        _agg(
            mmqc, {**common_agg, "Avg_Inference_Time_s": ("Inference Time (s)", "mean")}
        ),
        mmqc,
    )

    # model × mode × criterion
    mmc = g + ["Model", "Thinking", "Criterion ID", "Criterion"]
    by_mmc = _merge_ci(
        _agg(
            mmc,
            {
                **summary_agg,
                "Queries_Evaluated": ("Query ID", "nunique"),
                "Supported_Queries": ("Supported_Query_ID", "nunique"),
            },
        ),
        mmc,
    )

    # query × criterion
    qc = g + ["Query ID", "Query", "Criterion ID", "Criterion"]
    by_qc = _merge_ci(
        _agg(qc, {**summary_agg, "Models_Evaluated": ("Model", "nunique")}),
        qc,
    )

    # model × mode × query
    mmq = g + ["Model", "Thinking", "Query ID", "Query"]
    by_mmq = _merge_ci(
        _agg(
            mmq, {**common_agg, "Avg_Inference_Time_s": ("Inference Time (s)", "mean")}
        ),
        mmq,
    )
    by_mmq = by_mmq.merge(
        _build_aspect_columns(evaluated_df, mmq, criterion_ids), on=mmq, how="left"
    )
    by_mmq["Weighted_Overall"] = _compute_weighted_overall(
        by_mmq, criterion_ids, criterion_weights
    )

    # model × mode
    mm = g + ["Model", "Thinking"]
    by_mm = _merge_ci(
        _agg(
            mm,
            {
                **summary_agg,
                "Queries_Evaluated": ("Query ID", "nunique"),
                "Supported_Queries": ("Supported_Query_ID", "nunique"),
            },
        ),
        mm,
    )
    by_mm = by_mm.merge(
        _build_aspect_columns(evaluated_df, mm, criterion_ids), on=mm, how="left"
    )
    by_mm["Weighted_Overall"] = _compute_weighted_overall(
        by_mm, criterion_ids, criterion_weights
    )

    # query only
    q = g + ["Query ID", "Query"]
    by_q = _merge_ci(
        _agg(q, {**summary_agg, "Models_Evaluated": ("Model", "nunique")}),
        q,
    )
    by_q = by_q.merge(
        _build_aspect_columns(evaluated_df, q, criterion_ids), on=q, how="left"
    )
    by_q["Weighted_Overall"] = _compute_weighted_overall(
        by_q, criterion_ids, criterion_weights
    )

    # round and fix CI column ordering
    result = {
        "by_model_mode_query_criterion": _ensure_ci_after_std(by_mmqc),
        "by_model_mode_criterion": _ensure_ci_after_std(by_mmc),
        "by_query_criterion": _ensure_ci_after_std(by_qc),
        "by_model_mode_query": _ensure_ci_after_std(by_mmq),
        "by_model_mode": _ensure_ci_after_std(by_mm),
        "by_query": _ensure_ci_after_std(by_q),
    }
    for frame in result.values():
        num_cols = frame.select_dtypes(include=["number"]).columns
        frame[num_cols] = frame[num_cols].round(4)

    return result


def evaluate_summary_folder(
    summary_root: str,
    evaluator_model: str,
    ollama_server: str,
    output_root: str = "outputs/query_eval",
    evaluator_options: dict | None = None,
    evaluator_thinking: bool = False,
    criteria_config: dict[str, dict[str, Any]] | None = None,
    ground_truths_path: str | None = None,
    test_query_ids: str | list[str] | tuple[str, ...] | set[str] | None = None,
    test_query_id: str | None = None,
    test_model: str | None = None,
    confidence_level: float | None = 0.95,
) -> dict[str, str | list[str] | pd.DataFrame]:
    summary_path = Path(summary_root)
    execution_files = _find_execution_files(summary_path)

    if test_model:
        target_dir = safe_name(str(test_model))
        execution_files = [f for f in execution_files if f.parent.name == target_dir]

    if not execution_files:
        raise ValueError(
            f"No executions_*.csv files found under {summary_path} for the selected filters"
        )

    normalized_criteria = normalize_criteria_config(criteria_config)
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
            criteria_config=normalized_criteria,
            ground_truths=ground_truths,
            evaluator_options=evaluator_options,
            evaluator_thinking=evaluator_thinking,
            test_query_ids=selected_queries,
            test_model=test_model,
        )

        if evaluated_df.empty:
            continue

        file_out = _save_evaluated_execution(
            evaluated_df, execution_file, evaluator_model, output_dir
        )
        per_file_paths.append(str(file_out))

        all_frames.append(evaluated_df)

        # Update partial cumulative files to avoid losses in case of error
        partial_df = pd.concat(all_frames, ignore_index=True)
        # Clean up partial files
        partial_files = [
            output_dir / "all_evaluations_partial.csv",
            output_dir / "by_model_query_criterion_partial.csv",
            output_dir / "by_criterion_partial.csv",
            output_dir / "by_query_criterion_partial.csv",
            output_dir / "by_model_query_partial.csv",
            output_dir / "by_model_partial.csv",
            output_dir / "by_query_partial.csv",
        ]
        for pf in partial_files:
            if pf.exists():
                pf.unlink()

        p_aggs = _aggregate_outputs(
            partial_df,
            criteria_config=normalized_criteria,
            confidence_level=confidence_level,
        )
        p_aggs["by_model_mode_query_criterion"].to_csv(
            output_dir / "by_model_query_criterion_partial.csv",
            index=False,
            encoding="utf-8",
        )
        p_aggs["by_model_mode_criterion"].to_csv(
            output_dir / "scores_by_criterion_partial.csv",
            index=False,
            encoding="utf-8",
        )
        p_aggs["by_query_criterion"].to_csv(
            output_dir / "scores_by_query_criterion_partial.csv",
            index=False,
            encoding="utf-8",
        )
        p_aggs["by_model_mode_query"].to_csv(
            output_dir / "scores_by_model_query_partial.csv",
            index=False,
            encoding="utf-8",
        )
        p_aggs["by_model_mode"].to_csv(
            output_dir / "scores_by_model_partial.csv",
            index=False,
            encoding="utf-8",
        )
        p_aggs["by_query"].to_csv(
            output_dir / "scores_by_query_partial.csv",
            index=False,
            encoding="utf-8",
        )
        print("    Updated partial global summary files.")

    if not all_frames:
        raise ValueError("No rows matched the selected test filters")

    all_evaluated_df = pd.concat(all_frames, ignore_index=True)
    aggs = _aggregate_outputs(
        all_evaluated_df,
        criteria_config=normalized_criteria,
        confidence_level=confidence_level,
    )
    by_model_mode_query_criterion = aggs["by_model_mode_query_criterion"]
    by_model_mode_criterion = aggs["by_model_mode_criterion"]
    by_query_criterion = aggs["by_query_criterion"]
    by_model_mode_query = aggs["by_model_mode_query"]
    by_model_mode = aggs["by_model_mode"]
    by_query = aggs["by_query"]

    all_file = output_dir / "scores_all_evaluations.csv"
    model_mode_query_criterion_file = output_dir / "scores_by_model_query_criterion.csv"
    model_mode_criterion_file = output_dir / "scores_by_criterion.csv"
    query_criterion_file = output_dir / "scores_by_query_criterion.csv"
    model_mode_query_file = output_dir / "scores_by_model_query.csv"
    model_mode_file = output_dir / "scores_by_model.csv"
    query_file = output_dir / "scores_by_query.csv"

    all_evaluated_df.to_csv(all_file, index=False, encoding="utf-8")
    by_model_mode_query_criterion.to_csv(
        model_mode_query_criterion_file, index=False, encoding="utf-8"
    )
    by_model_mode_criterion.to_csv(
        model_mode_criterion_file, index=False, encoding="utf-8"
    )
    by_query_criterion.to_csv(query_criterion_file, index=False, encoding="utf-8")
    by_model_mode_query.to_csv(model_mode_query_file, index=False, encoding="utf-8")
    by_model_mode.to_csv(model_mode_file, index=False, encoding="utf-8")
    by_query.to_csv(query_file, index=False, encoding="utf-8")

    display_model_mode_query_criterion = by_model_mode_query_criterion.drop(
        columns=["Query"], errors="ignore"
    )
    display_query_criterion = by_query_criterion.drop(
        columns=["Query"], errors="ignore"
    )
    display_model_mode_query = by_model_mode_query.drop(
        columns=["Query"], errors="ignore"
    )
    display_query = by_query.drop(columns=["Query"], errors="ignore")

    print(f"Saved output folder: {output_dir}")

    return {
        "output_dir": str(output_dir),
        "per_file_outputs": per_file_paths,
        "all_rows_file": str(all_file),
        "model_mode_query_criterion_file": str(model_mode_query_criterion_file),
        "model_mode_criterion_file": str(model_mode_criterion_file),
        "query_criterion_file": str(query_criterion_file),
        "model_mode_query_file": str(model_mode_query_file),
        "model_mode_file": str(model_mode_file),
        "query_file": str(query_file),
        "all_rows_df": all_evaluated_df,
        "model_mode_query_criterion_df": display_model_mode_query_criterion,
        "model_mode_criterion_df": by_model_mode_criterion,
        "query_criterion_df": display_query_criterion,
        "model_mode_query_df": display_model_mode_query,
        "model_mode_df": by_model_mode,
        "query_df": display_query,
    }
