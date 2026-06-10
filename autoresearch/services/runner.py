import json
from pathlib import Path
from typing import List, Dict, Any, Tuple
from autoresearch.core.query import Query
import utils
from autoresearch.services.generator import GeneratorClient
from autoresearch.services.evaluator import EvaluatorAgent

class ValidationRunner:
    """
    Orchestrates query generations and evaluations over the full validation dataset.
    Computes overall performance metrics and isolates failure logs.
    Each query can be run multiple times (runs_per_query); scores are averaged and
    the rationale from the worst-scoring run is used for failure reporting.
    """
    def __init__(
        self,
        ground_truths_path: str,
        generator: GeneratorClient,
        evaluator: EvaluatorAgent,
        runs_per_query: int = 1
    ):
        self.ground_truths_path = Path(ground_truths_path)
        self.generator = generator
        self.evaluator = evaluator
        self.runs_per_query = max(1, runs_per_query)
        self.queries = self._load_queries()

    def _load_queries(self) -> List[Query]:
        """Loads validation queries from ground_truth_sem_gir.json."""
        if not self.ground_truths_path.exists():
            raise FileNotFoundError(
                f"Ground truths file not found at '{self.ground_truths_path}'"
            )

        with open(self.ground_truths_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        queries = []
        for q_id, q_data in data.items():
            query_text = q_data.get("query", "").strip()
            solution = q_data.get("solution", "")
            if query_text:
                queries.append(Query(q_id, query_text, solution))

        return queries

    def run_validation(self, system_prompt: str) -> Tuple[float, List[Dict[str, Any]]]:
        """
        Executes the generator and evaluator on all queries.
        Each query is run runs_per_query times; scores are averaged and the
        rationale from the worst run is used for failure logging.
        Returns:
            mean_score: The average score across the validation set.
            failures: List of dicts describing failed queries (score < 1.0)
                      containing query_id, features, and rationale.
        """
        scores = []
        failures = []

        total_queries = len(self.queries)
        multi_run = self.runs_per_query > 1
        print(f"Starting validation run on {total_queries} queries"
              f"{f' x{self.runs_per_query} runs' if multi_run else ''}...")

        for idx, query in enumerate(self.queries, 1):
            print(f"  [{idx}/{total_queries}] Processing Query {query.id}...")

            # Convert ground truth solution to JSON string once per query
            gt_obj = query.solution
            if isinstance(gt_obj, (dict, list)):
                gt_str = json.dumps(gt_obj, indent=2)
            else:
                gt_str = str(gt_obj)

            run_scores: List[float] = []
            run_rationales: List[str] = []

            for _ in range(self.runs_per_query):
                # 1. Generate candidate SemGIR translation
                try:
                    candidate_raw = self.generator.generate_translation(system_prompt, query.text)
                    candidate_json = utils._extract_json_text(candidate_raw)
                except Exception as e:
                    run_scores.append(0.0)
                    run_rationales.append(f"Generator execution failed: {str(e)}")
                    continue

                # 2. Call Evaluator (LLM-as-a-Judge)
                try:
                    score, rationale = self.evaluator.evaluate(query.text, gt_str, candidate_json)
                except Exception as e:
                    score = 0.0
                    rationale = f"Evaluator execution failed: {str(e)}"

                run_scores.append(score)
                run_rationales.append(rationale)

            # Aggregate across runs: average score, worst-run rationale
            query_score = sum(run_scores) / len(run_scores) if run_scores else 0.0
            worst_idx = run_scores.index(min(run_scores)) if run_scores else 0
            query_rationale = run_rationales[worst_idx] if run_rationales else "No runs completed."

            scores.append(query_score)
            print(f"    Query {query.id} Score: {query_score:.2f}"
                  f"{f' (avg of {len(run_scores)} runs)' if multi_run else ''}")

            # 3. Log failures for scores strictly less than 1.0
            if query_score < 1.0:
                failures.append({
                    "id": query.id,
                    "features": query.features,
                    "rationale": query_rationale
                })

        mean_score = sum(scores) / len(scores) if scores else 0.0
        print(f"Validation run completed. Overall Mean Score: {mean_score:.4f}")
        return mean_score, failures
