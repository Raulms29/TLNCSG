# Model Evaluation

Benchmark and evaluation pipeline for local LLMs served via [Ollama](https://ollama.com). Part of a Master's thesis (TFM) on semantic parsing.

## Overview

The project consists of three independent but composable evaluation modules:

- **Model Benchmark (`model_eval`)** — runs each model against a set of natural language queries and measures inference time, JSON validity rate, and throughput.
- **Query Evaluation (`query_eval`)** — uses a judge LLM to score each model's responses across multiple linguistic criteria against a fixed ground truth. This is combined with the `model_eval` outputs to assess the quality of the models.
- **Grammar Evaluation (`grammar_eval`)** — compares model performance across two different grammar versions of the same IR, producing both per-grammar and combined cross-grammar reports. This is combined with the `model_eval` outputs to compare the grammars themselves.

---

## Setup

**Requirements:**
- Python 3.10+
- An Ollama server running and accessible

```bash
pip install -r requirements.txt
```

*Note: All scripts must be run from the **project root** (`Model Evaluation/`).*

---

## Usage

### Temperature Calibration

Find the optimal temperature for each model before running the full benchmark.

```bash
python model_eval/temperature.py
```

Edit the `models` list and `TEMPERATURE_CANDIDATES` inside the script to configure the search. Reports are saved to `outputs/temperatures/`.

### Model Benchmark

```bash
python model_eval/model_eval.py
```

Configure `models`, `queries`, `RUNS_PER_MODEL`, and `OLLAMA_SERVER` at the top of the file. Results are saved to `outputs/summary/<timestamp>/`.

> **Tip:** For long runs it is recommended to use `tmux` so the process survives disconnections:
> ```bash
> tmux new -s model_eval
> python3 -u model_eval/model_eval.py | ts '%Y-%m-%d %H:%M:%S' | tee model_eval.log
> # Detach with Ctrl+B, D
> ```

### Query Evaluation

```bash
python -m query_eval.query_eval
```

Set `SUMMARY_RUN_DIR` to the Model Benchmark output folder you want to evaluate. Configure `EVALUATOR_MODEL`, `OLLAMA_SERVER`, and `CRITERIA_CONFIG` at the top of the file. Results are saved to `outputs/query_eval/<timestamp>/`.

Partial result files are written after every execution file processed, so the run can be interrupted and inspected at any point.

> **Tip:** To run a quick test on a single query and model before the full run, set `TEST_MODE = True`.

### Grammar Evaluation

```bash
python -m grammar_eval.grammar_eval
```

This module compares model performance across two grammar variants (SemGIR and SemGIR-Lists) using a general holistic 0–1 evaluator prompt per grammar. Before running:

1. Fill in the two `summary_run_dir` placeholders in `grammar_eval/grammar_eval.py` with the Model Benchmark output folders produced with each grammar's system prompt.
2. Configure `EVALUATOR_MODEL` and `OLLAMA_SERVER`.

Outputs are saved to `outputs/grammar_eval/<timestamp>/`:
- `semgir/` and `semgir_lists/` — independent per-grammar scored CSVs and aggregation tables.
- `combined_*.csv` — cross-grammar tables with a `Grammar` column for direct comparison.

Partial combined files are also updated after each grammar completes, so the combined view is recoverable even if the run is interrupted.

---

## Key Configuration

All runtime parameters are defined as constants at the top of each script — no CLI arguments or config files needed.

| Parameter | Where | Description |
|---|---|---|
| `OLLAMA_SERVER` | all scripts | Ollama server URL |
| `RUNS_PER_MODEL` | `model_eval.py` | Repetitions per model per query |
| `SUMMARY_RUN_DIR` | `query_eval.py` | Benchmark folder to evaluate |
| `EVALUATOR_MODEL` | `query_eval.py`, `grammar_eval.py` | Model used as judge |
| `CRITERIA_CONFIG` | `query_eval.py` | Criteria weights, prompt files, and query scope |
| `GRAMMARS_CONFIG` | `grammar_eval.py` | Per-grammar run dirs, ground truths, and criteria |
| `TEST_MODE` | `query_eval.py`, `grammar_eval.py` | Limit run to one query/model for debugging |
| `confidence_level` | `utils.run_models_summary` | Pass `None` to skip CI columns in output |

---

## Project Structure

```text
Model Evaluation/
├── utils.py                          # Shared utilities (Ollama calls, metrics, CI, I/O)
├── prompts/                          # Evaluation and system prompts
│   ├── SYSTEM_PROMPT.prompt.md       # SemGIR grammar (base)
│   ├── SYSTEM_PROMPT_LISTS.prompt.md # SemGIR-Lists grammar (extended)
│   ├── A1_CS.prompt.md               # Criterion: Syntactic Correctness
│   ├── A2_FS.prompt.md               # Criterion: Semantic Faithfulness
│   ├── A3_SQ.prompt.md               # Criterion: Structural Quality
│   ├── A4_HQ.prompt.md               # Criterion: Hypothesis Quality
│   ├── A5_MR.prompt.md               # Criterion: Minimality & Non-redundancy
│   ├── A6_AP.prompt.md               # Criterion: Aggregation & Projection
│   ├── G0_SEMGIR.prompt.md           # General 0–1 evaluator for SemGIR grammar
│   └── G0_SEMGIR_LISTS.prompt.md     # General 0–1 evaluator for SemGIR-Lists grammar
├── ground_truths/                    # Ground truth answers for queries
│   ├── ground_truth_sem_gir.json     # General SemGIR ground truths
│   ├── class_a/ … class_e/           # Per-class ground truth sets
│   └── sem_gir_comparison/           # Grammar comparison ground truths
├── model_eval/                       # Benchmark scripts
│   ├── model_eval.py                 # Benchmarks all models
│   └── temperature.py                # Temperature calibration per model
├── query_eval/                       # Evaluation scripts
│   ├── query_eval.py                 # LLM-as-judge evaluation
│   ├── query_utils.py                # Public re-exports
│   ├── ground_truths_default.json    # Default reference ground truths
│   └── utils/                        # Engine logic & helpers
├── grammar_eval/                     # Grammar comparison scripts
│   ├── grammar_eval.py               # Grammar comparison entry point
│   ├── grammar_utils.py              # Public re-exports
│   └── utils/                        # Grammar-aware evaluation engine
└── outputs/                          # Generated assets
    ├── summary/                      # Benchmark outputs
    ├── query_eval/                   # Query evaluation outputs
    ├── grammar_eval/                 # Grammar evaluation outputs
    └── temperatures/                 # Temperature reports
```

---

## Evaluation Prompts

| File | Used by | Purpose |
|---|---|---|
| `SYSTEM_PROMPT.prompt.md` | `model_eval` | SemGIR grammar definition sent to models |
| `SYSTEM_PROMPT_LISTS.prompt.md` | `model_eval` | SemGIR-Lists grammar definition sent to models |
| `A1_CS` … `A6_AP` | `query_eval` | Six linguistic criteria (0–1 score each) |
| `G0_SEMGIR.prompt.md` | `grammar_eval` | Holistic 0–1 evaluator for SemGIR grammar |
| `G0_SEMGIR_LISTS.prompt.md` | `grammar_eval` | Holistic 0–1 evaluator for SemGIR-Lists grammar |
