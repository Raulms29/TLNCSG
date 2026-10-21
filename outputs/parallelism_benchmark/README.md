# Parallel requests benchmark (19/10/2026)

How much faster each workload of the project runs when 1, 2 or 4 requests are sent to Ollama at once.

## Setup

- **Server:** RTX 5090 (32 GB), Ollama 0.40.6 in Docker on WSL2, models stored on the WSL disk, `OLLAMA_NUM_PARALLEL=4`.
- **Workloads:** each scenario sends the same requests as the module it reproduces (same model, prompts and options: temperature 0, `num_predict` 3072, thinking off).

| Scenario | Model | num_ctx | Requests |
|---|---|---|---|
| autoresearch_generator | qwen3.8:27b | 16384 | BASE prompt over 40 SemGIR ground-truth queries |
| autoresearch_judge | gemma4:26b | 16384 | autoresearch evaluator over the generator's outputs |
| execution_qwen3.8 | qwen3.8:27b | 16384 | 40 GrailQA questions, the 4 grammar prompts in turn |
| execution_gemma4 | gemma4:26b | 16384 | same |
| execution_ministral | ministral-3:14b | 16384 | same |
| evaluation_judge | qwen3.8:27b | 16384 | EVAL_*_GRAILQA prompts over execution_qwen3.8's outputs |

- **Procedure:** each scenario loads its model once and fills every slot's prompt cache. It then runs the 40 requests 9 times: with 1, 2 and 4 at once, 3 repetitions each, in rotating order (1-2-4, 2-4-1, 4-1-2) so drift over time does not favour one setting. The server had no other load.
- **Totals:** 2,160 requests in one hour, all at 100% GPU. 1 runaway output (a request that reached the 3,072-token limit) and 1 client-side error.
- **Largest prompts:** 9,970 tokens (autoresearch judge) and 7,730 (execution with the APO prompt), so 16384 fits every workload with its output.

## Results

Median time to complete the 40 requests, with the speed-up over one request at a time:

| Scenario | 1 at a time | 2 at once | 4 at once |
|---|---|---|---|
| autoresearch_generator (qwen3.8) | 77.2 s | 74.5 s (1.04×) | 74.5 s (1.04×) |
| execution_qwen3.8 | 74.4 s | 71.9 s (1.03×) | 72.5 s (1.02×) |
| evaluation_judge (qwen3.8) | 84.8 s | 82.8 s (1.02×) | 82.4 s (1.03×) |
| autoresearch_judge (gemma4) | 50.0 s | 52.8 s (0.95×) | **35.7 s (1.40×)** |
| execution_gemma4 | 65.4 s | 62.1 s (1.05×) | **47.1 s (1.39×)** |
| execution_ministral | 73.0 s | 67.2 s (1.09×) | **34.2 s (2.13×)** |

Speed-ups are medians of requests per minute; `summary.csv` also has the ranges and the speed-up in output tokens per second.

## Findings

- **qwen3.8:27b does not gain.** Ollama forces the `qwen35` architecture family to a single slot, whatever `OLLAMA_NUM_PARALLEL` says. The server log shows `sched.go:558 "model architecture does not currently support parallel requests" architecture=qwen35` every time the model loads. The list is hardcoded in Ollama's `server/sched.go` ([ollama issue #18938](https://github.com/ollama/ollama/issues/18938); [PR #17144](https://github.com/ollama/ollama/pull/17144) proposes removing qwen35 from it).
- **gemma4:26b and ministral-3:14b only gain at 4.** At 2 the gain is within noise; at 4, gemma4 is about 1.4× and ministral about 2.1× faster.
- **execution_gemma4 at 4 overstates its gain.** Its answers were shorter in that setting (142.7 output tokens per request on average, against 159.0 one at a time), so the same requests took less work. In output tokens per second the gain is 1.13×; the real gain lies between 1.13× and 1.39×.
- **The time of each request rises with parallelism**, even when the total falls, because requests share the GPU or wait for the single slot. Mean time per request, measured by the client and including time waiting in the server's queue:

| Scenario | 1 at a time | 2 at once | 4 at once |
|---|---|---|---|
| execution_qwen3.8 | 1.84 s | 3.55 s | 7.00 s |
| execution_gemma4 | 1.53 s | 3.25 s | 4.53 s |
| execution_ministral | 1.82 s | 3.31 s | 3.62 s |

  This is why the pipeline's recorded `Inference Time (s)` is only comparable between runs made with the same `parallel_requests`.

## Settings chosen

| Setting | Value |
|---|---|
| Server `OLLAMA_NUM_PARALLEL` | 4 |
| `autoresearch/config.json` → `loop_settings.parallel_requests` | 4 (judge phase about 1.4× faster) |
| `execution_config.json` → `parallel_requests` | 4 (ministral about 2×, gemma4 1.1–1.4×) |
| `evaluation_config.json` → `parallel_requests` | 4 (no gain with the qwen3.8 judge; useful with another judge model) |
| `num_ctx` | 16384 for every workload, except the autoresearch optimizer (65536) |

## Files

- `summary.csv`: per scenario and concurrency, the median requests per minute and output tokens per second with their range, the speed-up, runaways, errors and GPU share.
- `measurements.csv`: one row per measurement (54 rows).
