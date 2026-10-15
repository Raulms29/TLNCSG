## General Objective
Reduce the volume of evaluation calls of Module 3 and human reviews of Module 4. If the LLM emitted exactly the same semantic/syntactic response for a query in 20 of the 30 iterations, these 20 are collapsed into a single group.
## Initial Grouping
It consists of grouping by direct text comparison after applying normalization.
The base code to normalize a JSON could be (subject to changes depending on the grammar and project needs):

```python
import json
import re

def normalize_llm_output(raw_text: str) -> str:
    """Normalizes the LLM output to ensure deterministic grouping."""
    # 1. Extract JSON (ignores surrounding conversational text)
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', raw_text, re.IGNORECASE)
    extracted_text = json_match.group(1) if json_match else raw_text.strip()
    
    try:
        # 2. Parse to Python object
        parsed_json = json.loads(extracted_text)
        
        # 3. Forced deterministic serialization
        return json.dumps(
            parsed_json, 
            sort_keys=True,          # Alphabetical order: nullifies order variations
            ensure_ascii=False,      # Retains special characters without escaping
            separators=(',', ':')    # Eliminates spaces after commas and colons
        )
    except json.JSONDecodeError:
        # Fallback in case the model returns broken JSON.
        # Important: Do not apply .lower() to avoid destroying semantics (e.g. Apple vs apple).
        return re.sub(r'\s+', ' ', extracted_text.strip())
```
## Secondary Grouping (Fallback by LLM)
In those cases where, after the initial normalization, there are groups composed of **a single member** or there are too many groups, an LLM can be used to determine if it is really a syntactically or semantically different interpretation, or it can be appended to a larger cluster.
*   **Grouping LLM Configuration:**
    *   `GROUPER_MODEL= "gemma4:26b"`
    *   `temperature: 0.0`
    *   `num_predict: 3072`, `num_ctx: 12288`
    *   `GROUPER_THINKING = False`
*   The model must return a justified reasoning and a `yes/no` in a JSON object.
## Cross-Model Grouping
Groups are formed per **(grammar, query)**, pooling the runs of every model and both thinking modes. An answer produced by several models is therefore evaluated and reviewed only once. Correctness depends only on the query, the output and the ground truth, so pooling does not change any verdict.

Each group keeps track of which runs it contains in the `Run Breakdown` column, a JSON object keyed by `<model directory>|<thinking>` with the run ids of that model and mode, e.g. `{"gemma4_26b|False": [1, 2, 5], "qwen3_8b|True": [3]}`. The Metrics Module uses it to split every group back into per-model counts.

Each group also gets an `Output Key`, a hash of grammar + QID + normalized output. The Review Module stores human verdicts under this key, so a verdict is reused by any later run that produces the same answer.

## Persistence Structure
From the output of Module 1, one document per query is generated, containing one row per group: `QID, Query, Output Key, Group Size, Run Breakdown, Representative Output, Reasoning, LLM Merged`. The representative is the first run in (model, thinking mode, run) order, so it is stable across reruns. The execution id (_id_) will be maintained.

```text
outputs
└───grouping
    └───script-start-date_script-end-date_id
        ├───GRAMMAR1
        │       Q1_grouped.csv
        │       Q200_grouped.csv
        │       ...
```
