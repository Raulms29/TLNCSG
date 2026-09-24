import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import utils
import json
from ollama import Client
from config import OLLAMA_SERVER

# ---------------------------------------------------------------------------
# Source models under evaluation
# ---------------------------------------------------------------------------
models = {
    "ministral-3:14b": {
        "enabled": True,
        "display_name": "Ministral 3 14B",
        "parameters": "14B",
        "supports_thinking": False,
        "temperature": 0.0,
        "g_cypher": True,
        "g_sparql": True,
    },
    "gemma4:26b": {
        "enabled": True,
        "display_name": "Gemma 4 26B",
        "parameters": "26B",
        "supports_thinking": False,
        "temperature": 0.0,
        "g_cypher": True,
        "g_sparql": True,
    },
    "qwen3.6:35b": {
        "enabled": True,
        "display_name": "Qwen 3.6 35B",
        "parameters": "35B",
        "supports_thinking": False,
        "temperature": 0.0,
        "g_cypher": True,
        "g_sparql": True,
    },
}

# ---------------------------------------------------------------------------
# System prompts and their associated ground truths
# ---------------------------------------------------------------------------

SYSTEM_PROMPTS_CONFIG = {
    # ------------------------------------------------------------------
    # Lambda DCS
    # ------------------------------------------------------------------
    "prompts/grammars/SYSTEM_PROMPT_LAMBDA_DCS.prompt.md": {
        "ground_truth": "ground_truths/class_a/ground_truth_lambda_dcs.json",
        "use_representation_weights": True,
        "expect_json_response": False,
    },
    # ------------------------------------------------------------------
    # PCCG CGG Lambda
    # ------------------------------------------------------------------
    "prompts/grammars/SYSTEM_PROMPT_PCCG_CGG_LAMBDA.prompt.md": {
        "ground_truth": "ground_truths/class_a/ground_truth_pccg_cgg_lambda.json",
        "use_representation_weights": True,
        "expect_json_response": False,
    },
    # ------------------------------------------------------------------
    # NSQA
    # ------------------------------------------------------------------
    "prompts/grammars/SYSTEM_PROMPT_NSQA.prompt.md": {
        "ground_truth": "ground_truths/class_c/ground_truth_nsqa.json",
        "use_representation_weights": True,
        "expect_json_response": False,
    },
    # ------------------------------------------------------------------
    # Squall
    # ------------------------------------------------------------------
    "prompts/grammars/SYSTEM_PROMPT_SQUALL.prompt.md": {
        "ground_truth": "ground_truths/class_d/ground_truth_squall.json",
        "use_representation_weights": True,
        "expect_json_response": False,
    },
    # ------------------------------------------------------------------
    # GraphQ Tree
    # ------------------------------------------------------------------
    "prompts/grammars/SYSTEM_PROMPT_GRAPHQ_TREE.prompt.md": {
        "ground_truth": "ground_truths/class_e/ground_truth_graphq_tree.json",
        "use_representation_weights": True,
        "expect_json_response": False,
    },
    # ------------------------------------------------------------------
    # SemGIR
    # ------------------------------------------------------------------
    "prompts/grammars/SYSTEM_PROMPT_SEM_GIR.prompt.md": {
        "ground_truth": "ground_truths/ground_truth_sem_gir.json",
        "use_representation_weights": True,
        "expect_json_response": True,
    },
    # ------------------------------------------------------------------
    # SemGIR Base
    # ------------------------------------------------------------------
    "prompts/grammars/SYSTEM_PROMPT_SEM_GIR_BASE.prompt.md": {
        "ground_truth": "ground_truths/ground_truth_sem_gir.json",
        "use_representation_weights": True,
        "expect_json_response": True,
    },
}

# ---------------------------------------------------------------------------
# Ollama inference options (shared across all models)
# ---------------------------------------------------------------------------

OLLAMA_OPTIONS = {
    # Limits the generated response. For models with "Thinking" (CoT),
    # the limit must be high to accommodate the reasoning block.
    "num_predict": 3072,
    # Defines the total context size (input + expected output).
    "num_ctx": 12288,
}

# ---------------------------------------------------------------------------
# Run configuration
# ---------------------------------------------------------------------------

RUNS_PER_MODEL = 30
OUTPUT_DIR = "outputs/model_eval"
# Confidence level for statistical intervals. Set to None to disable calculating
# and displaying confidence intervals in all aggregate output tables.
CONFIDENCE_LEVEL = 0.95

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

ollama_client = Client(OLLAMA_SERVER)

if __name__ == "__main__":
    for prompt_path, config in SYSTEM_PROMPTS_CONFIG.items():
        print(f"\n==================================================")
        print(f"Executing evaluation for prompt: {prompt_path}")
        print(f"==================================================")

        # 1. Load config values for this specific prompt
        gt_path = config["ground_truth"]
        use_weights = config.get("use_representation_weights", True)
        expect_json = config.get("expect_json_response", True)

        # 2. Dynamically load queries and weights from the associated ground truth file
        gt_full_path = os.path.join(os.path.dirname(__file__), "..", gt_path)
        with open(gt_full_path, "r", encoding="utf-8") as f:
            queries_data = json.load(f)
        queries = [
            {
                "id": q_id,
                "text": q_info["query"],
                "representation_weight": float(
                    q_info.get("representation_weight", 1.0)
                ),
            }
            for q_id, q_info in queries_data.items()
        ]

        prompt_full_path = os.path.join(os.path.dirname(__file__), "..", prompt_path)
        system_prompt = utils.load_prompt_file(prompt_full_path)

        # Save outputs under a subdirectory named after the prompt file to prevent conflicts
        prompt_name = os.path.basename(prompt_path).replace(".prompt.md", "")
        prompt_output_dir = os.path.join(OUTPUT_DIR, prompt_name)

        (
            results_df,
            model_comparison_df,
            model_files,
            query_files,
            execution_files,
            all_results_file,
            model_comparison_file,
        ) = utils.run_models_summary(
            ollama_client=ollama_client,
            models=models,
            queries=queries,
            system_prompt=system_prompt,
            base_options=OLLAMA_OPTIONS,
            runs_per_model=RUNS_PER_MODEL,
            output_dir=prompt_output_dir,
            confidence_level=CONFIDENCE_LEVEL,
            use_representation_weights=use_weights,
            expect_json_response=expect_json,
        )

        print(f"\nFinished evaluation for prompt: {prompt_path}")
        print("Saved per-model files:")
        for file_path in model_files:
            print(f"- {file_path}")

        print("Saved per-query files:")
        for file_path in query_files:
            print(f"- {file_path}")

        print("Saved execution files (query + model + mode):")
        for file_path in execution_files:
            print(f"- {file_path}")

        print(f"Saved master file: {all_results_file}")
        print(f"Saved model comparison file: {model_comparison_file}")

        print("\nModel comparison summary:")
        print(model_comparison_df.to_string())

        print("\nDetailed results:")
        print(results_df.to_string())
