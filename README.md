# Model Evaluation

Benchmark and evaluation pipeline for local LLMs served via [Ollama](https://ollama.com). Part of a Master's thesis (TFM) on semantic parsing.

The pipeline has two stages:

1. **Model evaluation** — runs each model against a set of natural language queries and measures inference time, JSON validity rate, and throughput.
2. **Query evaluation** — uses a judge LLM to score each model's responses across six linguistic criteria.

---

## Setup

**Requirements:** Python 3.10+, an Ollama server running and accessible.

```bash
pip install -r requirements.txt
```

All scripts must be run from the **project root** (`Model Evaluation/`).

---

## Structure

```
Model Evaluation/
├── utils.py                        # Shared utilities (Ollama calls, metrics, I/O)
├── prompts/                        # System and criterion prompt files
├── model_eval/
│   ├── model_eval.py               # Stage 1: benchmark all models
│   └── temperature.py              # Temperature calibration per model
├── query_eval/
│   ├── query_eval.py               # Stage 2: LLM-as-judge evaluation
│   ├── ground_truths_default.json  # Reference ground truths
│   └── utils/                      # Evaluation engine and aggregation logic
└── outputs/
    ├── summary/                    # Stage 1 outputs (CSVs per model/query/run)
    ├── query_eval/                 # Stage 2 outputs (scored CSVs, aggregations)
    └── temperatures/               # Temperature calibration reports
```

---

## Usage

### 1. Temperature calibration

Find the optimal temperature for each model before running the full benchmark.

```bash
python model_eval/temperature.py
```

Edit the `models` list and `TEMPERATURE_CANDIDATES` inside the script to configure the search. Reports are saved to `outputs/temperatures/`.

### 2. Model benchmark (Stage 1)

```bash
python model_eval/model_eval.py
```

Configure `models`, `queries`, `RUNS_PER_MODEL`, and `OLLAMA_SERVER` at the top of the file. Results are saved to `outputs/summary/<timestamp>/`.

> For long runs it is recommended to use `tmux` so the process survives disconnections:
> ```bash
> tmux new -s model_eval
> python3 -u model_eval/model_eval.py | ts '%Y-%m-%d %H:%M:%S' | tee model_eval.log
> # Detach with Ctrl+B, D
> ```

### 3. Query evaluation (Stage 2)

```bash
python -m query_eval.query_eval
```

Set `SUMMARY_RUN_DIR` to the Stage 1 output folder you want to evaluate, and configure `EVALUATOR_MODEL` and `OLLAMA_SERVER` at the top of the file. Results are saved to `outputs/query_eval/<timestamp>/`.

To run a quick test on a single query and model before the full run, set `TEST_MODE = True`.

---

## Key configuration

All runtime parameters are defined as constants at the top of each script — no CLI arguments or config files needed.

| Parameter | Where | Description |
|---|---|---|
| `OLLAMA_SERVER` | `model_eval.py`, `query_eval.py`, `temperature.py` | Ollama server URL |
| `RUNS_PER_MODEL` | `model_eval.py` | Repetitions per model per query |
| `SUMMARY_RUN_DIR` | `query_eval.py` | Stage 1 folder to evaluate |
| `EVALUATOR_MODEL` | `query_eval.py` | Model used as judge |
| `TEST_MODE` | `query_eval.py` | Limit run to one query/model for debugging |
