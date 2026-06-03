import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import utils
from ollama import Client

models = {
    # "deepseek-r1:8b": {
    #     "enabled": True,
    #     "display_name": "DeepSeek R1 8B",
    #     "parameters": "8B",
    #     "supports_thinking": False,
    #     "temperature": 0.1,
    #     "g_cypher": True,
    #     "g_sparql": True,
    # },
    # "ministral-3:3b": {
    #     "enabled": True,
    #     "display_name": "Ministral 3 3B",
    #     "parameters": "3B",
    #     "supports_thinking": False,
    #     "temperature": 0.05,
    #     "g_cypher": True,
    #     "g_sparql": True,
    # },
    # "ministral-3:8b": {
    #     "enabled": True,
    #     "display_name": "Ministral 3 8B",
    #     "parameters": "8B",
    #     "supports_thinking": False,
    #     "temperature": 0.15,
    #     "g_cypher": True,
    #     "g_sparql": True,
    # },
    "ministral-3:14b": {
        "enabled": True,
        "display_name": "Ministral 3 14B",
        "parameters": "14B",
        "supports_thinking": False,
        "temperature": 0.1,
        "g_cypher": True,
        "g_sparql": True,
    },
    # "mistral-nemo:12b": {
    #     "enabled": True,
    #     "display_name": "Mistral Nemo 12B",
    #     "parameters": "12B",
    #     "supports_thinking": False,
    #     "temperature": 0.15,
    #     "g_cypher": True,
    #     "g_sparql": True,
    # },
    # "mistral:7b": {
    #     "enabled": True,
    #     "display_name": "Mistral 7B",
    #     "parameters": "7B",
    #     "supports_thinking": False,
    #     "temperature": 0.15,
    #     "g_cypher": True,
    #     "g_sparql": True,
    # },
    # "phi4:14b": {
    #     "enabled": True,
    #     "display_name": "Phi-4 14B",
    #     "parameters": "14B",
    #     "supports_thinking": False,
    #     "temperature": 0.15,
    #     "g_cypher": True,
    #     "g_sparql": True,
    # },
    # "gemma4:e2b": {
    #     "enabled": True,
    #     "display_name": "Gemma 4 E2B",
    #     "parameters": "2B",
    #     "supports_thinking": True,
    #     "temperature": 0.05,
    #     "g_cypher": True,
    #     "g_sparql": True,
    # },
    # "gemma4:e4b": {
    #     "enabled": True,
    #     "display_name": "Gemma 4 E4B",
    #     "parameters": "4B",
    #     "supports_thinking": True,
    #     "temperature": 0.05,
    #     "g_cypher": True,
    #     "g_sparql": True,
    # },
    "gemma4:26b": {
        "enabled": True,
        "display_name": "Gemma 4 26B",
        "parameters": "26B",
        "supports_thinking": False,
        "temperature": 0.05,
        "g_cypher": True,
        "g_sparql": True,
    },
    # "qwen3.5:9b": {
    #     "enabled": True,
    #     "display_name": "Qwen 3.5 9B",
    #     "parameters": "9B",
    #     "supports_thinking": False,
    #     "temperature": 0.1,
    #     "g_cypher": True,
    #     "g_sparql": True,
    # },
    "qwen3.6:35b-a3b": {
        "enabled": True,
        "display_name": "Qwen 3.6 35B-A3B",
        "parameters": "35B-A3B",
        "supports_thinking": False,
        "temperature": 0.1,
        "g_cypher": True,
        "g_sparql": True,
    },
    # "llama3.1:8b": {
    #     "enabled": True,
    #     "display_name": "Llama 3.1 8B",
    #     "parameters": "8B",
    #     "supports_thinking": False,
    #     "temperature": 0.1,
    #     "g_cypher": True,
    #     "g_sparql": True,
    # },
}

