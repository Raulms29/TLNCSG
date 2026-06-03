from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from ollama import Client

from query_eval.utils.config import normalize_criteria_config
from query_eval.utils.engine import (
    _build_aspect_columns,
    _build_ci_frame,
    _compute_weighted_overall,
    _ensure_ci_after_std,
    _find_execution_files,
    clean_json_response,
    evaluate_execution_file,
    export_default_ground_truths,
    ground_truth_to_json_text,
    load_ground_truths,
    safe_name,
)

__all__ = [
    "clean_json_response",
    "evaluate_grammars",
    "export_default_ground_truths",
    "ground_truth_to_json_text",
    "load_ground_truths",
    "safe_name",
]


# ---------------------------------------------------------------------------
# Grammar-aware aggregation
# Extends query_eval's aggregation with an optional "Grammar" grouping prefix.
# ---------------------------------------------------------------------------

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
            evaluated_df.groupby(group_cols, dropna=False)
            .agg(**agg_spec)
            .reset_index()
        )

    def _merge_ci(frame: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
        if confidence_level is None:
            return frame
        ci = _build_ci_frame(evaluated_df, group_cols, confidence_level)
        return frame.merge(ci, on=group_cols, how="left")

    common_agg = dict(
        Runs=("Eval Score", "count"),
        Mean_Score=("Eval Score", "mean"),
        Std_Score=("Eval Score", "std"),
        Min_Score=("Eval Score", "min"),
        Max_Score=("Eval Score", "max"),
    )
    summary_agg = dict(
        Total_Runs=("Eval Score", "count"),
        Overall_Score=("Eval Score", "mean"),
        Std_Score=("Eval Score", "std"),
        Min_Score=("Eval Score", "min"),
        Max_Score=("Eval Score", "max"),
    )

    # model × mode × query × criterion
    mmqc = g + ["Model", "Thinking", "Query ID", "Query", "Criterion ID", "Criterion"]
    by_mmqc = _merge_ci(
        _agg(mmqc, {**common_agg, "Avg_Inference_Time_s": ("Inference Time (s)", "mean")}),
        mmqc,
    )

    # model × mode × criterion
    mmc = g + ["Model", "Thinking", "Criterion ID", "Criterion"]
    by_mmc = _merge_ci(
        _agg(mmc, {**summary_agg, "Queries_Evaluated": ("Query ID", "nunique")}),
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
        _agg(mmq, {**common_agg, "Avg_Inference_Time_s": ("Inference Time (s)", "mean")}),
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
        _agg(mm, {**summary_agg, "Queries_Evaluated": ("Query ID", "nunique")}),
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate_grammars(
    grammars_config: dict[str, dict[str, Any]],
    evaluator_model: str,
    ollama_server: str,
    output_root: str = "outputs/grammar_eval",
    evaluator_options: dict | None = None,
    evaluator_thinking: bool = False,
    confidence_level: float | None = 0.95,
    test_query_ids: str | list[str] | tuple[str, ...] | set[str] | None = None,
    test_model: str | None = None,
) -> dict[str, Any]:
    """
    Evaluate and compare multiple grammar variants.

    Parameters
    ----------
    grammars_config:
        A dict mapping a grammar label (e.g. ``"semgir"``) to a config dict
        with the following keys:

        - ``summary_run_dir`` (str): folder containing ``executions_*.csv``
          files produced by ``run_models_summary`` for this grammar.
        - ``ground_truths_path`` (str): path to the JSON ground-truth file.
        - ``criteria_config`` (dict): criterion definitions (same format as
          ``query_eval``). Each criterion must have ``name``, ``weight``,
          ``query_ids``, and either ``prompt_file`` or ``system_prompt``.

    evaluator_model:
        Ollama model used as evaluator.
    ollama_server:
        URL of the Ollama server.
    output_root:
        Root folder for all output artifacts.
    evaluator_options:
        Ollama generation options for the evaluator.
    evaluator_thinking:
        Whether to enable thinking mode for the evaluator.
    confidence_level:
        Confidence level for CI computation.
    test_query_ids:
        Restrict evaluation to these query IDs (applied to all grammars).
    test_model:
        Restrict evaluation to execution files of this model (all grammars).

    Returns
    -------
    dict with keys:
        - ``output_dir``
        - ``per_grammar``: dict grammar_label → per-grammar result dict
        - ``combined_all_rows_file`` and ``combined_all_rows_df``
        - ``combined_by_*_file`` / ``combined_by_*_df`` for each aggregation
    """
    if not grammars_config:
        raise ValueError("grammars_config must define at least one grammar")

    selected_query_ids: set[str] | None = None
    if test_query_ids:
        if isinstance(test_query_ids, str):
            selected_query_ids = {test_query_ids.strip()}
        else:
            selected_query_ids = {
                str(q).strip() for q in test_query_ids if str(q).strip()
            }

    execution_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(output_root) / execution_id
    output_dir.mkdir(parents=True, exist_ok=True)

    ollama_client = Client(ollama_server)

    # Merge criteria configs from all grammars to ensure all columns are represented in the combined outputs
    merged_criteria = {}
    for grammar_cfg in grammars_config.values():
        raw_crit = grammar_cfg.get("criteria_config")
        if raw_crit:
            merged_criteria.update(normalize_criteria_config(raw_crit))

    per_grammar_results: dict[str, dict[str, Any]] = {}
    all_combined_frames: list[pd.DataFrame] = []

    for grammar_label, grammar_cfg in grammars_config.items():
        print(f"\nStarting grammar: {grammar_label}")

        summary_run_dir = grammar_cfg["summary_run_dir"]
        ground_truths_path = grammar_cfg.get("ground_truths_path")
        raw_criteria = grammar_cfg.get("criteria_config")

        normalized_criteria = normalize_criteria_config(raw_criteria)
        ground_truths = load_ground_truths(ground_truths_path)

        # Ensure directory exists and is not a placeholder
        summary_path = Path(summary_run_dir)
        if "<" in summary_run_dir or ">" in summary_run_dir or not summary_path.exists():
            raise FileNotFoundError(
                f"Summary folder does not exist or is a placeholder: '{summary_run_dir}'. "
                f"Please configure a valid summary_run_dir in grammar_eval.py."
            )

        execution_files = _find_execution_files(summary_path)
        if test_model:
            target_dir = safe_name(str(test_model))
            execution_files = [
                f for f in execution_files if f.parent.name == target_dir
            ]
        if not execution_files:
            raise ValueError(
                f"No executions_*.csv files found under {summary_run_dir} "
                f"for grammar '{grammar_label}' with the selected filters"
            )

        grammar_output_dir = output_dir / safe_name(grammar_label)
        grammar_output_dir.mkdir(parents=True, exist_ok=True)

        per_file_paths: list[str] = []
        grammar_frames: list[pd.DataFrame] = []
        announced_models: set[str] = set()

        for file_idx, execution_file in enumerate(execution_files, start=1):
            source_model = execution_file.parent.name
            if source_model not in announced_models:
                print(
                    f"\n  Starting source model: {source_model} | "
                    f"Evaluator: {evaluator_model}"
                )
                announced_models.add(source_model)

            print(
                f"  - [{file_idx}/{len(execution_files)}] "
                f"Evaluating {execution_file.name}"
            )

            # Reuse query_eval's evaluate_execution_file directly
            evaluated_df = evaluate_execution_file(
                execution_csv=execution_file,
                ollama_client=ollama_client,
                evaluator_model=evaluator_model,
                criteria_config=normalized_criteria,
                ground_truths=ground_truths,
                evaluator_options=evaluator_options,
                evaluator_thinking=evaluator_thinking,
                test_query_ids=selected_query_ids,
                test_model=test_model,
            )

            if evaluated_df.empty:
                continue

            # Tag every row with its grammar so combined tables are unambiguous
            evaluated_df.insert(0, "Grammar", grammar_label)

            model_group = safe_name(execution_file.parent.name)
            model_output_dir = grammar_output_dir / model_group
            model_output_dir.mkdir(parents=True, exist_ok=True)

            file_out = model_output_dir / f"evaluated_{execution_file.name}"
            evaluated_df.to_csv(file_out, index=False, encoding="utf-8")
            per_file_paths.append(str(file_out))
            grammar_frames.append(evaluated_df)

            # Persist cumulative partial files after each execution file
            partial_df = pd.concat(grammar_frames, ignore_index=True)
            partial_df.to_csv(
                grammar_output_dir / f"evaluation_all_runs_partial_{execution_id}.csv",
                index=False,
                encoding="utf-8",
            )
            p_aggs = _aggregate_outputs(
                partial_df,
                criteria_config=normalized_criteria,
                group_has_grammar=False,
                confidence_level=confidence_level,
            )
            for key, stem in [
                ("by_model_mode_query_criterion", "evaluation_model_mode_query_criterion_partial"),
                ("by_model_mode_criterion",       "evaluation_model_mode_criterion_partial"),
                ("by_query_criterion",            "evaluation_query_criterion_partial"),
                ("by_model_mode_query",           "evaluation_model_mode_query_partial"),
                ("by_model_mode",                 "evaluation_model_mode_partial"),
                ("by_query",                      "evaluation_query_partial"),
            ]:
                p_aggs[key].to_csv(
                    grammar_output_dir / f"{stem}_{execution_id}.csv",
                    index=False,
                    encoding="utf-8",
                )
            print("    Updated partial global summary files.")

        if not grammar_frames:
            raise ValueError(
                f"No rows matched the selected filters for grammar '{grammar_label}'"
            )

        grammar_all_df = pd.concat(grammar_frames, ignore_index=True)
        aggs = _aggregate_outputs(
            grammar_all_df,
            criteria_config=normalized_criteria,
            group_has_grammar=False,
            confidence_level=confidence_level,
        )

        def _save(df: pd.DataFrame, stem: str, base: Path = grammar_output_dir) -> str:
            p = base / f"{stem}_{execution_id}.csv"
            df.to_csv(p, index=False, encoding="utf-8")
            return str(p)

        grammar_result: dict[str, Any] = {
            "output_dir": str(grammar_output_dir),
            "per_file_outputs": per_file_paths,
            "all_rows_file": _save(grammar_all_df, "evaluation_all_runs"),
            "model_mode_query_criterion_file": _save(aggs["by_model_mode_query_criterion"], "evaluation_model_mode_query_criterion"),
            "model_mode_criterion_file":       _save(aggs["by_model_mode_criterion"],       "evaluation_model_mode_criterion"),
            "query_criterion_file":            _save(aggs["by_query_criterion"],            "evaluation_query_criterion"),
            "model_mode_query_file":           _save(aggs["by_model_mode_query"],           "evaluation_model_mode_query"),
            "model_mode_file":                 _save(aggs["by_model_mode"],                 "evaluation_model_mode"),
            "query_file":                      _save(aggs["by_query"],                      "evaluation_query"),
            "all_rows_df": grammar_all_df,
            **{f"{k}_df": v for k, v in aggs.items()},
        }
        per_grammar_results[grammar_label] = grammar_result
        all_combined_frames.append(grammar_all_df)

        # Persist cumulative combined partial files after each grammar completes
        combined_partial_df = pd.concat(all_combined_frames, ignore_index=True)
        combined_partial_df.to_csv(
            output_dir / f"combined_all_runs_partial_{execution_id}.csv",
            index=False,
            encoding="utf-8",
        )
        p_combined_aggs = _aggregate_outputs(
            combined_partial_df,
            criteria_config=merged_criteria,
            group_has_grammar=True,
            confidence_level=confidence_level,
        )
        for key, stem in [
            ("by_model_mode_query_criterion", "combined_model_mode_query_criterion_partial"),
            ("by_model_mode_criterion",       "combined_model_mode_criterion_partial"),
            ("by_query_criterion",            "combined_query_criterion_partial"),
            ("by_model_mode_query",           "combined_model_mode_query_partial"),
            ("by_model_mode",                 "combined_model_mode_partial"),
            ("by_query",                      "combined_query_partial"),
        ]:
            p_combined_aggs[key].to_csv(
                output_dir / f"{stem}_{execution_id}.csv",
                index=False,
                encoding="utf-8",
            )
        print(f"Saved grammar output folder: {grammar_output_dir}")
        print("    Updated partial global summary files.")


    # -----------------------------------------------------------------------
    # Combined cross-grammar aggregation (Grammar column included in groups)
    # -----------------------------------------------------------------------
    print("\nBuilding combined cross-grammar aggregation...")

    combined_df = pd.concat(all_combined_frames, ignore_index=True)

    combined_aggs = _aggregate_outputs(
        combined_df,
        criteria_config=merged_criteria,
        group_has_grammar=True,
        confidence_level=confidence_level,
    )

    def _save_combined(df: pd.DataFrame, stem: str) -> str:
        p = output_dir / f"{stem}_{execution_id}.csv"
        df.to_csv(p, index=False, encoding="utf-8")
        return str(p)

    result: dict[str, Any] = {
        "output_dir": str(output_dir),
        "per_grammar": per_grammar_results,
        "combined_all_rows_file": _save_combined(combined_df, "combined_all_runs"),
        "combined_all_rows_df": combined_df,
    }
    for key, stem in [
        ("by_model_mode_query_criterion", "combined_model_mode_query_criterion"),
        ("by_model_mode_criterion",       "combined_model_mode_criterion"),
        ("by_query_criterion",            "combined_query_criterion"),
        ("by_model_mode_query",           "combined_model_mode_query"),
        ("by_model_mode",                 "combined_model_mode"),
        ("by_query",                      "combined_query"),
    ]:
        df = combined_aggs[key]
        result[f"combined_{key}_file"] = _save_combined(df, stem)
        result[f"combined_{key}_df"] = df

    print(f"Saved output folder: {output_dir}")
    return result
