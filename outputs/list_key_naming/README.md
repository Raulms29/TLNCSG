# List key naming in aggregates and quantifiers
Whether renaming the `list` key of `SCALAR_AGGREGATE` and `QUANTIFIER_PREDICATE` stops generators from confusing the two list levels. In the grammar a LIST is `{"list": CREATE_LIST, ...}`, and an aggregate or quantifier holds a LIST under the key `list`, so a correct aggregate has `"list": {"list": {"list_elements": ...}}`. Models often write a single level, `"list": {"list_elements": ...}`.

## Setup

- **Models:** qwen3.8:27b, ministral-3:14b and gemma4:26b, temperature 0, no thinking, `num_ctx` 16384, `num_predict` 3072, on local Ollama.
- **Prompt:** `SYSTEM_PROMPT_SEM_GIR_BASE.prompt.md`. In each variant the key is renamed in the two grammar lines and in the 7 example lines where an aggregate or quantifier holds a LIST. The LIST's own `list` key and `COUNT`'s `count` key are unchanged.
- **Keys:** `list` (the current prompt), `over`, `source` and `collection`.
- **Questions:**
  - **Run 1:** 76 questions. 52 hand-written queries whose solution has an aggregate, a quantifier or a count, and 24 GrailQA train questions (8 argmax, 8 argmin, 8 count, seed 42). All four keys.
  - **Run 2:** 180 other GrailQA train questions (60 argmax, 60 argmin, 60 count, seed 7). Keys `over`, `source` and `collection`, to check whether the differences between them in run 1 were noise.
- **Check:** structural, on every aggregate or quantifier node of each parseable answer:
  - **ok:** the variant's key holds a LIST, and the node has no `list` key (for the renamed variants);
  - **old key:** a renamed variant's node uses `list` instead;
  - **one level:** the key holds a CREATE_LIST directly;
  - **other:** anything else.
  - `COUNT` nodes are checked too: ok when `count` holds a LIST.

## Results

Aggregate and quantifier nodes with the right nesting (errors in brackets):

| Model | Run | `list` | `over` | `source` | `collection` |
|---|---|---|---|---|---|
| qwen3.8:27b | 1 | 31/33 (2 one level) | 35/35 | 34/34 | 34/34 |
| qwen3.8:27b | 2 | | 30/30 | 35/35 | 36/36 |
| ministral-3:14b | 1 | 16/40 (20 one level, 4 other) | 57/57 | 55/55 | 52/53 (1 old key) |
| ministral-3:14b | 2 | | 140/143 (3 old key) | 96/101 (5 old key) | 107/116 (9 old key) |
| gemma4:26b | 1 | 35/42 (7 one level) | 40/41 (1 old key) | 40/40 | 42/42 |
| gemma4:26b | 2 | | 26/26 | 27/27 | 29/29 |

`COUNT` nodes are all correct except gemma4 with `list` in run 1 (30/35). Every variant has at most 4 unparseable answers out of 76, and at most 1 out of 180.

## Findings

- **Renaming fixes most of the confusion.** With `list`, ministral nested 40% of its aggregates correctly and gemma4 83%. With any other key, every model is above 92%, and qwen and gemma4 make no errors in run 2.
- **The remaining errors are the same mistake.** All 17 "old key" nodes in run 2 are ministral writing `"list": {"list_elements": ...}`: one level, under the old name. One question (2104439001000) fails with all three keys.
- **Between the three names, the differences are mostly noise.** For ministral in run 2 the error rate is 2.1% with `over`, 5.0% with `source` and 7.8% with `collection`. Fisher's exact test gives p = 0.28 for `over` vs `source` and 0.58 for `source` vs `collection`. Only `over` vs `collection` (p = 0.04) is borderline, and the test assumes independent nodes, which they are not (several nodes come from the same answer or question).
- **ministral uses aggregates much more than the others** on argmax/argmin questions (101–143 nodes against 26–36). qwen and gemma4 mostly express them another way, so run 2 tests them on fewer nodes.

## Files

- `summary.csv`: per run, model and key, the number of answers, unparseable answers, aggregate/quantifier nodes by check result and `COUNT` nodes.
- `checks.csv`: one row per generation (2,532 rows), with the question's source and the check counts for that answer.