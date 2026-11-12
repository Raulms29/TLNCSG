# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

An experimental pipeline that tests how well local LLMs (served by Ollama) translate natural-language questions into schema-independent intermediate representations for graph queries (SemGIR, SQUALL, GraphQ IR). `autoresearch/` is the APO loop that improves the SemGIR system prompt.

## Commands

There are no tests, linter or build step. Python 3.14 in `.venv/`; `OLLAMA_HOST` comes from the environment, then `.env`.

Run from the repo root (pipeline paths are relative to the working directory):

```bash
python -m pipeline.execution.main  --config execution_config.json [--resume-dir outputs/execution/<run>]
python -m pipeline.grouping.main   --config grouping_config.json   --execution-dir outputs/execution/<run>
python -m pipeline.evaluation.main --config evaluation_config.json --grouping-dir  outputs/grouping/<run>
python -m streamlit run pipeline/review/app.py     # reads review_config.json
python -m pipeline.metrics.main    --config metrics_config.json    --run-dir outputs/review/<run>
python -m autoresearch.main [--reset]
python autoresearch/tools/build_pool.py            # rebuilds ground_truths/autoresearch_pool.json
python autoresearch/tools/coverage.py
```

The Docker wrappers take the same arguments: `scripts/{windows,linux}/run_pipeline.{ps1,sh} <execution|grouping|evaluation|review|metrics> [args]` and `run_autoresearch.{ps1,sh} <run|reset>`. Build the image with `docker build -t virtualuser/tlncsg:latest .`.

## Pipeline

Each stage is a package under `pipeline/` (`config.py`, `main.py`, `runner.py`) with a JSON config at the root. It reads the previous stage's run directory and mirrors it; the run directory name is the join key between stages:

```
outputs/<stage>/<start>_<end>_<id>/<Grammar>/<model>/<QID>[-R]*.csv      # -R = thinking mode
```

- **Execution**: one CSV per query; an existing CSV means done (`--resume-dir`). A query with a failed run is not saved, so a resume retries it.
- **Grouping**: `grouping/normalizers.py` defines what "the answer" is (`extract_answer`, `normalize_output`) for grouping, the judge and the review alike. `output_key` (hash of grammar, QID and normalized output) identifies an answer across models and runs.
- **Evaluation**: `evaluation/judge.py` gives one verdict per group; autoresearch uses the same judge.
- **Review**: human verdicts live in one `outputs/review/review_state.json` keyed by `Output Key`, so they carry over between runs. The export writes the `_reviewed.csv` files that metrics reads.
- **Metrics**: computed from the human verdicts, weighted by `Group Size`.

Conventions that span files:

- Grammar names are free-form keys in `execution_config.json` and become directory names. They are matched by lower-cased substring (`pipeline/grammars.py`), so `SemGIR_APO` uses SemGIR's handling and prompts.
- Judge prompts are looked up as `prompts/evaluation/EVAL_<GRAMMAR>_<DATASET>.prompt.md`.
- The dataset is inferred from the QID prefix: `AMB_` Ambrosia, `T2C_` Text2Cypher, otherwise GrailQA.
- `evaluation/error_categories.py` must match the `ERROR CATEGORIES` section of every evaluation prompt.
- New datasets subclass `QueryDataset` and are registered in `DATASET_LOADERS` (`execution/main.py`).

## Autoresearch (APO)

- Only the `## INSTRUCTIONS` section of the prompt is rewritten (`services/assembler.py`); grammar, examples and rules stay fixed.
- The optimizer sees only failing *train* queries. A candidate becomes champion when fixed-minus-broken queries on *val* reach `min_net_gain`.
- State: `autoresearch/experiments.json`, `autoresearch/prompts/champion_*.prompt.md` and `autoresearch/archive/run_<timestamp>/`. Running again resumes; `--reset` archives first; creating `autoresearch/stop.txt` stops before the next iteration.
- `autoresearch/verdict_cache.json` keeps verdicts by query and normalized output across runs, and is edited by hand to fix wrong verdicts.

## Project rules

- **Code**: follow the conventions of the module you edit and good practice in general: PEP 8, type hints, clear names, small focused functions, no dead code or duplicated logic. In this repo that means a docstring on each module and public function, `logging.getLogger(__name__)` instead of `print` (outside the `autoresearch/tools/` scripts), pipeline configs as dataclasses loaded through `config_utils.known_fields`, and reusing the shared helpers (`OllamaClient`, `Judge`, `grouping/normalizers.py`, `grammars.py`) instead of reimplementing them.
- **Docs**: call it an "experimental pipeline", not a framework. Keep READMEs concise.
- **Results are data**: `outputs/` and `autoresearch/archive/` are tracked experiment results; don't delete or regenerate them. `review_state.json` and `verdict_cache.json` hold human judgements that cannot be regenerated.