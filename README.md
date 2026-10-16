# TLNCSG

An experimental pipeline that tests how well local LLMs, served by [Ollama](https://ollama.com), translate natural-language questions into schema-independent intermediate representations (IRs) for graph queries.

The same questions are run through several IR grammars and models. The results are judged by an LLM, and then manually reviewed. The project also has an **Automatic Prompt Optimisation (APO)** loop, also known as automatic prompt engineering (APE), under `autoresearch/`.

## Datasets

- **GrailQA**: extract `datasets/GrailQA_v1.0.zip` into `datasets/GrailQA_v1.0/`. The configs use the combined train + dev set. Queries are deduplicated by canonical qid and sampled with stratification by function, node count and edge count.
- **Ambrosia**: questions with ambiguity of type *scope* and *attachment*. *Vague* questions are excluded because their ambiguity depends on database content. Sampling is stratified by ambiguity type and domain. Available from the [Ambrosia benchmark](https://ambrosia-benchmark.github.io/).

## Setup

Requirements: Python 3.14 and an Ollama server with the models you plan to use already pulled.

```bash
pip install -r requirements.txt
cp .env.example .env   # then set OLLAMA_HOST
```

The Ollama server address is set in a single place, the `OLLAMA_HOST` variable. It's read from the environment first, then from the untracked `.env` file at the project root. If neither is set, it defaults to `http://localhost:11434`.

## Pipeline

### 1. Execution

Samples queries from the configured dataset and sends each one to every enabled model × grammar combination, `runs_per_model` times.

```bash
python -m pipeline.execution.main --config execution_config.json
# resume an interrupted run
python -m pipeline.execution.main --config execution_config.json --resume-dir outputs/execution/<run>
```

Config: `execution_config.json` sets the dataset (type, path, `n_queries`, `seed`), the models with their per-grammar system prompts, the Ollama options and `runs_per_model`.

### 2. Grouping

Groups identical answers. Outputs are normalised (JSON is extracted, parsed and re-serialised with sorted keys) so equivalent answers collapse into the same group. An LLM-based grouper can be enabled as a fallback.

```bash
python -m pipeline.grouping.main --config grouping_config.json --execution-dir outputs/execution/<run>
```

Config: `grouping_config.json` sets the grouper model, `enable_llm_fallback` and `llm_fallback_max_group_size`.

### 3. Evaluation

An LLM judge compares each distinct answer against the ground truth, using the grammar and dataset-specific prompts in `prompts/evaluation/`.

```bash
python -m pipeline.evaluation.main --config evaluation_config.json --grouping-dir outputs/grouping/<run>
```

Config: `evaluation_config.json` sets the evaluator model and the dataset paths used to look up ground truths.

### 4. Review

A Streamlit app for human review of the judge's verdicts. Each page shows one query with its ground truth, followed by a card for every distinct answer from every model. The reviewer judges each answer and saves the whole query.

```bash
streamlit run pipeline/review/app.py
```

Config: `review_config.json` sets `evaluation_dir`, the evaluation run to review.

## Automatic Prompt Optimisation (autoresearch)

`autoresearch/` iteratively improves a model's system prompt:

1. **Generator**: runs the current prompt over the validation set (`runs_per_query` times per query).
2. **Evaluator**: an LLM judge scores each output against the SemGIR ground truths and explains every failure.
3. **Optimizer**: rewrites only the `## INSTRUCTIONS` section of the prompt from the failure logs. The grammar and examples are left untouched. It keeps a memory of recent unsuccessful edits so it doesn't repeat them.

When a candidate prompt beats the current champion, it's saved as a new champion version. The loop stops at `max_iterations` or once `target_score` is reached.

```bash
cd autoresearch
python main.py           # run / continue the loop
python main.py --reset   # archive the current run into autoresearch/archive/ and start over
```

Config: `autoresearch/config.json` sets the models and parameters for the optimizer, generator and evaluator, the prompt and ground-truth paths, and the loop settings.