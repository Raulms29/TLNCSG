import csv
import json
import logging
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Dict, Any, Tuple, Iterable, Callable, Iterator
from autoresearch.core.query import Query
from autoresearch.services.services_utils import _extract_json_text
from autoresearch.services.generator import GeneratorClient
from autoresearch.services.evaluator import EvaluatorAgent
from autoresearch.core.constants import AUTORESEARCH_DIR
from pipeline.grouping.normalizers import normalize_json_output

logger = logging.getLogger(__name__)


class ValidationAborted(Exception):
    """Raised when Ollama could not be reached, so the validation results would not be valid."""


class ValidationRunner:
    """
    Orchestrates query generations and evaluations over the full validation dataset.
    Each query is run runs_per_query times; a query passes when the share of correct
    runs reaches pass_threshold.
    """

    def __init__(
        self,
        ground_truths_path: str,
        generator: GeneratorClient,
        evaluator: EvaluatorAgent,
        runs_per_query: int = 1,
        pass_threshold: float = 0.8,
        parallel_requests: int = 1,
    ):
        self.ground_truths_path = Path(ground_truths_path)
        self.generator = generator
        self.evaluator = evaluator
        self.runs_per_query = max(1, runs_per_query)
        self.pass_threshold = pass_threshold
        self.parallel_requests = max(1, parallel_requests)
        self.queries = self._load_queries()

    def _load_queries(self) -> List[Query]:
        """Loads validation queries from the ground truths file."""
        if not self.ground_truths_path.exists():
            raise FileNotFoundError(
                f"Ground truths file not found at '{self.ground_truths_path}'"
            )

        with open(self.ground_truths_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        queries = []
        for q_id, q_data in data.items():
            query_text = q_data.get("query", "").strip()
            if query_text:
                queries.append(
                    Query(q_id, query_text, q_data.get("solution", ""), q_data.get("rubric_features", []))
                )
        return queries

    def run_validation(
        self, system_prompt: str, iteration: int = 1, run_timestamp_str: str = ""
    ) -> Tuple[float, Dict[str, Dict[str, Any]], str]:
        """
        Executes the generator and evaluator on all queries.
        Raises ValidationAborted if a generation or judge request could not reach Ollama.
        Returns:
            mean_rate: The average share of correct runs across the validation set.
            results: Per-query summary keyed by query ID (rate, passed, error category, rationale).
            log_file: Path to the validation results CSV file.
        """
        total_queries = len(self.queries)
        logger.info(
            "Starting validation run of iteration #%d on %d queries x%d runs...",
            iteration, total_queries, self.runs_per_query,
        )

        # Generation and evaluation run in separate phases so each model stays loaded
        logger.info("--- PHASE 1: GENERATION ---")
        jobs = [query for query in self.queries for _ in range(self.runs_per_query)]
        generations = {query.id: [] for query in self.queries}
        for idx, (query, gen) in enumerate(zip(jobs, self._run_parallel(lambda q: self._generate(system_prompt, q), jobs)), 1):
            generations[query.id].append(gen)
            if len(generations[query.id]) == self.runs_per_query:
                done = str(idx // self.runs_per_query).zfill(len(str(total_queries)))
                logger.info("  [%s/%d] Generated Query %s", done, total_queries, query.id)

        # A run that could not reach Ollama is not a parser mistake: stop instead of counting it as incorrect
        errors = [gen["error"] for runs in generations.values() for gen in runs if gen["error"]]
        if errors:
            raise ValidationAborted(f"{len(errors)} generations failed (first error: {errors[0]})")

        logger.info("--- PHASE 2: EVALUATION ---")
        # Runs with the same normalized output are judged once, as in the pipeline's grouping
        distinct = {}
        for query in self.queries:
            for gen in generations[query.id]:
                distinct.setdefault((query.id, normalize_json_output(gen["candidate_raw"])), (query, gen))
        logger.info("  Judging %d distinct outputs of %d runs...", len(distinct), len(jobs))

        # Verdicts arrive in query order: each query is summarized and logged as soon as its outputs are judged
        pending = Counter(qid for qid, _ in distinct)
        verdicts = {}
        runs_by_query = {}
        results = {}
        try:
            for key, verdict in zip(distinct, self._run_parallel(lambda job: self._evaluate(*job), list(distinct.values()))):
                verdicts[key] = verdict
                qid = key[0]
                pending[qid] -= 1
                if pending[qid] == 0:
                    runs_by_query[qid] = [
                        {**gen, **verdicts[(qid, normalize_json_output(gen["candidate_raw"]))]} for gen in generations[qid]
                    ]
                    results[qid] = self._summarize(runs_by_query[qid])
                    self._log_query(len(results), total_queries, qid, runs_by_query[qid])
        except RuntimeError as e:
            raise ValidationAborted(str(e)) from e

        log_file = self._save_csv(runs_by_query, results, iteration, run_timestamp_str)
        mean_rate = sum(r["rate"] for r in results.values()) / len(results) if results else 0.0
        passed = sum(r["passed"] for r in results.values())
        logger.info(
            "Validation run completed: %d/%d queries pass | mean correct rate %.4f", passed, total_queries, mean_rate
        )
        return mean_rate, results, log_file

    def _log_query(self, idx: int, total: int, qid: str, runs: List[Dict[str, Any]]) -> None:
        """Logs a query's correct runs and one mark per distinct output with its size, e.g. "08/10 | ✓ 08  ✗ 02".
        Numbers are zero-padded to the width of their total so the columns line up."""
        width = len(str(len(runs)))
        groups = Counter((normalize_json_output(run["candidate_raw"]), run["correct"]) for run in runs)
        marks = "  ".join(f"{'✓' if correct else '✗'} {size:0{width}d}" for (_, correct), size in groups.items())
        correct = sum(run["correct"] for run in runs)
        logger.info(
            "  [%s/%d] %s — %s/%d | %s",
            str(idx).zfill(len(str(total))), total, qid, str(correct).zfill(width), len(runs), marks,
        )

    def merge_results(
        self, first: Dict[str, Dict[str, Any]], second: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """Combines two evaluations of the same prompt into one with twice the runs per query."""
        merged = {}
        for qid in first:
            rate = (first[qid]["rate"] + second[qid]["rate"]) / 2
            # Keep the error category and rationale of an evaluation where the query had wrong runs
            failing = [result for result in (second[qid], first[qid]) if result["error_category"]]
            merged[qid] = {**(failing[0] if failing else second[qid]), "rate": rate, "passed": rate >= self.pass_threshold}
        return merged

    def build_failures(self, results: Dict[str, Dict[str, Any]], excluded_ids: Iterable[str] = ()) -> List[Dict[str, Any]]:
        """Lists the failing queries the optimizer may see, skipping the excluded (hidden) ones."""
        excluded = set(excluded_ids)
        return [
            {
                "id": query.id,
                "features": query.features,
                "rubric_features": query.rubric_features,
                "rate": results[query.id]["rate"],
                "error_category": results[query.id]["error_category"],
                "rationale": results[query.id]["rationale"],
            }
            for query in self.queries
            if not results[query.id]["passed"] and query.id not in excluded
        ]

    def _run_parallel(self, fn: Callable, jobs: List) -> Iterator:
        """Runs fn over jobs with parallel_requests concurrent Ollama calls, yielding results in job order."""
        with ThreadPoolExecutor(self.parallel_requests) as pool:
            yield from pool.map(fn, jobs)

    def _generate(self, system_prompt: str, query: Query) -> Dict[str, Any]:
        try:
            candidate_raw = self.generator.generate_translation(system_prompt, query.text)
            return {"candidate_raw": candidate_raw, "candidate_json": _extract_json_text(candidate_raw), "error": None}
        except Exception as e:
            return {"candidate_raw": None, "candidate_json": None, "error": str(e)}

    def _evaluate(self, query: Query, gen: Dict[str, Any]) -> Dict[str, Any]:
        """Judges one output and returns the verdict fields."""
        gt = query.solution
        gt_str = json.dumps(gt, indent=2) if isinstance(gt, (dict, list)) else str(gt)
        correct, category, rationale = self.evaluator.evaluate(query.text, gt_str, gen["candidate_json"])
        return {"correct": correct, "error_category": category, "rationale": rationale}

    def _summarize(self, runs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregates the runs of one query; the reported error is the most frequent one."""
        rate = sum(run["correct"] for run in runs) / len(runs)
        wrong = [run for run in runs if not run["correct"]]
        category = Counter(run["error_category"] for run in wrong).most_common(1)[0][0] if wrong else None
        rationale = next((run["rationale"] for run in wrong if run["error_category"] == category), "")
        return {
            "rate": rate,
            "passed": rate >= self.pass_threshold,
            "error_category": category,
            "rationale": rationale,
            "distinct_outputs": len({normalize_json_output(run["candidate_raw"]) for run in runs}),
        }

    def _save_csv(self, runs_by_query, results, iteration: int, run_timestamp_str: str) -> str:
        if not run_timestamp_str:
            run_timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        outputs_dir = AUTORESEARCH_DIR / "archive" / f"run_{run_timestamp_str}" / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        log_file = outputs_dir / f"validation_results_iter{iteration}_{time.strftime('%Y%m%d_%H%M%S')}.csv"

        try:
            with open(log_file, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Query ID", "Query Text", "Run Number", "Candidate Raw", "Candidate JSON",
                    "Correct", "Error Category", "Rationale", "Query Rate", "Distinct Outputs",
                ])
                for query in self.queries:
                    summary = results[query.id]
                    for i, run in enumerate(runs_by_query[query.id], 1):
                        writer.writerow([
                            query.id, query.text, i, run["candidate_raw"] or "",
                            json.dumps(run["candidate_json"]) if run["candidate_json"] is not None else "",
                            run["correct"], run["error_category"] or "", run["rationale"],
                            summary["rate"], summary["distinct_outputs"],
                        ])
            logger.info("Saved validation results to %s", log_file)
        except Exception as e:
            logger.error("Failed to save validation results: %s", e)
        return str(log_file)
