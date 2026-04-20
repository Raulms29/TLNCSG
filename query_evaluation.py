import pandas as pd
from typing import cast

from query_utils import evaluate_summary_folder

# Path with model execution files (executions_*.csv)
SUMMARY_RUN_DIR = "outputs/summary/20260417_201301"

# Evaluator model and runtime configuration
EVALUATOR_MODEL = "gemma4:e4b"
OLLAMA_SERVER = "http://156.35.95.33:11434"
EVALUATOR_OPTIONS = {
    "temperature": 0.0,
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
GROUND_TRUTHS_FILE = None


if __name__ == "__main__":
    result = evaluate_summary_folder(
        summary_root=SUMMARY_RUN_DIR,
        evaluator_model=EVALUATOR_MODEL,
        ollama_server=OLLAMA_SERVER,
        output_root=OUTPUT_ROOT,
        evaluator_options=EVALUATOR_OPTIONS,
        evaluator_thinking=EVALUATOR_THINKING,
        ground_truths_path=GROUND_TRUTHS_FILE,
        test_query_ids=TEST_QUERY_IDS if TEST_MODE else None,
        test_model=TEST_MODEL if TEST_MODE else None,
    )

    print("Output folder:", result["output_dir"])
    print("All rows file:", result["all_rows_file"])
    print("Model/mode/query summary:", result["model_mode_query_file"])
    print("Model/mode overall:", result["model_mode_file"])
    print("Query overall:", result["query_file"])

    model_mode_query_df = cast(pd.DataFrame, result["model_mode_query_df"])
    print("\nModel/mode/query summary preview:\n")
    print(model_mode_query_df.to_string(index=False))

    model_mode_df = cast(pd.DataFrame, result["model_mode_df"])
    print("\nModel/mode overall preview:\n")
    print(model_mode_df.to_string(index=False))

    query_df = cast(pd.DataFrame, result["query_df"])
    print("\nQuery overall preview:\n")
    print(query_df.to_string(index=False))
