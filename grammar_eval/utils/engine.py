from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import re

import numpy as np
import pandas as pd
from ollama import Client

from query_eval.utils.config import normalize_criteria_config
from query_eval.utils.engine import (
    _aggregate_outputs,
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
    use_representation_weights: bool = True,
    expect_json_response: bool = True,
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
    output_dir = Path(output_root).resolve() / execution_id
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

        g_use_weights = grammar_cfg.get(
            "use_representation_weights", use_representation_weights
        )
        g_expect_json = grammar_cfg.get("expect_json_response", expect_json_response)

        normalized_criteria = normalize_criteria_config(raw_criteria)
        ground_truths = load_ground_truths(ground_truths_path)

        # Ensure directory exists and is not a placeholder
        summary_path = Path(summary_run_dir)
        if (
            "<" in summary_run_dir
            or ">" in summary_run_dir
            or not summary_path.exists()
        ):
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

        # Partial files for this grammar are stored in a dedicated subfolder
        # so they do not clutter the final output directory.
        grammar_partial_dir = grammar_output_dir / "partial"
        grammar_partial_dir.mkdir(parents=True, exist_ok=True)

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
                use_representation_weights=g_use_weights,
                expect_json_response=g_expect_json,
            )

            if evaluated_df.empty:
                continue

            # Tag every row with its grammar so combined tables are unambiguous
            evaluated_df.insert(0, "Grammar", grammar_label)

            model_group = safe_name(execution_file.parent.name)
            model_output_dir = grammar_output_dir / model_group
            model_output_dir.mkdir(parents=True, exist_ok=True)

            query_id_match = re.search(r"_(Q\d+)_", execution_file.name)
            query_id = query_id_match.group(1) if query_id_match else "unknown"
            thinking_match = re.search(r"_th_(true|false)", execution_file.name)
            if not thinking_match:
                thinking_match = re.search(
                    r"_thinking_(true|false)", execution_file.name
                )
            thinking = thinking_match.group(1) if thinking_match else "unknown"

            file_out = model_output_dir / f"eval_trace_{query_id}_th_{thinking}.csv"
            evaluated_df.to_csv(file_out, index=False, encoding="utf-8")
            per_file_paths.append(str(file_out))
            grammar_frames.append(evaluated_df)

            # Persist cumulative partial files after each execution file
            partial_df = pd.concat(grammar_frames, ignore_index=True)
            partial_df.to_csv(
                grammar_partial_dir / "scores_all_evaluations_partial.csv",
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
                (
                    "by_model_mode_query_criterion",
                    "scores_by_model_query_criterion_partial",
                ),
                ("by_model_mode_criterion", "scores_by_criterion_partial"),
                ("by_query_criterion", "scores_by_query_criterion_partial"),
                ("by_model_mode_query", "scores_by_model_query_partial"),
                ("by_model_mode", "grammar_scores_by_model_partial"),
                ("by_query", "scores_by_query_partial"),
            ]:
                p_aggs[key].to_csv(
                    grammar_partial_dir / f"{stem}.csv",
                    index=False,
                    encoding="utf-8",
                )
            print(f"    Updated partial files: {grammar_partial_dir}")

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
            p = base / f"{stem}.csv"
            df.to_csv(p, index=False, encoding="utf-8")
            return str(p)

        per_grammar_results[grammar_label] = {
            "output_dir": str(grammar_output_dir),
            "file_paths": per_file_paths,
            "all_runs_file": _save(grammar_all_df, "scores_all_evaluations"),
            "by_model_mode_query_criterion_file": _save(
                aggs["by_model_mode_query_criterion"], "scores_by_model_query_criterion"
            ),
            "by_model_mode_criterion_file": _save(
                aggs["by_model_mode_criterion"], "scores_by_criterion"
            ),
            "by_query_criterion_file": _save(
                aggs["by_query_criterion"], "scores_by_query_criterion"
            ),
            "by_model_mode_query_file": _save(
                aggs["by_model_mode_query"], "scores_by_model_query"
            ),
            "by_model_mode_file": _save(
                aggs["by_model_mode"], "grammar_scores_by_model"
            ),
            "by_query_file": _save(aggs["by_query"], "scores_by_query"),
            "by_model_mode_df": aggs["by_model_mode"],
        }

        all_combined_frames.append(grammar_all_df)

        # Persist cumulative combined partial files after each grammar completes
        # Stored in a dedicated partial/ subfolder to keep the root dir clean.
        combined_partial_dir = output_dir / "partial"
        combined_partial_dir.mkdir(parents=True, exist_ok=True)

        combined_partial_df = pd.concat(all_combined_frames, ignore_index=True)
        combined_partial_df.to_csv(
            combined_partial_dir / "scores_all_evaluations_partial.csv",
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
            (
                "by_model_mode_query_criterion",
                "scores_by_model_query_criterion_partial",
            ),
            ("by_model_mode_criterion", "scores_by_criterion_partial"),
            ("by_query_criterion", "scores_by_query_criterion_partial"),
            ("by_model_mode_query", "scores_by_model_query_partial"),
            ("by_model_mode", "scores_by_model_partial"),
            ("by_query", "scores_by_query_partial"),
        ]:
            p_combined_aggs[key].to_csv(
                combined_partial_dir / f"{stem}.csv",
                index=False,
                encoding="utf-8",
            )
        print(f"Saved grammar output folder: {grammar_output_dir}")
        print(f"    Updated combined partial files: {combined_partial_dir}")

    # -----------------------------------------------------------------------
    # Combined cross-grammar aggregation (Grammar column included in groups)
    # -----------------------------------------------------------------------
    print("\nBuilding combined cross-grammar aggregation...")

    all_combined_df = pd.concat(all_combined_frames, ignore_index=True)

    c_aggs = _aggregate_outputs(
        all_combined_df,
        criteria_config=merged_criteria,
        group_has_grammar=True,
        confidence_level=confidence_level,
    )

    def _save_comb(df: pd.DataFrame, stem: str) -> str:
        p = output_dir / f"{stem}.csv"
        df.to_csv(p, index=False, encoding="utf-8")
        return str(p)

    return {
        "output_dir": str(output_dir),
        "per_grammar": per_grammar_results,
        "combined_all_rows_file": _save_comb(all_combined_df, "scores_all_evaluations"),
        "combined_by_model_mode_query_criterion_file": _save_comb(
            c_aggs["by_model_mode_query_criterion"],
            "scores_by_model_query_criterion",
        ),
        "combined_by_model_mode_criterion_file": _save_comb(
            c_aggs["by_model_mode_criterion"], "scores_by_criterion"
        ),
        "combined_by_query_criterion_file": _save_comb(
            c_aggs["by_query_criterion"], "scores_by_query_criterion"
        ),
        "combined_by_model_mode_query_file": _save_comb(
            c_aggs["by_model_mode_query"], "scores_by_model_query"
        ),
        "combined_by_model_mode_file": _save_comb(
            c_aggs["by_model_mode"], "scores_by_model"
        ),
        "combined_by_query_file": _save_comb(c_aggs["by_query"], "scores_by_query"),
        "combined_by_model_mode_df": c_aggs["by_model_mode"],
    }
