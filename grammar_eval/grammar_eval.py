import sys
import os
script_dir = os.path.abspath(os.path.dirname(__file__))
project_root = os.path.abspath(os.path.join(script_dir, ".."))
sys.path = [p for p in sys.path if os.path.abspath(p) != script_dir]
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import pandas as pd
from typing import cast

from grammar_eval.grammar_utils import evaluate_grammars

# ---------------------------------------------------------------------------
# Evaluator configuration (shared across all grammars)
# ---------------------------------------------------------------------------

EVALUATOR_MODEL = "gemma4:26b"
OLLAMA_SERVER = "http://156.35.95.33:11434"
EVALUATOR_OPTIONS = {
    "temperature": 0.0,
    "num_predict": 2048,
    "num_ctx": 12288,
}
EVALUATOR_THINKING = False

# Confidence level for statistical intervals. Set to None to disable calculating
# and displaying confidence intervals in all aggregate output tables.
CONFIDENCE_LEVEL = None

# Quick test mode: run only selected queries / one source model.
TEST_MODE = False
TEST_QUERY_IDS = ["Q01"]
TEST_MODEL = "gemma4:26b"

# Output folder for all evaluation artifacts
OUTPUT_ROOT = "outputs/grammar_eval"

PROMPTS_DIR = "prompts"

# ---------------------------------------------------------------------------
# Query sets — adjust as needed to match your run.
# Both grammars share the same 10 queries (Q01-Q10).
# ---------------------------------------------------------------------------

ALL_QUERY_IDS = [f"Q{i:02d}" for i in range(1, 11)]  # Q01 … Q10

# ---------------------------------------------------------------------------
# Grammar definitions
# Each key is the grammar label shown in all output files.
# ---------------------------------------------------------------------------

GRAMMARS_CONFIG = {
    # ------------------------------------------------------------------
    # SemGIR-Lists v1 — Grammar 1 (SYSTEM_PROMPT_LISTS_v1)
    # ------------------------------------------------------------------
    "semgir_lists_v1": {
        # Folder produced by model_eval for v1 prompt (replace placeholder with actual timestamp folder)
        "summary_run_dir": "outputs/summary/SYSTEM_PROMPT_LISTS_v1/20260605_134853",
        # Ground-truth JSON for this grammar
        "ground_truths_path": "ground_truths/sem_gir_comparison/ground_truths_semgir_lists_v1.json",
        "criteria_config": {
            "G0_SEMGIR_LISTS_v1": {
                "name": "Overall Translation Quality (SemGIR-Lists v1)",
                "weight": 1.0,
                "query_ids": ALL_QUERY_IDS,
                "prompt_file": f"{PROMPTS_DIR}/G0_SEMGIR_LISTS_v1.prompt.md",
            },
        },
    },
    # ------------------------------------------------------------------
    # SemGIR-Lists v2 — Grammar 2 (SYSTEM_PROMPT_LISTS_v2)
    # ------------------------------------------------------------------
    "semgir_lists_v2": {
        # Folder produced by model_eval for v2 prompt (replace placeholder with actual timestamp folder)
        "summary_run_dir": "outputs/summary/SYSTEM_PROMPT_LISTS_v2/20260605_203824",
        # Ground-truth JSON for this grammar
        "ground_truths_path": "ground_truths/sem_gir_comparison/ground_truths_semgir_lists_v2.json",
        "criteria_config": {
            "G0_SEMGIR_LISTS_v2": {
                "name": "Overall Translation Quality (SemGIR-Lists v2)",
                "weight": 1.0,
                "query_ids": ALL_QUERY_IDS,
                "prompt_file": f"{PROMPTS_DIR}/G0_SEMGIR_LISTS_v2.prompt.md",
            },
        },
    },
    # ------------------------------------------------------------------
    # SemGIR-Lists v3 — Grammar 3 (SYSTEM_PROMPT_LISTS_v3)
    # ------------------------------------------------------------------
    "semgir_lists_v3": {
        # Folder produced by model_eval for v3 prompt (replace placeholder with actual timestamp folder)
        "summary_run_dir": "outputs/summary/SYSTEM_PROMPT_LISTS_v3/20260606_030045",
        # Ground-truth JSON for this grammar
        "ground_truths_path": "ground_truths/sem_gir_comparison/ground_truths_semgir_lists_v3.json",
        "criteria_config": {
            "G0_SEMGIR_LISTS_v3": {
                "name": "Overall Translation Quality (SemGIR-Lists v3)",
                "weight": 1.0,
                "query_ids": ALL_QUERY_IDS,
                "prompt_file": f"{PROMPTS_DIR}/G0_SEMGIR_LISTS_v3.prompt.md",
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    result = evaluate_grammars(
        grammars_config=GRAMMARS_CONFIG,
        evaluator_model=EVALUATOR_MODEL,
        ollama_server=OLLAMA_SERVER,
        output_root=OUTPUT_ROOT,
        evaluator_options=EVALUATOR_OPTIONS,
        evaluator_thinking=EVALUATOR_THINKING,
        confidence_level=CONFIDENCE_LEVEL,
        test_query_ids=TEST_QUERY_IDS if TEST_MODE else None,
        test_model=TEST_MODEL if TEST_MODE else None,
    )

    print("\n=== Output paths ===")
    print("Output folder          :", result["output_dir"])
    print("Combined all rows      :", result["combined_all_rows_file"])
    print("Combined model/mode    :", result["combined_by_model_mode_file"])
    print("Combined model/mode/q  :", result["combined_by_model_mode_query_file"])
    print("Combined query         :", result["combined_by_query_file"])
    print(
        "Combined mmqc          :",
        result["combined_by_model_mode_query_criterion_file"],
    )

    print("\n=== Per-grammar output folders ===")
    for grammar_label, grammar_result in result["per_grammar"].items():
        print(f"  [{grammar_label}] {grammar_result['output_dir']}")

    # -----------------------------------------------------------------------
    # Preview: combined model × grammar breakdown
    # -----------------------------------------------------------------------
    combined_mm_df = cast(pd.DataFrame, result["combined_by_model_mode_df"])
    print("\n=== Combined model × mode × grammar preview ===")
    print(combined_mm_df.to_string(index=False))

    # -----------------------------------------------------------------------
    # Preview: per-grammar model × mode tables
    # -----------------------------------------------------------------------
    for grammar_label, grammar_result in result["per_grammar"].items():
        mm_df = cast(pd.DataFrame, grammar_result["by_model_mode_df"])
        print(f"\n=== [{grammar_label}] Model × mode overall ===")
        print(mm_df.to_string(index=False))
