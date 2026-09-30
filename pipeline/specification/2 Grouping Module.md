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
## Persistence Structure
From the output of Module 1, documents will be generated that include a representative output of the set and the total number of queries that are part of that group (e.g. 20 of 30). The execution id (_id_) will be maintained.

```text
outputs
└───script2
    └───script-start-date_script-end-date_id
        ├───GRAMMAR1
        │   ├───gemma4-26b
        │   │       Q1-R_grouped.csv
        │   │       Q1_grouped.csv
        │   │       Q200-R_grouped.csv
        │   │       ...
```
