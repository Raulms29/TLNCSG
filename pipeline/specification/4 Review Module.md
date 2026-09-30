## General Objective
Create an interactive tool for the human researcher to supervise, validate, and correct the evaluations made by the LLM in Module 3, additionally adding a qualitative error analysis.
## User Interface (UI) with Streamlit
**Streamlit** will be used, which allows building complete interactive web applications using the Python language imperatively.
## Workflow and Validations
The screen will display the plain text query and its IDs, the group (e.g., 3 of 4) and the representative query, along with the transformed LISP or SQL for AMBROSIA, the evaluator's verdict, and its reasoning.
The researcher will have two paths:
1. **Agreement with the LLM:**
    * If it is the **highest mark (Correct)**: No changes. The system automatically moves to the next group.
    * If it is **Incorrect**: The user categorizes the solution's error using the menu, with an additional text field to indicate the reason (optional).
2. **Disagreement with the LLM (Discrepancy):**
    * The user indicates in text the reason for the discrepancy (being recorded in the model's document).
    * If the user establishes that it is **Correct**: Moves to the next one.
    * If the user establishes that it is **Incorrect**: Categorizes the error.
### Express Validation of Hypothesis Coverage
If the reviewed query has multiple interpretations (multiple *Ground Truths*), the automatic evaluator reported a breakdown of the hypotheses it considered covered (Module 3). The human reviewer **must confirm or adjust** this validated numerical value, consolidating it as definitive for the Module 5 calculations.
## Qualitative Error Analysis (Categories)
A selector menu (dropdown) will be displayed to qualitatively group the failures. Initial proposal of categories:
* Semantic omission
* Wrong relation
* Wrong variable binding
* Aggregation error
* Structural error
* Ambiguity/hypothesis error
* Hallucination
* Syntax/format error
## Persistence and Iteration
* **Save by Query:** Progress must be persisted **upon finishing/confirming the review of each individual query**. This ensures being able to progressively resume the work without losing work if there is an interruption.
* **Speed Toggle:** The interface must provide a *switch* to temporarily disable strict qualitative analysis, allowing quick validations based purely on correctness or failure.
* **Outputs:** Three outputs will be generated from this process: the grouped CSV with definitive assessments, a document with the categorized errors of the base LLM, and a document with the evaluation failures committed by the Judge LLM.
