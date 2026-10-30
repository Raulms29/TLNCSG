# TLNCSG

An experimental pipeline that tests how well local LLMs, served by [Ollama](https://ollama.com), translate natural-language questions into schema-independent intermediate representations (IRs) for graph queries.

The same questions are run through several IR grammars and models, judged by an LLM and then reviewed by hand. `autoresearch/` holds an **Automatic Prompt Optimisation (APO)** loop that improves a system prompt.

## Datasets

- **GrailQA**: extract `datasets/GrailQA_v1.0.zip` into `datasets/GrailQA_v1.0/`. The pipeline samples dev; autoresearch samples train, without the templates that occur in dev. Questions are deduplicated by canonical qid and sampled by function, node count and edge count.
- **Text2Cypher**: Neo4j's [text2cypher-2025v1](https://huggingface.co/datasets/neo4j/text2cypher-2025v1), `train.parquet` and `test.parquet` in `datasets/text2cypher_2025v1/`. The pipeline samples test; autoresearch samples train, without the questions that occur in test. Write queries and a few unusable sources are excluded, questions are deduplicated, and the sample is stratified by `data_source`.

## Setup

Requirements: Python 3.14 and an Ollama server with the models already pulled.

```bash
pip install -r requirements.txt
cp .env.example .env   # then set OLLAMA_HOST
```

`OLLAMA_HOST` is read from the environment, then from `.env`, and defaults to `http://localhost:11434`.

## Running

Every module is launched through the Docker scripts in `scripts/linux/` or `scripts/windows/`; each script's header lists its commands and arguments.

```bash
./scripts/linux/run_pipeline.sh <execution|grouping|evaluation|review|metrics> [args]
./scripts/linux/run_autoresearch.sh <run|reset>
```

```powershell
.\scripts\windows\run_pipeline.ps1 <execution|grouping|evaluation|review|metrics> [args]
.\scripts\windows\run_autoresearch.ps1 <run|reset>
```

## Pipeline

Each module has a JSON config at the project root.

1. **Execution** (`execution_config.json`): sends each sampled query to every enabled model × grammar, `runs_per_model` times. Interrupted runs can be resumed with `--resume-dir`.
2. **Grouping** (`grouping_config.json`): groups identical answers after normalising them (JSON extracted and re-serialised with sorted keys). An LLM grouper can be enabled as a fallback.
3. **Evaluation** (`evaluation_config.json`): an LLM judge compares each distinct answer with the ground truth, using the prompts in `prompts/evaluation/`.
4. **Review** (`review_config.json`): a Streamlit app for human review of the judge's verdicts.
5. **Metrics** (`metrics_config.json`): aggregates the reviewed results.

`parallel_requests` in the execution and evaluation configs sends several requests at once (the server needs `OLLAMA_NUM_PARALLEL` at least as high).

> **Note:** with `parallel_requests` > 1 the recorded `Inference Time (s)` per request is higher, so only compare runs made with the same value; each run's `manifest.json` records it.

## Automatic Prompt Optimisation (autoresearch)

Each iteration:

1. An optimizer model rewrites the prompt's `## INSTRUCTIONS` from the failing **train** queries.
2. The new prompt is run over every query of the pool, train and val, and an LLM judge marks each output.
3. It replaces the current prompt only if, on the **val** queries, it fixes at least `min_net_gain` more queries than it breaks. The optimizer never sees the val queries.

The pool (`ground_truths/autoresearch_pool.json`) holds the hand-written SemGIR ground truths and samples of the GrailQA and Text2Cypher training splits, each source split into train and val. Its sources and the val fraction are set in `pool` in `autoresearch_config.json`; build it with `python autoresearch/tools/build_pool.py`.

- Settings: `autoresearch_config.json`
- Results: `autoresearch/archive/run_<timestamp>/`
- Ground-truth coverage: `python autoresearch/tools/coverage.py`