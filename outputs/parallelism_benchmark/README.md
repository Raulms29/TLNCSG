# Parallel requests benchmark

How much faster each workload runs with 1, 2 or 4 requests sent to Ollama at once, and how parallelism affects the outputs.

## Setup

- **Server:** RTX 5090 (32 GB), Ollama 0.40.6, `OLLAMA_NUM_PARALLEL=4`, no other load.
- **Workloads:** the same requests as each module (temperature 0, `num_predict` 3072, `num_ctx` 16384, thinking off).

| Scenario | Model | Requests |
|---|---|---|
| autoresearch_generator | qwen3.8:27b | BASE prompt over 40 SemGIR ground-truth queries |
| autoresearch_judge | gemma4:26b | autoresearch evaluator over the generator's outputs |
| execution_qwen3.8 / gemma4 / ministral | qwen3.8:27b, gemma4:26b, ministral-3:14b | 40 GrailQA questions, the 4 grammar prompts in turn |
| evaluation_judge | qwen3.8:27b | EVAL_*_GRAILQA prompts over execution_qwen3.8's outputs |

- **Procedure:** the 40 requests run with 1, 2 and 4 at once, 3 repetitions each, in rotating order.

## Results

Median time for the 40 requests (speed-up over 1 at a time):

| Scenario | 1 at a time | 2 at once | 4 at once |
|---|---|---|---|
| autoresearch_generator (qwen3.8) | 77.2 s | 74.5 s (1.04×) | 74.5 s (1.04×) |
| execution_qwen3.8 | 74.4 s | 71.9 s (1.03×) | 72.5 s (1.02×) |
| evaluation_judge (qwen3.8) | 84.8 s | 82.8 s (1.02×) | 82.4 s (1.03×) |
| autoresearch_judge (gemma4) | 50.0 s | 52.8 s (0.95×) | **35.7 s (1.40×)** |
| execution_gemma4 | 65.4 s | 62.1 s (1.05×) | **47.1 s (1.39×)** |
| execution_ministral | 73.0 s | 67.2 s (1.09×) | **34.2 s (2.13×)** |

## Findings

- **qwen3.8 does not gain:** Ollama forces the `qwen35` architecture to a single slot ([ollama issue #18938](https://github.com/ollama/ollama/issues/18938)).
- **gemma4 and ministral only gain at 4** (about 1.4× and 2.1×).
- **Time per request rises with parallelism** (e.g. execution_qwen3.8: 1.84 s → 7.00 s at 4), so `Inference Time (s)` is only comparable between runs with the same `parallel_requests`.
- **Parallelism makes results inconsistent.** Batched requests change the GPU's floating-point rounding, which at temperature 0 can flip a near-tied token ([Thinking Machines](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/)). Test with ministral-3:14b (10 GrailQA queries, 8 runs per setting), queries with more than one distinct output:

| Prompt | 1 at a time | 4 at once |
|---|---|---|
| GraphQ_IR | 0/10 | 3/10 |
| SemGIR | 0/10 | 7/10 |

## Settings chosen

Runs are sequential, for reproducibility: `parallel_requests` is 1 in `autoresearch_config.json`, `execution_config.json` and `evaluation_config.json`.

## Files

- `summary.csv`: per scenario and concurrency, median requests per minute and output tokens per second with ranges, speed-ups, runaways, errors and GPU share.
- `measurements.csv`: one row per measurement (54 rows).