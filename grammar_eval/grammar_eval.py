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
from config import OLLAMA_SERVER

# ---------------------------------------------------------------------------
# Evaluator configuration (shared across all grammars)
# ---------------------------------------------------------------------------

EVALUATOR_MODEL = "gemma4:26b"
EVALUATOR_OPTIONS = {
    "temperature": 0.0,
    "num_predict": 3072,
    "num_ctx": 12288,
}
EVALUATOR_THINKING = False

# Confidence level for statistical intervals. Set to None to disable calculating
# and displaying confidence intervals in all aggregate output tables.
CONFIDENCE_LEVEL = 0.95

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
    # Lambda DCS
    # ------------------------------------------------------------------
    "lambda_dcs": {
        "summary_run_dir": "<<FILL_RUN_DIR>>",
        "ground_truths_path": "ground_truths/class_a/ground_truth_lambda_dcs.json",
        "expect_json_response": False,
        "criteria_config": {
            "EVAL_PROMPT_LAMBDA_DCS": {
                "name": "Overall Translation Quality (Lambda DCS)",
                "weight": 1.0,
                "query_ids": ALL_QUERY_IDS,
                "prompt_file": f"{PROMPTS_DIR}/grammars/eval/EVAL_PROMPT_LAMBDA_DCS.prompt.md",
            },
        },
    },
    # ------------------------------------------------------------------
    # PCCG CGG Lambda
    # ------------------------------------------------------------------
    "pccg_cgg_lambda": {
        "summary_run_dir": "<<FILL_RUN_DIR>>",
        "ground_truths_path": "ground_truths/class_a/ground_truth_pccg_cgg_lambda.json",
        "expect_json_response": False,
        "criteria_config": {
            "EVAL_PROMPT_PCCG_CGG_LAMBDA": {
                "name": "Overall Translation Quality (PCCG CGG Lambda)",
                "weight": 1.0,
                "query_ids": ALL_QUERY_IDS,
                "prompt_file": f"{PROMPTS_DIR}/grammars/eval/EVAL_PROMPT_PCCG_CGG_LAMBDA.prompt.md",
            },
        },
    },
    # ------------------------------------------------------------------
    # NSQA
    # ------------------------------------------------------------------
    "nsqa": {
        "summary_run_dir": "<<FILL_RUN_DIR>>",
        "ground_truths_path": "ground_truths/class_c/ground_truth_nsqa.json",
        "expect_json_response": False,
        "criteria_config": {
            "EVAL_PROMPT_NSQA": {
                "name": "Overall Translation Quality (NSQA)",
                "weight": 1.0,
                "query_ids": ALL_QUERY_IDS,
                "prompt_file": f"{PROMPTS_DIR}/grammars/eval/EVAL_PROMPT_NSQA.prompt.md",
            },
        },
    },
    # ------------------------------------------------------------------
    # Squall
    # ------------------------------------------------------------------
    "squall": {
        "summary_run_dir": "<<FILL_RUN_DIR>>",
        "ground_truths_path": "ground_truths/class_d/ground_truth_squall.json",
        "expect_json_response": False,
        "criteria_config": {
            "EVAL_PROMPT_SQUALL": {
                "name": "Overall Translation Quality (Squall)",
                "weight": 1.0,
                "query_ids": ALL_QUERY_IDS,
                "prompt_file": f"{PROMPTS_DIR}/grammars/eval/EVAL_PROMPT_SQUALL.prompt.md",
            },
        },
    },
    # ------------------------------------------------------------------
    # GraphQ Tree
    # ------------------------------------------------------------------
    "graphq_tree": {
        "summary_run_dir": "<<FILL_RUN_DIR>>",
        "ground_truths_path": "ground_truths/class_e/ground_truth_graphq_tree.json",
        "expect_json_response": False,
        "criteria_config": {
            "EVAL_PROMPT_GRAPHQ_TREE": {
                "name": "Overall Translation Quality (GraphQ Tree)",
                "weight": 1.0,
                "query_ids": ALL_QUERY_IDS,
                "prompt_file": f"{PROMPTS_DIR}/grammars/eval/EVAL_PROMPT_GRAPHQ_TREE.prompt.md",
            },
        },
    },
    # ------------------------------------------------------------------
    # SemGIR
    # ------------------------------------------------------------------
    "semgir": {
        "summary_run_dir": "<<FILL_RUN_DIR>>",
        "ground_truths_path": "ground_truths/ground_truth_sem_gir.json",
        "expect_json_response": True,
        "criteria_config": {
            "EVAL_PROMPT_SEMGIR": {
                "name": "Overall Translation Quality (SemGIR)",
                "weight": 1.0,
                "query_ids": ALL_QUERY_IDS,
                "prompt_file": f"{PROMPTS_DIR}/evaluator.prompt.md",
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
