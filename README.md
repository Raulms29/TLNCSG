# TLNCSG

An experimental pipeline that tests how well local LLMs, served by [Ollama](https://ollama.com), translate natural-language questions into schema-independent intermediate representations (IRs) for graph queries.

The same questions are run through several IR grammars and models, judged by an LLM and then reviewed by hand. `autoresearch/` holds an **Automatic Prompt Optimisation (APO)** loop that improves a system prompt.

## Datasets

- **GrailQA**: extract `datasets/GrailQA_v1.0.zip` into `datasets/GrailQA_v1.0/`. The configs use the combined train + dev set, deduplicated by canonical qid and sampled by function, node count and edge count.
- **Ambrosia**: *scope* and *attachment* ambiguities (*vague* questions are excluded), sampled by ambiguity type and domain. Available from the [Ambrosia benchmark](https://ambrosia-benchmark.github.io/).

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

1. An optimizer model rewrites the prompt's `## INSTRUCTIONS` from the failing queries.
2. The new prompt is run over the SemGIR ground truths and an LLM judge marks each output.
3. It replaces the current prompt only if it fixes clearly more queries than it breaks, confirmed by a second evaluation.

- Settings: `autoresearch_config.json`
- Results: `autoresearch/archive/run_<timestamp>/`
- Ground-truth coverage: `python autoresearch/tools/coverage.py`
