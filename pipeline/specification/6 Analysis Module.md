## General Objective
This module will be composed of one or several **Jupyter Notebooks (`.ipynb`)** aimed exclusively at extracting graphical conclusions and formatting tables for their subsequent direct inclusion in the final document.
## Graphical and Tabular Analysis Flow
1. **Qualitative Error Analysis:**
    * Tabulation and creation of charts (e.g., *pie charts* or *bar charts*) of the failure categories manually recorded in Script 4 (e.g., *Semantic Omission*, *Hallucination*, *Syntax error*). 
    * This visual breakdown will allow discovering in which grammar (SemGIR vs SQUALL vs GraphQ) the models fail the most according to the semantic error type.
2. **Quantitative Complexity Analysis:**
    * Crossing of the pure metric data originally yielded in Script 1 (using the `summary.csv` and `summary_per_query.csv` documents that contain inference times and raw token consumption).
    * The objective will be to generate comparative tables that contrast the average size (in tokens and characters) that it costs to generate **SemGIR** against **SQUALL** and **GraphQ**.
3. **Final Global Metrics:**
    * Definitive summary tables exposing and visually comparing the `Pass@30`, `Success Rate`, and the `Ambiguity Coverage` calculated previously in Script 5.
*Note:* These Notebooks will serve as the final presentation layer, providing the graphical resources directly embeddable into the academic work.
