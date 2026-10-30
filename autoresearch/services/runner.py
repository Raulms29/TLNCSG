import csv
import hashlib
import json
import logging
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Dict, Any, Tuple, Callable, Iterator, Optional
from autoresearch.core.query import Query
from autoresearch.services.generator import GeneratorClient
from autoresearch.core.constants import AUTORESEARCH_DIR
from pipeline.evaluation.ground_truth import GroundTruth
from pipeline.evaluation.judge import Judge
from pipeline.grouping.normalizers import extract_answer, normalize_json_output

logger = logging.getLogger(__name__)


class ValidationAborted(Exception):
    """Raised when Ollama could not be reached, so the validation results would not be valid."""


class ValidationRunner:
    """
    Orchestrates query generations and evaluations over every query of the pool, train and val.
    Each query is run runs_per_query times; a query passes when the share of correct
    runs reaches pass_threshold. An output judged before keeps its verdict, so an unchanged output
    cannot flip; the verdicts are kept in verdict_cache_path, if given, shared by every run.
    """

    def __init__(
        self,
        pool_path: str,
        generator: GeneratorClient,
        judge: Judge,
        judge_prompts: Dict[str, str],
        runs_per_query: int = 1,
        pass_threshold: float = 0.8,
        parallel_requests: int = 1,
        verdict_cache_path: Optional[str] = None,
    ):
        self.pool_path = Path(pool_path)
        self.generator = generator
        self.judge = judge
        self.judge_prompts = judge_prompts  # judge system prompt by source
        self.runs_per_query = max(1, runs_per_query)
        self.pass_threshold = pass_threshold
        self.parallel_requests = max(1, parallel_requests)
        self.queries = self._load_queries()
        self.ground_truth_hashes = {
            query.id: self._ground_truth_hash(query) for query in self.queries
        }
        self.cache_path = Path(verdict_cache_path) if verdict_cache_path else None
        self.other_verdicts: Dict[str, Any] = (
            {}
        )  # cache entries of queries outside this run
        self.verdicts = self._load_verdict_cache()

    def _load_queries(self) -> List[Query]:
        """Loads the queries of the pool file (built by autoresearch/tools/build_pool.py)."""
        if not self.pool_path.exists():
            raise FileNotFoundError(
                f"Pool file not found at '{self.pool_path}': build it with autoresearch/tools/build_pool.py"
            )

        with open(self.pool_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        queries = []
        for q_id, q_data in data.items():
            solution = q_data.get("solution")
            if solution is not None:
                ground_truth = GroundTruth(
                    dataset="semgir", semgir_json=json.dumps(solution, indent=2)
                )
            else:
                ground_truth = GroundTruth(**q_data["ground_truth"])
            queries.append(
                Query(
                    q_id,
                    q_data["query"].strip(),
                    q_data["source"],
                    q_data["split"],
                    ground_truth,
                    solution=solution,
                    features=q_data.get("features"),
                    rubric_features=q_data.get("rubric_features"),
                )
            )
        return queries

    @staticmethod
    def _ground_truth_hash(query: Query) -> str:
        # Hand-written queries hash the solution, as cache entries made before the pool did
        if query.solution is not None:
            text = json.dumps(query.solution, sort_keys=True, ensure_ascii=False)
        else:
            text = query.ground_truth.judge_sections()
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]

    def _load_verdict_cache(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Verdicts by query ID and normalized output. The verdicts of a query whose ground truth changed
        since they were given are dropped. The file can be edited to fix a wrong verdict.
        Entries of queries outside this run are kept as they are and written back on save.
        """
        if not self.cache_path or not self.cache_path.exists():
            return {}
        data = json.loads(self.cache_path.read_text(encoding="utf-8"))
        self.other_verdicts = {
            qid: item
            for qid, item in data.items()
            if qid not in self.ground_truth_hashes
        }
        return {
            qid: {entry.pop("output"): entry for entry in item["verdicts"]}
            for qid, item in data.items()
            if item["ground_truth"] == self.ground_truth_hashes.get(qid)
        }

    def _save_verdict_cache(self) -> None:
        if not self.cache_path:
            return
        data = {
            qid: {
                "ground_truth": self.ground_truth_hashes[qid],
                "verdicts": [
                    {"output": output, **verdict} for output, verdict in outputs.items()
                ],
            }
            for qid, outputs in self.verdicts.items()
        }
        data = dict(sorted({**self.other_verdicts, **data}.items()))
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def run_validation(
        self, system_prompt: str, iteration: int = 1, run_timestamp_str: str = ""
    ) -> Tuple[Dict[str, Dict[str, Any]], str]:
        """
        Executes the generator and evaluator on all queries.
        Raises ValidationAborted if a generation or judge request could not reach Ollama.
        Returns:
            results: Per-query summary keyed by query ID (rate, passed, error category, rationale).
            log_file: Path to the validation results CSV file.
        """
        total_queries = len(self.queries)
        logger.info(
            "Starting validation run of iteration #%d on %d queries x%d runs...",
            iteration,
            total_queries,
            self.runs_per_query,
        )

        # Generation and evaluation run in separate phases so each model stays loaded
        logger.info("--- PHASE 1: GENERATION ---")
        jobs = [query for query in self.queries for _ in range(self.runs_per_query)]
        generations = {query.id: [] for query in self.queries}
        for idx, (query, gen) in enumerate(
            zip(
                jobs,
                self._run_parallel(lambda q: self._generate(system_prompt, q), jobs),
            ),
            1,
        ):
            generations[query.id].append(gen)
            if len(generations[query.id]) == self.runs_per_query:
                done = str(idx // self.runs_per_query).zfill(len(str(total_queries)))
                logger.info(
                    "  [%s/%d] Generated Query %s", done, total_queries, query.id
                )

        # A run that could not reach Ollama is not a parser mistake: stop instead of counting it as incorrect
        errors = [
            gen["error"]
            for runs in generations.values()
            for gen in runs
            if gen["error"]
        ]
        if errors:
            raise ValidationAborted(
                f"{len(errors)} generations failed (first error: {errors[0]})"
            )

        logger.info("--- PHASE 2: EVALUATION ---")
        # Runs with the same normalized output are judged once, as in the pipeline's grouping
        distinct = {}
        for query in self.queries:
            for gen in generations[query.id]:
                distinct.setdefault((query.id, gen["output"]), (query, gen))
        todo = {
            key: job
            for key, job in distinct.items()
            if key[1] not in self.verdicts.get(key[0], {})
        }
        logger.info(
            "  Judging %d new distinct outputs of %d runs (%d already in the verdict cache)...",
            len(todo),
            len(jobs),
            len(distinct) - len(todo),
        )

        # Queries are summarized and logged in order, as soon as every output of the query has a verdict
        pending = Counter(qid for qid, _ in todo)
        queue = list(self.queries)
        runs_by_query = {}
        results = {}

        def summarize_ready() -> None:
            while queue and pending[queue[0].id] == 0:
                qid = queue.pop(0).id
                runs_by_query[qid] = [
                    {**gen, **self.verdicts[qid][gen["output"]]}
                    for gen in generations[qid]
                ]
                results[qid] = self._summarize(runs_by_query[qid])
                self._log_query(len(results), total_queries, qid, runs_by_query[qid])

        try:
            summarize_ready()
            for (qid, output), verdict in zip(
                todo,
                self._run_parallel(
                    lambda job: self._evaluate(*job), list(todo.values())
                ),
            ):
                self.verdicts.setdefault(qid, {})[output] = verdict
                pending[qid] -= 1
                summarize_ready()
        except RuntimeError as e:
            raise ValidationAborted(str(e)) from e
        finally:
            # A judge failure is not a verdict on the output: forget it, so the next evaluation judges it again
            for outputs in self.verdicts.values():
                for output in [
                    output
                    for output, verdict in outputs.items()
                    if verdict.get("judge_failed")
                ]:
                    del outputs[output]
            self._save_verdict_cache()

        log_file = self._save_csv(runs_by_query, results, iteration, run_timestamp_str)
        mean_rate = (
            sum(r["rate"] for r in results.values()) / len(results) if results else 0.0
        )
        passed = sum(r["passed"] for r in results.values())
        logger.info(
            "Validation run completed: %d/%d queries pass | mean correct rate %.4f",
            passed,
            total_queries,
            mean_rate,
        )
        return results, log_file

    def _log_query(
        self, idx: int, total: int, qid: str, runs: List[Dict[str, Any]]
    ) -> None:
        """Logs a query's correct runs and one mark per distinct output with its size, e.g. "08/10 | ✓ 08  ✗ 02".
        Numbers are zero-padded to the width of their total so the columns line up."""
        width = len(str(len(runs)))
        groups = Counter((run["output"], run["correct"]) for run in runs)
        marks = "  ".join(
            f"{'✓' if correct else '✗'} {size:0{width}d}"
            for (_, correct), size in groups.items()
        )
        correct = sum(run["correct"] for run in runs)
        logger.info(
            "  [%s/%d] %s — %s/%d | %s",
            str(idx).zfill(len(str(total))),
            total,
            qid,
            str(correct).zfill(width),
            len(runs),
            marks,
        )

    def build_failures(
        self, results: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Lists the failing train queries, the only ones the optimizer sees."""
        return [
            {
                "id": query.id,
                "source": query.source,
                "features": query.features,
                "rubric_features": query.rubric_features,
                "rate": results[query.id]["rate"],
                "error_category": results[query.id]["error_category"],
                "rationale": results[query.id]["rationale"],
            }
            for query in self.queries
            if query.split == "train"
            and not results[query.id]["passed"]
            and not results[query.id].get("judge_failed")
        ]

    def _run_parallel(self, fn: Callable, jobs: List) -> Iterator:
        """Runs fn over jobs with parallel_requests concurrent Ollama calls, yielding results in job order."""
        with ThreadPoolExecutor(self.parallel_requests) as pool:
            yield from pool.map(fn, jobs)

    def _generate(self, system_prompt: str, query: Query) -> Dict[str, Any]:
        """One generation. The candidate is the answer extracted as in the pipeline's grouping:
        the judge sees it and the verdict cache is keyed by it."""
        try:
            candidate_raw = self.generator.generate_translation(
                system_prompt, query.text
            )
            candidate = extract_answer(candidate_raw, "SemGIR")
            return {
                "candidate_raw": candidate_raw,
                "candidate": candidate,
                "output": normalize_json_output(candidate),
                "error": None,
            }
        except Exception as e:
            return {
                "candidate_raw": None,
                "candidate": None,
                "output": None,
                "error": str(e),
            }

    def _evaluate(self, query: Query, gen: Dict[str, Any]) -> Dict[str, Any]:
        """Judges one output and returns the verdict fields."""
        verdict = self.judge.judge(
            self.judge_prompts[query.source],
            query.text,
            query.ground_truth,
            gen["candidate"],
        )
        fields = {
            "correct": verdict.correct,
            "error_category": verdict.error_category or None,
            "rationale": verdict.rationale,
        }
        if verdict.judge_failed:
            fields["judge_failed"] = True
        return fields

    def _summarize(self, runs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregates the runs of one query; the reported error is the most frequent one."""
        rate = sum(run["correct"] for run in runs) / len(runs)
        wrong = [run for run in runs if not run["correct"]]
        # Runs the judge failed to read are not errors of the output
        judged_wrong = [run for run in wrong if not run.get("judge_failed")]
        category = (
            Counter(run["error_category"] for run in judged_wrong).most_common(1)[0][0]
            if judged_wrong
            else None
        )
        rationale = next(
            (
                run["rationale"]
                for run in judged_wrong
                if run["error_category"] == category
            ),
            "",
        )
        return {
            "rate": rate,
            "passed": rate >= self.pass_threshold,
            "error_category": category,
            "rationale": rationale,
            "judge_failed": bool(wrong) and not judged_wrong,
            "distinct_outputs": len({run["output"] for run in runs}),
        }

    def _save_csv(
        self, runs_by_query, results, iteration: int, run_timestamp_str: str
    ) -> str:
        if not run_timestamp_str:
            run_timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        outputs_dir = (
            AUTORESEARCH_DIR / "archive" / f"run_{run_timestamp_str}" / "outputs"
        )
        outputs_dir.mkdir(parents=True, exist_ok=True)
        log_file = (
            outputs_dir
            / f"validation_results_iter{iteration}_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        )

        try:
            with open(log_file, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "Query ID",
                        "Source",
                        "Split",
                        "Query Text",
                        "Run Number",
                        "Candidate Raw",
                        "Candidate JSON",
                        "Correct",
                        "Error Category",
                        "Rationale",
                        "Query Rate",
                        "Distinct Outputs",
                    ]
                )
                for query in self.queries:
                    summary = results[query.id]
                    for i, run in enumerate(runs_by_query[query.id], 1):
                        writer.writerow(
                            [
                                query.id,
                                query.source,
                                query.split,
                                query.text,
                                i,
                                run["candidate_raw"] or "",
                                run["candidate"] or "",
                                run["correct"],
                                run["error_category"] or "",
                                run["rationale"],
                                summary["rate"],
                                summary["distinct_outputs"],
                            ]
                        )
            logger.info("Saved validation results to %s", log_file)
        except Exception as e:
            logger.error("Failed to save validation results: %s", e)
        return str(log_file)
