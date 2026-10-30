"""The optimization loop: proposes changes to the instructions, evaluates them and keeps the ones that win."""

import logging
import sys
from typing import Any, Dict, List, Tuple

from autoresearch.core import Experiment
from autoresearch.core.acceptance import mean_rate, net_change, word_count
from autoresearch.core.constants import AUTORESEARCH_DIR
from autoresearch.services import OptimizerAgent, PromptAssembler, ValidationRunner
from autoresearch.services.runner import ValidationAborted
from autoresearch.storage import ExperimentLogger, PromptStore

logger = logging.getLogger(__name__)

Results = Dict[str, Dict[str, Any]]
DISCARD_STATUSES = ("DISCARDED", "SKIPPED")
STOP_FILE = AUTORESEARCH_DIR / "stop.txt"


def rejected_since_keep(history: List[Experiment]) -> List[Experiment]:
    """The discarded or skipped iterations since the last kept one, oldest first."""
    rejected = []
    for exp in reversed(history):
        if exp.status not in DISCARD_STATUSES:
            break
        rejected.insert(0, exp)
    return rejected


class OptimizationLoop:
    """
    Keeps the champion prompt and runs the iterations that try to improve it.
    The optimizer sees the failing train queries; a candidate is kept when it wins on the val queries.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        runner: ValidationRunner,
        optimizer: OptimizerAgent,
        prompt_store: PromptStore,
        experiments: ExperimentLogger,
        run_timestamp: str,
    ):
        self.acceptance = config["acceptance"]
        self.loop_settings = config["loop_settings"]
        self.runner = runner
        self.optimizer = optimizer
        self.prompt_store = prompt_store
        self.experiments = experiments
        self.run_timestamp = run_timestamp
        self.assembler = PromptAssembler()
        self.train_ids = [
            query.id for query in runner.queries if query.split == "train"
        ]
        self.val_ids = [query.id for query in runner.queries if query.split == "val"]

        prompt = prompt_store.get_latest_prompt_content()
        if not prompt:
            logger.error("Prompt could not be loaded.")
            sys.exit(1)
        self.prefix, self.instructions, self.suffix = (
            self.assembler.extract_instructions(prompt)
        )
        self.prompt_context = f"{self.prefix.strip()}\n\n{self.suffix.strip()}"

        # Champion state, set by _start()
        self.results: Results = {}
        self.score = 0.0  # mean correct rate on val
        self.prompt_path = ""
        self.iteration = 0
        self.discards = 0  # iterations rejected since the last kept change

    def run(self) -> None:
        self._start()
        logger.info("Queries: %d train, %d val", len(self.train_ids), len(self.val_ids))
        logger.info(
            "Minimum net gain on val to keep a change: %d",
            self.acceptance["min_net_gain"],
        )
        logger.info("Entering optimization loop...")
        while not self._should_stop() and self._run_iteration():
            pass

        logger.info("Optimization process completed.")
        final = self.experiments.get_champion()
        if final:
            logger.info(
                "Champion prompt from iteration #%d with val mean correct rate %.4f",
                final.iteration,
                mean_rate(final.reference_results, self.val_ids),
            )

    # ------------------------------------------------------------------
    # Champion
    # ------------------------------------------------------------------

    def _start(self) -> None:
        """Restores the champion of a resumed run, or evaluates the baseline to set it."""
        champion = self.experiments.get_champion()
        if champion:
            self.iteration = self.experiments.get_next_iteration_number()
            logger.info(
                "Resuming optimization loop from iteration #%d.", self.iteration
            )
            # The champion is evaluated again so verdicts fixed by hand in the verdict cache apply;
            # its outputs are unchanged, so the judge is not called again
            logger.info(
                "Evaluating the champion again to read its verdicts from the verdict cache..."
            )
            self.results, _ = self._evaluate_champion(champion.iteration)
        else:
            champion = self._evaluate_baseline()
            self.iteration = 1
            self.results = champion.reference_results

        self.score = mean_rate(self.results, self.val_ids)
        self.prompt_path = champion.prompt_path
        logger.info(
            "Current champion: iteration #%d with val mean correct rate %.4f (train %.4f)",
            champion.iteration,
            self.score,
            mean_rate(self.results, self.train_ids),
        )

        # Restore the optimizer's memory of the changes rejected since the last kept prompt
        rejected = rejected_since_keep(self.experiments.load_history())
        self.discards = len(rejected)
        for exp in rejected:
            if exp.instructions is not None:
                self.optimizer.add_to_failure_history(
                    self.instructions,
                    exp.instructions,
                    exp.net_train,
                    self._broken(exp.query_results),
                )

    def _evaluate_baseline(self) -> Experiment:
        logger.info("=== Iteration #0 (baseline) ===")
        results, log_file = self._evaluate_champion(0)
        prompt = self.assembler.assemble_prompt(
            self.prefix, self.instructions, self.suffix
        )
        champion = Experiment(
            iteration=0,
            score=mean_rate(results, self.val_ids),
            train_score=mean_rate(results, self.train_ids),
            delta=0.0,
            status="CHAMPION_INIT",
            prompt_path=str(self.prompt_store.save_champion(0, prompt)),
            query_results=results,
            instructions_words=word_count(self.instructions),
            results_file=log_file,
            reference_results=results,
        )
        self.experiments.log_experiment(champion)
        logger.info("Baseline established.")
        return champion

    def _evaluate_champion(self, iteration: int) -> Tuple[Results, str]:
        prompt = self.assembler.assemble_prompt(
            self.prefix, self.instructions, self.suffix
        )
        try:
            return self.runner.run_validation(prompt, iteration, self.run_timestamp)
        except ValidationAborted as e:
            logger.error(
                "%s. Stopping: run again to repeat the champion evaluation.", e
            )
            sys.exit(1)

    # ------------------------------------------------------------------
    # Iterations
    # ------------------------------------------------------------------

    def _should_stop(self) -> bool:
        # Checked first so the file is always consumed, whatever else would stop the loop
        if STOP_FILE.exists():
            logger.info(
                "Graceful stop flagged via '%s' file. Exiting loop cleanly.", STOP_FILE
            )
            STOP_FILE.unlink(missing_ok=True)
            return True
        max_iterations = self.loop_settings["max_iterations"]
        if max_iterations != -1 and self.iteration > max_iterations:
            logger.info(
                "Reached max_iterations (%d). Stopping optimization.", max_iterations
            )
            return True
        if all(self.results[qid]["passed"] for qid in self.train_ids):
            logger.info("Every train query passes. Stopping optimization.")
            return True
        if self.discards >= self.loop_settings["max_consecutive_discards"]:
            logger.info(
                "%d iterations in a row without improvement. Stopping optimization.",
                self.discards,
            )
            return True
        return False

    def _run_iteration(self) -> bool:
        """Runs one iteration. Returns False when the loop has to stop."""
        failures = self.runner.build_failures(self.results)
        logger.info("=== Iteration #%d ===", self.iteration)
        logger.info("Champion val mean correct rate: %.4f", self.score)
        logger.info("Failing train queries shown to the optimizer: %d", len(failures))

        try:
            instructions, rationale = self.optimizer.optimize_instructions(
                self.instructions, self.prompt_context, failures
            )
        except Exception as e:
            logger.error(
                "Optimization error: %s. Exiting optimization loop to prevent infinite retry.",
                e,
            )
            return False

        if (
            not instructions.strip()
            or instructions.strip() == self.instructions.strip()
        ):
            self._skip(
                instructions, rationale, "the instructions are empty or unchanged"
            )
        else:
            try:
                self._evaluate_candidate(instructions, rationale)
            except ValidationAborted as e:
                logger.error(
                    "%s. Stopping: resume to repeat iteration #%d.", e, self.iteration
                )
                return False
        self.iteration += 1
        return True

    def _skip(self, instructions: str, rationale: str, reason: str) -> None:
        logger.info("SKIPPED: %s.", reason)
        self._reject(instructions, 0, [])
        self.experiments.log_experiment(
            Experiment(
                iteration=self.iteration,
                score=0.0,
                delta=0.0,
                status="SKIPPED",
                prompt_path=self.prompt_path,
                instructions_words=word_count(instructions),
                instructions=instructions,
                rationale=f"Not evaluated: {reason}.\n\n{rationale}",
            )
        )

    def _evaluate_candidate(self, instructions: str, rationale: str) -> None:
        """Evaluates a candidate on every query and keeps it if it wins on val."""
        prompt = self.assembler.assemble_prompt(self.prefix, instructions, self.suffix)
        results, log_file = self.runner.run_validation(
            prompt, self.iteration, self.run_timestamp
        )
        score, train_score = mean_rate(results, self.val_ids), mean_rate(
            results, self.train_ids
        )
        net_train = net_change(self.results, results, self.train_ids)
        net_val = net_change(self.results, results, self.val_ids)
        logger.info(
            "Candidate mean correct rate: val %.4f, train %.4f | net: val %+d, train %+d | words: %d -> %d",
            score,
            train_score,
            net_val,
            net_train,
            word_count(self.instructions),
            word_count(instructions),
        )

        keep = net_val >= self.acceptance["min_net_gain"]
        delta = score - self.score
        if keep:
            status = "KEEP"
            self._keep(instructions, prompt, results)
        else:
            status = "DISCARDED"
            logger.info("DISCARDED: the net gain on val is below the minimum.")
            self._reject(instructions, net_train, self._broken(results))

        # prompt_path is the new champion when kept, or the champion the candidate was compared against
        self.experiments.log_experiment(
            Experiment(
                iteration=self.iteration,
                score=score,
                train_score=train_score,
                delta=delta,
                status=status,
                prompt_path=self.prompt_path,
                query_results=results,
                net_train=net_train,
                net_val=net_val,
                instructions_words=word_count(instructions),
                instructions=instructions,
                rationale=rationale,
                results_file=log_file,
                reference_results=results if keep else None,
            )
        )
        logger.info("Iteration #%d logged to experiments.json.", self.iteration)

    def _broken(self, results: Results) -> List[Dict[str, str]]:
        """The train queries the champion passes and a candidate fails, with the judge's rationale."""
        return [
            {"id": qid, "rationale": results[qid]["rationale"]}
            for qid in self.train_ids
            if self.results[qid]["passed"] and not results[qid]["passed"]
        ]

    def _reject(
        self, instructions: str, net_train: int, broken: List[Dict[str, str]]
    ) -> None:
        self.optimizer.add_to_failure_history(
            self.instructions, instructions, net_train, broken
        )
        self.discards += 1

    def _keep(self, instructions: str, prompt: str, results: Results) -> None:
        logger.info("KEEP: saving new champion prompt.")
        self.prompt_path = str(self.prompt_store.save_champion(self.iteration, prompt))
        self.optimizer.clear_failure_history()
        self.instructions = instructions
        self.results = results
        self.score = mean_rate(results, self.val_ids)
        self.discards = 0
        logger.info("New champion val mean correct rate: %.4f", self.score)
