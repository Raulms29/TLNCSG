import sys
import os
script_dir = os.path.abspath(os.path.dirname(__file__))
project_root = os.path.abspath(os.path.join(script_dir, ".."))
sys.path = [p for p in sys.path if os.path.abspath(p) != script_dir]
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import pandas as pd
from typing import cast

from query_eval.query_utils import evaluate_summary_folder

# Path with model execution files (executions_*.csv)
SUMMARY_RUN_DIR = "outputs/summary/20260506_091738 E2 (keep)"

# Evaluator model and runtime configuration
EVALUATOR_MODEL = "deepseek-r1:8b"
OLLAMA_SERVER = "http://156.35.95.33:11434"
EVALUATOR_OPTIONS = {
    "temperature": 0.0,
    # Limits the generated response. Knowing that 95% of valid responses
    # are resolved in < 1200 tokens and the median in 200.
    "num_predict": 2048,
    # Defines the total context size (input + expected output).
    # I have had prompts of up to 4096 tokens.
    "num_ctx": 12288,
}
EVALUATOR_THINKING = True

# Quick test mode: run only selected queries and one source model.
TEST_MODE = False
TEST_QUERY_IDS = ["Q01"]
TEST_MODEL = "gemma4:e2b"

# Output folder for evaluation artifacts
OUTPUT_ROOT = "outputs/query_eval"

# Optional JSON file with ground truths by query id.
# If None, query_utils.DEFAULT_GROUND_TRUTHS are used.
GROUND_TRUTHS_FILE = "query_eval/ground_truths_default.json"

# Criterion-specific query sets (must be non-empty for each defined criterion).
CRITERION_1_QUERY_IDS = ["Q04", "Q06", "Q07", "Q08", "Q10", "Q11", "Q12"]
CRITERION_2_QUERY_IDS = ["Q03", "Q04", "Q05", "Q07", "Q09", "Q10"]
CRITERION_3_QUERY_IDS = ["Q01", "Q02", "Q03", "Q05", "Q06", "Q09", "Q10"]
CRITERION_4_QUERY_IDS = ["Q01", "Q02", "Q10", "Q11", "Q13", "Q14"]
CRITERION_5_QUERY_IDS = ["Q01", "Q02", "Q04", "Q08", "Q09", "Q12"]
CRITERION_6_QUERY_IDS = ["Q01", "Q02", "Q03", "Q05", "Q07", "Q08"]

PROMPTS_DIR = "prompts"

CRITERIA_CONFIG = {
    "A1_CS": {
        "name": "Syntactic Correctness (Well-formedness)",
        "weight": 1 / 6,
        "query_ids": CRITERION_1_QUERY_IDS,
        "prompt_file": f"{PROMPTS_DIR}/A1_CS.prompt.md",
    },
    "A2_FS": {
        "name": "Semantic Faithfulness",
        "weight": 1 / 6,
        "query_ids": CRITERION_2_QUERY_IDS,
        "prompt_file": f"{PROMPTS_DIR}/A2_FS.prompt.md",
    },
    "A3_SQ": {
        "name": "Structural Quality",
        "weight": 1 / 6,
        "query_ids": CRITERION_3_QUERY_IDS,
        "prompt_file": f"{PROMPTS_DIR}/A3_SQ.prompt.md",
    },
    "A4_HQ": {
        "name": "Hypothesis Quality",
        "weight": 1 / 6,
        "query_ids": CRITERION_4_QUERY_IDS,
        "prompt_file": f"{PROMPTS_DIR}/A4_HQ.prompt.md",
    },
    "A5_MR": {
        "name": "Minimality and Non-redundancy",
        "weight": 1 / 6,
        "query_ids": CRITERION_5_QUERY_IDS,
        "prompt_file": f"{PROMPTS_DIR}/A5_MR.prompt.md",
    },
    "A6_AP": {
        "name": "Aggregation and Projection Correctness",
        "weight": 1 / 6,
        "query_ids": CRITERION_6_QUERY_IDS,
        "prompt_file": f"{PROMPTS_DIR}/A6_AP.prompt.md",
    },
}


if __name__ == "__main__":
    result = evaluate_summary_folder(
        summary_root=SUMMARY_RUN_DIR,
        evaluator_model=EVALUATOR_MODEL,
        ollama_server=OLLAMA_SERVER,
        output_root=OUTPUT_ROOT,
        evaluator_options=EVALUATOR_OPTIONS,
        evaluator_thinking=EVALUATOR_THINKING,
        criteria_config=CRITERIA_CONFIG,
        ground_truths_path=GROUND_TRUTHS_FILE,
        test_query_ids=TEST_QUERY_IDS if TEST_MODE else None,
        test_model=TEST_MODEL if TEST_MODE else None,
    )

    print("Output folder:", result["output_dir"])
    print("All rows file:", result["all_rows_file"])
    print("Model/mode/query by criterion:", result["model_mode_query_criterion_file"])
    print("Model/mode by criterion:", result["model_mode_criterion_file"])
    print("Query by criterion:", result["query_criterion_file"])
    print("Model/mode/query summary:", result["model_mode_query_file"])
    print("Model/mode overall:", result["model_mode_file"])
    print("Query overall:", result["query_file"])

    model_mode_query_criterion_df = cast(
        pd.DataFrame, result["model_mode_query_criterion_df"]
    )
    print("\nModel/mode/query by criterion preview:\n")
    print(model_mode_query_criterion_df.to_string(index=False))

    model_mode_criterion_df = cast(pd.DataFrame, result["model_mode_criterion_df"])
    print("\nModel/mode by criterion preview:\n")
    print(model_mode_criterion_df.to_string(index=False))

    query_criterion_df = cast(pd.DataFrame, result["query_criterion_df"])
    print("\nQuery by criterion preview:\n")
    print(query_criterion_df.to_string(index=False))

    model_mode_query_df = cast(pd.DataFrame, result["model_mode_query_df"])
    print("\nModel/mode/query summary preview:\n")
    print(model_mode_query_df.to_string(index=False))

    model_mode_df = cast(pd.DataFrame, result["model_mode_df"])
    print("\nModel/mode overall preview:\n")
    print(model_mode_df.to_string(index=False))

    query_df = cast(pd.DataFrame, result["query_df"])
    print("\nQuery overall preview:\n")
    print(query_df.to_string(index=False))