# queries = [
#     {
#         "id": "Q01",
#         "text": "Give me the movies that have more than four actors with the same birth year",
#     },
#     {
#         "id": "Q02",
#         "text": "Give me the movies that have more than four actors born in the same year as another actor in the cast",
#     },
#     {
#         "id": "Q03",
#         "text": "Give me the director and actors of any 1990 movie, provided that one of the actors was born in 2002",
#     },
#     {
#         "id": "Q04",
#         "text": "Give me the shortest path between Article where title is Open sets satisfying systems of congruences and Report, with report_id equal 5049b80a2935f95cc95cf14dbfb8c610, including the nodes on the path!",
#     },
#     {
#         "id": "Q05",
#         "text": "Give me the name of the Application that has the most incoming connections from other Applications",
#     },
#     {
#         "id": "Q06",
#         "text": "Give me the nodes that are 3 hops away from Keyword for which key_id=6ded85146e3dbfb1bb866831b8948f5b!",
#     },
#     {
#         "id": "Q07",
#         "text": "Give me the movies that have an actor with more salary than Meryl Streep and Clint Eastwood together",
#     },
#     {
#         "id": "Q08",
#         "text": "Give me the actors whose father is among the top 5 highest-paid directors",
#     },
#     {
#         "id": "Q09",
#         "text": "Give me the movies that have no actors that have work with Meryl Streep in any movie",
#     },
#     {
#         "id": "Q10",
#         "text": "Give me the movies where all the main actors have won more awards than any Argentine actor",
#     },
#     {
#         "id": "Q11",
#         "text": "Give me the actors who got married in 1980 where one of them appears in The Matrix?",
#     },
#     {
#         "id": "Q12",
#         "text": "Give me the actors of The Matrix along with the three actors who have acted the most in any movie with them",
#     },
#     {
#         "id": "Q13",
#         "text": "Give me the movies and its featuring actors that have won an Oscar",
#     },
#     {
#         "id": "Q14",
#         "text": "Give me the people who have directed or acted in more than 5 occasions",
#     },
# ]

queries = [
    {
        "id": "Q01",
        "text": "Give me the communication routes between the server with ID 'SR45' and any server at the University of Oviedo.",
    },
    {
        "id": "Q02",
        "text": "Give me each Queen of England along with the list of their residences.",
    },
    {
        "id": "Q03",
        "text": "Give me the third-degree relatives of Alfonso X.",
    },
    {
        "id": "Q04",
        "text": "Give me all the groups that directly or indirectly influenced Queen.",
    },
    {
        "id": "Q05",
        "text": "Give me the routes from Madrid to Barcelona that do not pass through Huesca.",
    },
    {
        "id": "Q06",
        "text": "Give me the list of salaries of Málaga players who are under 20 years old.",
    },
    {
        "id": "Q07",
        "text": "Give me the routes between Oviedo and Málaga whose total distance is less than 1000 km.",
    },
    {
        "id": "Q08",
        "text": "Give me the universities that rank between 10th and 20th in terms of highest funding.",
    },
    {
        "id": "Q09",
        "text": "Give me the actors whose father has more money than the top 5 highest-paid directors combined.",
    },
    {
        "id": "Q10",
        "text": "Give me the movies in which all the main actors earn more money than the highest-paid Argentine actor.",
    },
]

OLLAMA_SERVER = "http://156.35.95.33:11434"
OLLAMA_OPTIONS = {
    # Limita la respuesta generada. Para modelos con "Thinking" (CoT),
    # el límite debe ser alto para acomodar el bloque de razonamiento.
    "num_predict": 3072,
    # Define el tamaño de contexto total (entrada + salida esperada).
    # He tenido prompts de hasta 4000 tokens.
    "num_ctx": 8192,
}

SYSTEM_PROMPTS_PATHS = [
    "prompts/SYSTEM_PROMPT_LISTS_v1.prompt.md",
    "prompts/SYSTEM_PROMPT_LISTS_v2.prompt.md",
    "prompts/SYSTEM_PROMPT_LISTS_v3.prompt.md",
]
RUNS_PER_MODEL = 5
OUTPUT_DIR = "outputs/summary"
CONFIDENCE_LEVEL = None  # Usa None para no calcular intervalos de confianza

ollama_client = Client(OLLAMA_SERVER)

for prompt_path in SYSTEM_PROMPTS_PATHS:
    print(f"\n==================================================")
    print(f"Executing evaluation for prompt: {prompt_path}")
    print(f"==================================================")

    system_prompt = utils.load_prompt_file(prompt_path)

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
