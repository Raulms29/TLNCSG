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
    return sorted(root.rglob("executions_*.csv"))


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
) -> tuple[float, str, str, str]:
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
    criteria_config: dict[str, dict[str, Any]],
    ground_truths: dict[str, dict],
    evaluator_options: dict | None = None,
    evaluator_thinking: bool = False,
    test_query_ids: str | list[str] | tuple[str, ...] | set[str] | None = None,
    test_model: str | None = None,
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

        for criterion_id, criterion_cfg in criteria_config.items():
            if query_id not in criterion_cfg["query_ids"]:
                continue

            score, rationale, error, eval_raw = _evaluate_candidate(
                ollama_client=ollama_client,
                evaluator_model=evaluator_model,
                evaluator_system_prompt=str(criterion_cfg["system_prompt"]),
                query_text=query_text,
                ground_truth_json=ground_truth_json,
                candidate_json=candidate_json,
                evaluator_options=evaluator_options,
                evaluator_thinking=evaluator_thinking,
            )

            row_data = cast(dict[str, Any], row.to_dict())
            row_data.update(
                {
                    "Criterion ID": criterion_id,
                    "Criterion": str(criterion_cfg["name"]),
                    "Criterion Weight": float(criterion_cfg["weight"]),
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
    criteria_config: dict[str, dict[str, Any]],
    confidence_level: float = 0.95,
) -> tuple[
    pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame
]:
    criterion_ids = list(criteria_config.keys())
    criterion_weights = {
        criterion_id: float(criteria_config[criterion_id]["weight"])
        for criterion_id in criterion_ids
    }

    def _build_ci_frame(group_cols: list[str]) -> pd.DataFrame:
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

            row = {
                col: value for col, value in zip(group_cols, group_key, strict=False)
            }
            row["95% CI (Score)"] = f"[{ci_low:.4f}, {ci_high:.4f}]"
            ci_rows.append(row)

        return pd.DataFrame(ci_rows)

    def _compute_weighted_overall(frame: pd.DataFrame) -> pd.Series:
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
        ci_col = "95% CI (Score)"
        std_col = "Std_Score"
        if ci_col in frame.columns and std_col in frame.columns:
            cols = [col for col in frame.columns if col != ci_col]
            cols.insert(cols.index(std_col) + 1, ci_col)
            return frame[cols]
        return frame

    def _build_aspect_columns(base_group_cols: list[str]) -> pd.DataFrame:
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

    by_model_mode_query_criterion = (
        evaluated_df.groupby(
            ["Model", "Thinking", "Query ID", "Query", "Criterion ID", "Criterion"],
            dropna=False,
        )
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

    ci_model_mode_query_criterion = _build_ci_frame(
        ["Model", "Thinking", "Query ID", "Query", "Criterion ID", "Criterion"]
    )
    by_model_mode_query_criterion = by_model_mode_query_criterion.merge(
        ci_model_mode_query_criterion,
        on=["Model", "Thinking", "Query ID", "Query", "Criterion ID", "Criterion"],
        how="left",
    )

    by_model_mode_criterion = (
        evaluated_df.groupby(
            ["Model", "Thinking", "Criterion ID", "Criterion"], dropna=False
        )
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

    ci_model_mode_criterion = _build_ci_frame(
        ["Model", "Thinking", "Criterion ID", "Criterion"]
    )
    by_model_mode_criterion = by_model_mode_criterion.merge(
        ci_model_mode_criterion,
        on=["Model", "Thinking", "Criterion ID", "Criterion"],
        how="left",
    )

    by_query_criterion = (
        evaluated_df.groupby(
            ["Query ID", "Query", "Criterion ID", "Criterion"], dropna=False
        )
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

    ci_query_criterion = _build_ci_frame(
        ["Query ID", "Query", "Criterion ID", "Criterion"]
    )
    by_query_criterion = by_query_criterion.merge(
        ci_query_criterion,
        on=["Query ID", "Query", "Criterion ID", "Criterion"],
        how="left",
    )

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
    model_mode_query_aspects = _build_aspect_columns(
        ["Model", "Thinking", "Query ID", "Query"]
    )
    by_model_mode_query = by_model_mode_query.merge(
        model_mode_query_aspects,
        on=["Model", "Thinking", "Query ID", "Query"],
        how="left",
    )
    by_model_mode_query["Weighted_Overall"] = _compute_weighted_overall(
        by_model_mode_query
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
    model_mode_aspects = _build_aspect_columns(["Model", "Thinking"])
    by_model_mode = by_model_mode.merge(
        model_mode_aspects,
        on=["Model", "Thinking"],
        how="left",
    )
    by_model_mode["Weighted_Overall"] = _compute_weighted_overall(by_model_mode)

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
    query_aspects = _build_aspect_columns(["Query ID", "Query"])
    by_query = by_query.merge(
        query_aspects,
        on=["Query ID", "Query"],
        how="left",
    )
    by_query["Weighted_Overall"] = _compute_weighted_overall(by_query)

    by_model_mode_query_criterion = _ensure_ci_after_std(by_model_mode_query_criterion)
    by_model_mode_criterion = _ensure_ci_after_std(by_model_mode_criterion)
    by_query_criterion = _ensure_ci_after_std(by_query_criterion)
    by_model_mode_query = _ensure_ci_after_std(by_model_mode_query)
    by_model_mode = _ensure_ci_after_std(by_model_mode)
    by_query = _ensure_ci_after_std(by_query)

    for frame in (
        by_model_mode_query_criterion,
        by_model_mode_criterion,
        by_query_criterion,
        by_model_mode_query,
        by_model_mode,
        by_query,
    ):
        numeric_cols = frame.select_dtypes(include=["number"]).columns
        frame[numeric_cols] = frame[numeric_cols].round(4)

    return (
        by_model_mode_query_criterion,
        by_model_mode_criterion,
        by_query_criterion,
        by_model_mode_query,
        by_model_mode,
        by_query,
    )


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
    (
        by_model_mode_query_criterion,
        by_model_mode_criterion,
        by_query_criterion,
        by_model_mode_query,
        by_model_mode,
        by_query,
    ) = _aggregate_outputs(all_evaluated_df, criteria_config=normalized_criteria)

    all_file = output_dir / f"evaluation_all_runs_{execution_id}.csv"
    model_mode_query_criterion_file = (
        output_dir / f"evaluation_model_mode_query_criterion_{execution_id}.csv"
    )
    model_mode_criterion_file = (
        output_dir / f"evaluation_model_mode_criterion_overall_{execution_id}.csv"
    )
    query_criterion_file = (
        output_dir / f"evaluation_query_criterion_overall_{execution_id}.csv"
    )
    model_mode_query_file = (
        output_dir / f"evaluation_model_mode_query_{execution_id}.csv"
    )
    model_mode_file = output_dir / f"evaluation_model_mode_overall_{execution_id}.csv"
    query_file = output_dir / f"evaluation_query_overall_{execution_id}.csv"

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
