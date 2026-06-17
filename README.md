# Model Evaluation

Benchmark and evaluation pipeline for local LLMs served via [Ollama](https://ollama.com). Part of the Master's thesis (TFM) titled *"Transforming Natural Language into Graph Queries"*.

## Overview

The project consists of four independent but composable modules:

- **Model Benchmark (`model_eval`)** — Runs each model against a set of natural language queries across multiple grammars. It measures inference time, JSON validity rate, and throughput.
- **Query Evaluation (`query_eval`)** — Uses an LLM-as-judge to score the models' responses across six fine-grained linguistic criteria (e.g., Syntactic Correctness, Semantic Faithfulness) against a fixed ground truth.
- **Grammar Evaluation (`grammar_eval`)** — Compares model performance across different grammar variants of the same intermediate representation (IR) using holistic evaluator prompts. It aggregates the results to find the most effective grammar.
- **Autoresearch (`autoresearch`)** — Autonomous loop that iteratively improves the generator system prompt via an LLM-as-optimizer strategy.

---

## Setup

**Requirements:** Python 3.10+, Ollama server.

```bash
pip install -r requirements.txt
```

**Configuration:** The Ollama server URL is defined in a single file at the project root.
Edit [`config.py`](config.py) to update the endpoint for all scripts:
```python
OLLAMA_SERVER = "http://localhost:11434"
```

---

## Execution Scripts (`scripts/`)

For convenience and safe long-running execution, use the provided helper scripts in the `scripts/` directory. They automatically handle directory routing, logging with timestamps, and error redirection. The scripts are organised into `scripts/windows/` (`.ps1`) and `scripts/linux/` (`.sh`).

> **Tip:** For long runs, it is highly recommended to use `tmux` so the process survives SSH disconnections:
> ```bash
> tmux new -s eval_run
> ./scripts/linux/run_model_eval.sh
> # Detach with Ctrl+B, D
> ```

**To run a script:**
- **Linux/macOS:** Run `./scripts/linux/<script_name>.sh` from the terminal.
- **Windows:** Run `.\scripts\windows\<script_name>.ps1` from PowerShell.

### Detailed Script Behaviors

| Script | Purpose & Outputs | Configuration |
|---|---|---|
| `run_temperature` | **Purpose:** Finds the optimal generation temperature for each model.<br>**Outputs:** Temperature reports saved to `outputs/temperatures/`. | Edit `models` and `TEMPERATURE_CANDIDATES` in `model_eval/temperature.py`. |
| `run_model_eval` | **Purpose:** Iterates over every configured grammar, running all models against the natural language queries. Records the raw outputs, execution times, and JSON validity.<br>**Outputs:** CSV files saved to `outputs/summary/<grammar_name>/<timestamp>/`. | Configured via `SYSTEM_PROMPTS_CONFIG` and `RUNS_PER_MODEL` in `model_eval/model_eval.py`. |
| `run_query_eval` | **Purpose:** Evaluates a specific Model Benchmark run. An LLM acts as a judge, comparing the models' IR outputs against the ground truth across 6 linguistic criteria (`A1_CS` to `A6_AP`).<br>**Outputs:** Scored CSVs saved progressively to `outputs/query_eval/<timestamp>/`. | Set `SUMMARY_RUN_DIR` and `EVALUATOR_MODEL` in `query_eval/query_eval.py`. |
| `run_grammar_eval` | **Purpose:** Evaluates multiple Model Benchmark runs (one per grammar) using a holistic 0–1 evaluator prompt for each grammar. Produces cross-grammar comparison tables.<br>**Outputs:** Individual and combined CSVs saved progressively to `outputs/grammar_eval/<timestamp>/`. | Configure the `summary_run_dir` (`<<FILL_RUN_DIR>>`) for each grammar in `grammar_eval/grammar_eval.py`. |
| `run_autoresearch` | **Purpose:** Runs the autonomous prompt optimization loop. It generates IRs, evaluates them, and asks an optimizer LLM to rewrite the prompt based on failures.<br>**Outputs:** Experiment history appended to `autoresearch/experiments.json` and logs. | Edit `autoresearch/config.json` for models, context sizes, and loop thresholds. |
| `run_autoresearch_reset` | **Purpose:** Hard resets the Autoresearch state.<br>**Outputs:** Clears `experiments.json` and starts the loop fresh. | N/A |

---

## Project Structure

```text
Model Evaluation/
├── config.py                             # Shared config (OLLAMA_SERVER)
├── scripts/                              # Helper execution scripts
│   ├── windows/                          # PowerShell (.ps1) scripts
│   └── linux/                            # Bash (.sh) scripts
├── prompts/                              # System and evaluation prompts
│   ├── generator.prompt.md               # Main SemGIR system prompt 
│   ├── evaluator.prompt.md               # Holistic 0–1 evaluator for SemGIR
│   ├── optimizer.prompt.md               # Prompt optimiser instructions
│   └── grammars/                         # Alternative grammars
│       └── eval/                         # Evaluator prompts per grammar
├── ground_truths/                        # Ground truth answers for queries
│   ├── ground_truth_sem_gir.json         # Main SemGIR ground truths
│   └── class_a/ ... class_e/             # Ground truths for other grammars
├── model_eval/                           # Benchmark scripts
│   ├── model_eval.py                     # Main benchmark loop
│   └── temperature.py                    # Temperature calibration
├── query_eval/                           # LLM-as-judge evaluation engine
│   ├── query_eval.py                     # Entry point
│   └── utils/                            # Evaluation engine logic
├── grammar_eval/                         # Cross-grammar comparison engine
│   ├── grammar_eval.py                   # Entry point
│   └── utils/                            # Grammar-aware evaluation logic
├── autoresearch/                         # Autonomous prompt optimisation loop
│   ├── config.json                       # Autoresearch settings
│   └── experiments.json                  # Persisted experiment history
└── outputs/                              # Generated artefacts & logs
    ├── summary/                          # Model benchmark outputs
    ├── query_eval/                       # Query evaluation outputs
    └── grammar_eval/                     # Cross-grammar outputs
```
