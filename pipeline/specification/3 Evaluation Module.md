## General Objective
With the grouped data, this script will automatically evaluate the accuracy of the returned representations using an LLM as a judge. The evaluator will compare the solution given by the tested model against the query's *Ground Truth*.
## Input Preprocessing (LISP Adaptation)
Since the *Ground Truth* for GrailQA is in LISP notation (`s_expression` field), these expressions use Freebase IDs. To avoid having to provide too much context to the model and so it doesn't need to know the equivalence of the IDs, they will be replaced by a more readable name.
### Procedure:
1. Create an extractor function that sweeps the `nodes` and `edges` fields of the original GrailQA JSON.
2. Extract a mapping dictionary that associates the raw ID (e.g., a Freebase *mid*) with its associated `friendly_name` field.
3. Replace the IDs within the original `s_expression` with these friendly names. This more readable LISP representation will be the one introduced into the evaluation Prompt.
## Evaluation Dynamics and Prompting
* **Prompt Dimensionality:** A different evaluation prompt will be required crossing each Grammar with each Dataset used. For example, evaluating a SemGIR query is not the same if its underlying validation representation is LISP (GrailQA) or SQL (AMBROSIA).
* In the case of SQL-based datasets (AMBROSIA), the prompt will use the `db_dump` and `gold_queries` as Ground Truth instead of the LISP field.
## Evaluation of Multi-Hypothesis Queries and Persistence
When a query has multiple interpretation hypotheses (e.g., it is inherently ambiguous), the evaluator model must be able to assess it in two concurrent ways.
```json
{
  "rationale": "Concise explanation covering grammar compliance, semantic faithfulness, and comparison to the Ground Truth. It must explain in a few words the problems identified and what should have been done structurally instead of what it was, with few detail about the specific query entities or data.",
  "hypotheses_covered": "Number of hypotheses covered by the response",
  "correct": "True or False"
}
```
If the tested model correctly guesses **at least one of the correct hypotheses** (this means that the hypothesis is correct and the generated query too), the query as a whole will pass the primary validation (score of 1). This is the field considered for calculating the `Pass@30` and `Success rate` metrics.
This behavior only applies to SemGIR, as it is the only grammar that allows modeling multiple hypotheses simultaneously. This behavior will only be considered when using the AMBROSIA dataset with SemGIR.
These data will be appended to the files resulting from Module 2, but new files will be created, the ones generated in Module 2 will not be modified.
