"""The optimization loop: proposes changes to the instructions, evaluates them and keeps the ones that win."""
import logging
import sys
from typing import Any, Dict, List, Optional, Tuple

from autoresearch.core import Experiment
from autoresearch.core.acceptance import decide, mean_rate, net_change, pick_hidden, word_count
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
    """Keeps the champion prompt and runs the iterations that try to improve it."""

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

        prompt = prompt_store.get_latest_prompt_content()
        if not prompt:
            logger.error("Prompt could not be loaded.")
            sys.exit(1)
        self.prefix, self.instructions, self.suffix = self.assembler.extract_instructions(prompt)
        self.prompt_context = f"{self.prefix.strip()}\n\n{self.suffix.strip()}"

        # Champion state, set by _start()
        self.results: Results = {}
        self.score = 0.0
        self.prompt_path = ""
        self.iteration = 0
        self.discards = 0  # optimize iterations rejected since the last kept change
        self.simplify_next = False

    def run(self) -> None:
        self._start()
        logger.info("Minimum net gain to keep a change: %d", self.acceptance["min_net_gain"])
        logger.info("Entering optimization loop...")
        while not self._should_stop() and self._run_iteration():
            pass

        logger.info("Optimization process completed.")
        final = self.experiments.get_champion()
        if final:
            logger.info(
                "Champion prompt from iteration #%d with mean correct rate %.4f",
                final.iteration, mean_rate(final.reference_results),
            )

    # ------------------------------------------------------------------
    # Champion
    # ------------------------------------------------------------------

    def _start(self) -> None:
        """Restores the champion of a resumed run, or evaluates the baseline to set it."""
        champion = self.experiments.get_champion()
        if champion:
            self.iteration = self.experiments.get_next_iteration_number()
            logger.info("Resuming optimization loop from iteration #%d.", self.iteration)
            # The champion is evaluated again so verdicts fixed by hand in the verdict cache apply;
            # its outputs are unchanged, so the judge is not called again
            logger.info("Evaluating the champion again to read its verdicts from the verdict cache...")
            _, self.results, _ = self._evaluate_champion(champion.iteration)
        else:
            champion = self._evaluate_baseline()
            self.iteration = 1
            self.results = champion.reference_results

        self.score = mean_rate(self.results)
        self.prompt_path = champion.prompt_path
        logger.info("Current champion: iteration #%d with mean correct rate %.4f", champion.iteration, self.score)

        # Restore the optimizer's memory of the changes rejected since the last kept prompt
        history = self.experiments.load_history()
        rejected = rejected_since_keep(history)
        self.discards = sum(exp.mode == "optimize" for exp in rejected)
        self.simplify_next = history[-1].status == "KEEP" and history[-1].mode == "optimize"
        for exp in rejected:
            if exp.instructions is not None:
                self.optimizer.add_to_failure_history(
                    self.instructions, exp.instructions, exp.net, self._broken(exp.query_results)
                )

    def _evaluate_baseline(self) -> Experiment:
        logger.info("=== Iteration #0 (baseline) ===")
        score, results, log_file = self._evaluate_champion(0)
        prompt = self.assembler.assemble_prompt(self.prefix, self.instructions, self.suffix)
        champion = Experiment(
            iteration=0, score=score, delta=0.0, status="CHAMPION_INIT",
            prompt_path=str(self.prompt_store.save_champion(0, prompt)), query_results=results,
            instructions_words=word_count(self.instructions), results_file=log_file, reference_results=results,
        )
        self.experiments.log_experiment(champion)
        logger.info("Baseline established.")
        return champion

    def _evaluate_champion(self, iteration: int) -> Tuple[float, Results, str]:
        prompt = self.assembler.assemble_prompt(self.prefix, self.instructions, self.suffix)
        try:
            return self.runner.run_validation(prompt, iteration, self.run_timestamp)
        except ValidationAborted as e:
            logger.error("%s. Stopping: run again to repeat the champion evaluation.", e)
            sys.exit(1)

    # ------------------------------------------------------------------
    # Iterations
    # ------------------------------------------------------------------

    def _should_stop(self) -> bool:
        # Checked first so the file is always consumed, whatever else would stop the loop
        if STOP_FILE.exists():
            logger.info("Graceful stop flagged via '%s' file. Exiting loop cleanly.", STOP_FILE)
            STOP_FILE.unlink(missing_ok=True)
            return True
        max_iterations = self.loop_settings["max_iterations"]
        if max_iterations != -1 and self.iteration > max_iterations:
            logger.info("Reached max_iterations (%d). Stopping optimization.", max_iterations)
            return True
        if all(result["passed"] for result in self.results.values()):
            logger.info("Every query passes. Stopping optimization.")
            return True
        if self.discards >= self.loop_settings["max_consecutive_discards"]:
            logger.info("%d iterations in a row without improvement. Stopping optimization.", self.discards)
            return True
        return False

    def _run_iteration(self) -> bool:
        """Runs one iteration. Returns False when the loop has to stop."""
        hidden_ids = pick_hidden(
            self.runner.queries, self.acceptance["hidden_fraction"], self.acceptance["seed"] + self.iteration
        )
        failures = self.runner.build_failures(self.results, excluded_ids=hidden_ids)
        mode = self._choose_mode(failures)
        self.simplify_next = False
        logger.info("=== Iteration #%d (%s) ===", self.iteration, mode)
        logger.info("Champion mean correct rate: %.4f", self.score)
        logger.info("Failing queries shown to the optimizer: %d (%d queries hidden)", len(failures), len(hidden_ids))

        try:
            instructions, rationale = self.optimizer.optimize_instructions(
                self.instructions, self.prompt_context, failures, mode
            )
        except Exception as e:
            logger.error("Optimization error: %s. Exiting optimization loop to prevent infinite retry.", e)
            return False

        skip_reason = self._skip_reason(instructions, mode)
        if skip_reason:
            self._skip(instructions, rationale, skip_reason, mode, hidden_ids)
        else:
            try:
                self._evaluate_candidate(instructions, rationale, mode, hidden_ids)
            except ValidationAborted as e:
                logger.error("%s. Stopping: resume to repeat iteration #%d.", e, self.iteration)
                return False
        self.iteration += 1
        return True

    def _choose_mode(self, failures: List[Dict[str, Any]]) -> str:
        # A kept change is followed by one simplification; with every failing query hidden there is
        # nothing to address, so the iteration simplifies instead
        return "simplify" if self.simplify_next or not failures else "optimize"

    def _skip_reason(self, instructions: str, mode: str) -> Optional[str]:
        """Why a candidate cannot be kept without evaluating it, or None if it has to be evaluated."""
        if not instructions.strip() or instructions.strip() == self.instructions.strip():
            return "the instructions are empty or unchanged"
        if mode == "simplify" and word_count(instructions) >= word_count(self.instructions):
            return "the simplified instructions are not shorter"
        return None

    def _skip(self, instructions: str, rationale: str, reason: str, mode: str, hidden_ids: List[str]) -> None:
        logger.info("SKIPPED: %s.", reason)
        self._reject(instructions, 0, [], mode)
        self.experiments.log_experiment(Experiment(
            iteration=self.iteration, score=0.0, delta=0.0, status="SKIPPED", prompt_path=self.prompt_path,
            mode=mode, hidden_ids=hidden_ids, instructions_words=word_count(instructions),
            instructions=instructions, rationale=f"Not evaluated: {reason}.\n\n{rationale}",
        ))

    def _net(self, results: Results, hidden_ids: List[str]) -> Tuple[int, int]:
        """Net change against the champion on all queries and on the hidden ones."""
        return net_change(self.results, results, results.keys()), net_change(self.results, results, hidden_ids)

    def _evaluate_candidate(self, instructions: str, rationale: str, mode: str, hidden_ids: List[str]) -> None:
        """Evaluates a candidate and keeps or discards it."""
        prompt = self.assembler.assemble_prompt(self.prefix, instructions, self.suffix)
        score, results, log_file = self.runner.run_validation(prompt, self.iteration, self.run_timestamp)
        net, net_hidden = self._net(results, hidden_ids)
        words_before, words_after = word_count(self.instructions), word_count(instructions)
        shorter = words_after < words_before
        logger.info(
            "Candidate mean correct rate: %.4f | net: %+d | net on hidden queries: %+d | words: %d -> %d",
            score, net, net_hidden, words_before, words_after,
        )

        keep = decide(net, net_hidden, shorter, mode, self.acceptance["min_net_gain"])
        delta = score - self.score
        if keep:
            status = "KEEP"
            self._keep(instructions, prompt, results, mode)
        else:
            status = "DISCARDED"
            logger.info("DISCARDED: the change does not meet the acceptance rule.")
            self._reject(instructions, net, self._broken(results), mode)

        # prompt_path is the new champion when kept, or the champion the candidate was compared against
        self.experiments.log_experiment(Experiment(
            iteration=self.iteration, score=score, delta=delta, status=status, prompt_path=self.prompt_path,
            mode=mode, query_results=results, hidden_ids=hidden_ids, net=net, net_hidden=net_hidden,
            instructions_words=words_after, instructions=instructions, rationale=rationale,
            results_file=log_file, reference_results=results if keep else None,
        ))
        logger.info("Iteration #%d logged to experiments.json.", self.iteration)

    def _broken(self, results: Results) -> List[Dict[str, str]]:
        """The queries the champion passes and a candidate fails, with the judge's rationale."""
        return [
            {"id": qid, "rationale": result["rationale"]}
            for qid, result in results.items()
            if self.results[qid]["passed"] and not result["passed"]
        ]

    def _reject(self, instructions: str, net: int, broken: List[Dict[str, str]], mode: str) -> None:
        self.optimizer.add_to_failure_history(self.instructions, instructions, net, broken)
        # Only optimize iterations count toward the stop: a simplification does not try to fix anything
        if mode == "optimize":
            self.discards += 1

    def _keep(self, instructions: str, prompt: str, results: Results, mode: str) -> None:
        logger.info("KEEP: saving new champion prompt.")
        self.prompt_path = str(self.prompt_store.save_champion(self.iteration, prompt))
        self.optimizer.clear_failure_history()
        self.instructions = instructions
        self.results = results
        self.score = mean_rate(results)
        self.discards = 0
        self.simplify_next = mode == "optimize"
        logger.info("New champion mean correct rate: %.4f", self.score)
