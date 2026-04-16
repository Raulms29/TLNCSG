import utils
from ollama import Client

models = {
    "ministral-3:8b": {
        "enabled": True,
        "display_name": "Ministral 3 8B",
        "parameters": "8B",
        "supports_thinking": False,
        "temperature": 0.1,
        "g_cypher": True,
        "g_sparql": True,
    },
    "phi4:14b": {
        "enabled": True,
        "display_name": "Phi-4 14B",
        "parameters": "14B",
        "supports_thinking": False,
        "temperature": 0.15,
        "g_cypher": True,
        "g_sparql": True,
    },
    "mistral-nemo:12b": {
        "enabled": True,
        "display_name": "Mistral Nemo 12B",
        "parameters": "12B",
        "supports_thinking": False,
        "temperature": 0.1,
        "g_cypher": True,
        "g_sparql": True,
    },
    "mistral:7b": {
        "enabled": True,
        "display_name": "Mistral 7B",
        "parameters": "7B",
        "supports_thinking": False,
        "temperature": 0.15,
        "g_cypher": True,
        "g_sparql": True,
    },
    "gemma4:e2b": {
        "enabled": True,
        "display_name": "Gemma 4 E2B",
        "parameters": "2B",
        "supports_thinking": True,
        "temperature": 0.05,
        "g_cypher": True,
        "g_sparql": True,
    },
    "gemma4:e4b": {
        "enabled": True,
        "display_name": "Gemma 4 E4B",
        "parameters": "4B",
        "supports_thinking": True,
        "temperature": 0.05,
        "g_cypher": True,
        "g_sparql": True,
    },
    "gemma4:26b": {
        "enabled": True,
        "display_name": "Gemma 4 26B",
        "parameters": "26B",
        "supports_thinking": False,
        "temperature": 0.05,
        "g_cypher": True,
        "g_sparql": True,
    },
    "llama3.1:8b": {
        "enabled": True,
        "display_name": "Llama 3.1 8B",
        "parameters": "8B",
        "supports_thinking": False,
        "temperature": 0.1,
        "g_cypher": True,
        "g_sparql": True,
    },
}

queries = [
    {
        "id": "Q01",
        "text": "Give me the films directed by Eastwood and starring Meryl Streep",
    },
    {
        "id": "Q02",
        "text": "Give me the films whose actors won an Oscar",
    },
    {
        "id": "Q03",
        "text": "Give me the films featuring more than three actors born after 1980",
    },
    {
        "id": "Q04",
        "text": "Give me the directors whose surname is the same as that of one of the actors",
    },
    {
        "id": "Q05",
        "text": "Give me the films in which all the actors are US citizens",
    },
]

OLLAMA_SERVER = "http://156.35.95.33:11434"
OLLAMA_OPTIONS = {}

SYSTEM_PROMPT = utils.SYSTEM_PROMPT
RUNS_PER_MODEL = 30
OUTPUT_DIR = "outputs/summary"
CONFIDENCE_LEVEL = 0.95

ollama_client = Client(OLLAMA_SERVER)

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
    system_prompt=SYSTEM_PROMPT,
    base_options=OLLAMA_OPTIONS,
    runs_per_model=RUNS_PER_MODEL,
    output_dir=OUTPUT_DIR,
    confidence_level=CONFIDENCE_LEVEL,
)

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
