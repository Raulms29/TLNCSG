# Autoresearch for Prompt Optimization (SemGIR) - Implementation Plan

This document outlines the software architecture, modular directories, execution flows, and key prompt design guidelines for the autonomous prompt optimizer.

---

## 1. Folder Structure & Modular Architecture

To ensure high maintainability, testability, and clean separation of concerns, the system is designed around a modular, object-oriented service architecture:

```
autoresearch/
├── config.json                     # System configurations (models, server, paths)
├── main.py                         # Clean entry point; orchestrates loop & signal handling
├── core/                           # Data models & value objects
│   ├── __init__.py
│   ├── query.py                    # Encapsulates a validation query (ID, expected IR, tags)
│   └── experiment.py               # Holds state of a single iteration (metrics, prompts)
├── services/                       # Business logic services
│   ├── __init__.py
│   ├── assembler.py                # Handles prompt reading, slicing, and dynamic reassembly
│   ├── generator.py                # Wrapper for executing the target generator model
│   ├── evaluator.py                # LLM-as-a-Judge API (scores a candidate against ground truth)
│   ├── optimizer.py                # Proposes refinements based on fails & historical memory
│   └── runner.py                   # Orchestrates the execution of the full ~45 validation suite
└── storage/                        # Persistence & I/O
    ├── __init__.py
    ├── prompt_store.py             # Manages versioning (champion_v1, champion_latest) in prompts/
    └── experiment_logger.py        # Appends and reads execution history (experiments.json)
```

---

## 2. Refined Design & Execution Flow

### A. Preventing Overfitting to Specific Test Data
To ensure the optimizer refines the prompt's logical grammar rules rather than hardcoding rules for specific test strings:
* **Information Masking**: The natural language text of the queries and the expected JSON solutions will be **omitted** from the inputs sent to the optimizer.
* **Input to Optimizer**: The optimizer will only receive:
  1. The current active **Champion Instructions**.
  2. The **Query ID** (e.g. `Query Q04`) to group issues.
  3. **Logical Feature Tags**: Structural features involved in the query (e.g. `["paths", "constraints", "aggregations"]`), which describes the SemGIR constructs tested by the query without revealing the natural language text.
  4. The **Evaluator Rationale** (which conceptualizes the error, e.g. *"The candidate generated a direct relationship instead of using the PATH block required for multi-hop traversals"*).
  5. The **Failure Memory Queue** (summaries of recent rejected instruction modifications).

This ensures the optimizer acts purely on abstract, structural failure descriptions rather than concrete test data.

#### How Logical Feature Tags are Obtained:
The tags are extracted **programmatically** in Python by analyzing the keys present in the expected Ground Truth JSON at startup:
* If the ground truth JSON contains the key `"paths"`, add `"paths"`.
* If it contains `"list"` or `"aggregate_kind"`, add `"aggregations"`.
* If it contains `"quantifier_kind"`, add `"quantifiers"`.
* If it contains `"order_by"`, `"limit"`, or `"skip"`, add `"modifiers"`.
* If it contains multiple criteria under `"and_conditions"` or `"or_conditions"`, add `"complex_constraints"`.

### B. Linux-Native Graceful Stopping
Since the system runs on a Linux VM:
* **Signal Handlers (`signal` module)**: `main.py` will register handlers for standard UNIX signals: `SIGINT` (Ctrl+C) and `SIGTERM`.
* **Graceful Toggle**: When a signal is captured, the handler sets a global flag `graceful_stop = True`.
* **Flow**: The main loop checks this flag at the start of each iteration. If active, it logs the current status, saves all versioned prompts, and exits cleanly.
* **Forced Termination**: If the user presses `Ctrl+C` a second time while the iteration is finishing, the handler forces an immediate termination (`sys.exit(1)`).

---

## 3. Prompt Design Guidelines

Instead of using literal, rigid prompts, the system should follow these design principles and input/output structures for the agents:

### A. The Evaluator Agent (LLM-as-a-Judge)
The evaluator's primary job is to provide objective, structural grading.

* **Inputs Received**:
  1. Natural language query text.
  2. Ground Truth JSON.
  3. Generated Candidate JSON.
* **Design Guidelines**:
  * **Explicit Grading Dimensions**: Prompt the judge to evaluate along specific axes: syntax correctness, relation role conventions (lowercase, snake_case), and path correctness.
  * **Tolerance to Synonyms**: Instruct the judge that naming differences (e.g. different entity IDs like `e_1` vs `e_server`) and condition orderings are acceptable if the underlying SemGIR representation is logically equivalent.
  * **Structured JSON Output**: The output must be strictly formatted as a JSON object containing a float `score` and a detailed conceptual `rationale`. This ensures the script can easily parse it.

---

### B. The Optimizer Agent (Prompt Refiner)
The optimizer is a meta-agent that identifies ambiguities and corrects them.

* **Inputs Received**:
  1. The active `## INSTRUCTIONS` text block.
  2. Mapped failures list containing `[Query ID, Structural Feature Tags, Evaluator Rationale]`.
  3. Memory of recent rejected instruction changes.
* **Design Guidelines**:
  * **Keep Modifications Targeted**: Instruct the model to make surgical, small edits to existing instructions instead of rewriting the entire block.
  * **Generalize Rules**: Instruct the model that rules must describe grammatical logic (e.g. *"When encountering indirect connections, utilize paths..."*) and never mention query-specific terms.
  * **Markdown Strictness**: The output must return only the updated `## INSTRUCTIONS` block, formatted as clean markdown, making it easy to merge.

---

## 4. Separation of Concerns & Class Responsibilities

| Class / Service | Responsibility | Why it makes the code maintainable |
|---|---|---|
| **`PromptAssembler`** | Splices the baseline markdown file and merges the optimized instructions into a full prompt. | If you change the markdown structure or add sections in the future, you only edit this class. |
| **`ValidationRunner`** | Orchestrates query generations and evaluations. Computes the average metrics. | Keeps the main loop focused on optimization logic. Easily swap sequential execution for parallel execution later. |
| **`EvaluatorAgent`** | Handles connection to Ollama and parses JSON evaluation metrics. | If you swap the evaluator model (e.g., from local Ollama to a hosted API), you only change this module. |
| **`PromptStore`** | Writes versioned markdown files and maintains references. | Decouples filesystem naming structures from the optimizer loop logic. |
| **`ExperimentLogger`** | Manages reading and writing `experiments.json`. | Allows changing the logging format (e.g. to SQLite or WandB) in the future without changing the loop. |

---

## 5. Configuration File Structure (`autoresearch/config.json`)
```json
{
  "ollama_server": "http://156.35.95.33:11434",
  "optimizer": {
    "model": "gemma4:26b",
    "temperature": 0.2,
    "num_ctx": 16384,
    "num_predict": 3072,
    "failure_memory_size": 3
  },
  "generator": {
    "model": "gemma4:26b",
    "temperature": 0.0,
    "num_ctx": 8192,
    "num_predict": 3072,
    "runs_per_query": 1
  },
  "evaluator": {
    "model": "gemma4:26b",
    "temperature": 0.0,
    "num_ctx": 12288,
    "num_predict": 2048
  },
  "paths": {
    "baseline_prompt": "prompts/SYSTEM_PROMPT_LISTS.prompt.md",
    "ground_truths": "ground_truths/ground_truth_sem_gir.json",
    "prompts_dir": "autoresearch/prompts"
  },
  "loop_settings": {
    "max_iterations": -1,
    "target_score": 1.0
  }
}
```
