import utils

from ollama import Client

models = [
    # "deepseek-r1:8b",
    # "ministral-3:8b",
    # "phi4:14b",
    # "mistral-nemo:12b",
    # "mistral:7b",
    # "gemma4:e2b",
    # "gemma4:e4b",
    # "gemma4:26b",
    # "llama3.1:8b",
    # "qwen3.5:9b",
    "qwen3.6:35b-a3b",
]

queries = [
    "Give me the films directed by Eastwood and starring Meryl Streep",
    "Give me the films whose actors won an Oscar",
    "Give me the films featuring more than three actors born after 1980",
    "Give me the films whose directors have the same surname as one of the actors",
    "Give me the films in which all the actors are US citizens",
]

OLLAMA_SERVER = "http://156.35.95.33:11434"
OLLAMA_OPTIONS = {}

SYSTEM_PROMPT = utils.SYSTEM_PROMPT
EVAL_QUERY = "Music albums where the lead singer was born in the same country as the album's producer"
TEMPERATURE_CANDIDATES = [
    0.025,
    0.05,
    0.1,
    0.15,
    0.2,
    0.25,
]
RUNS_PER_TEMPERATURE = 10
VARIABILITY_THRESHOLD = 20.0  # percent
THINKING = False
OUTPUT_DIR = "outputs/temperatures"

ollama_client = Client(OLLAMA_SERVER)

all_results = {}
all_recommended = {}

for model_name in models:
    results = utils.evaluate_temperature_candidates(
        ollama_client=ollama_client,
        model_name=model_name,
        query=EVAL_QUERY,
        system_prompt=SYSTEM_PROMPT,
        base_options=OLLAMA_OPTIONS,
        temperature_candidates=TEMPERATURE_CANDIDATES,
        runs_per_temperature=RUNS_PER_TEMPERATURE,
        variability_threshold=VARIABILITY_THRESHOLD,
        thinking=THINKING,
    )

    report = utils.build_temperature_evaluation_report(
        model_name=model_name,
        query=EVAL_QUERY,
        threshold=VARIABILITY_THRESHOLD,
        results=results,
    )

    print(report)
    print("\n" + "=" * 80 + "\n")

    saved_path = utils.save_temperature_report(OUTPUT_DIR, model_name, report)
    print(f"Saved report: {saved_path}\n")

    all_results[model_name] = results
    all_recommended[model_name] = utils.select_closest_below_threshold(
        results, VARIABILITY_THRESHOLD
    )
