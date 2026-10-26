"""Runner for the Evaluation Module."""

from __future__ import annotations

import csv
import json
import logging
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from pipeline.clients.ollama_client import OllamaClient
from pipeline.grammars import prompt_for_grammar
from pipeline.grouping.normalizers import last_code_block
from .config import EvaluationConfig
from .error_categories import canonical_category
from .ground_truth import GroundTruth, GroundTruthStore

logger = logging.getLogger(__name__)


class EvaluationRunner:
    """Orchestrates reading Grouping output, evaluating each group, and saving results."""

    def __init__(
        self,
        config: EvaluationConfig,
        client: OllamaClient,
        ground_truth: GroundTruthStore,
        prompts_dir: Path,
        grouping_dir: str | Path,
    ):
        self.config = config
        self.client = client
        self.ground_truth = ground_truth
        self.prompts_dir = prompts_dir
        self.grouping_dir = Path(grouping_dir)
        self._prompt_cache: dict[str, str] = {}

    def run(self) -> Path:
        """Executes the evaluation pipeline."""
        # Parse the grouping directory name to mirror it
        dir_name = self.grouping_dir.name
        output_root = Path(self.config.output_dir) / dir_name
        output_root.mkdir(parents=True, exist_ok=True)

        # Set up file logging
        file_handler = logging.FileHandler(
            output_root / "evaluation.log", encoding="utf-8"
        )
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s", "%Y-%m-%d %H:%M:%S")
        )
        logging.getLogger().addHandler(file_handler)

        n_files = sum(1 for _ in self.grouping_dir.glob("*/*/*_grouped.csv"))
        logger.info(
            "=== Evaluation started: %s (%d files, evaluator: %s) ===",
            dir_name,
            n_files,
            self.config.evaluator_model.name,
        )

        # Pre-load prompts to memory
        self._preload_prompts()

        total_files = 0
        # (grammar, model) -> [files, groups, correct groups, runs, correct runs]
        stats: dict[tuple[str, str], list[int]] = {}

        # Traverse: GRAMMAR / model / Q1_grouped.csv
        grammar_dirs = sorted(d for d in self.grouping_dir.iterdir() if d.is_dir())
        for grammar_idx, grammar_dir in enumerate(grammar_dirs, 1):
            grammar = grammar_dir.name
            out_grammar = output_root / grammar
            logger.info(
                "--- Grammar: %s [%d/%d] ---", grammar, grammar_idx, len(grammar_dirs)
            )

            for model_dir in sorted(d for d in grammar_dir.iterdir() if d.is_dir()):
                model = model_dir.name
                out_model = out_grammar / model
                out_model.mkdir(parents=True, exist_ok=True)
                logger.info("  Model: %s", model)
                model_stats = stats.setdefault((grammar, model), [0, 0, 0, 0, 0])

                csv_files = sorted(model_dir.glob("*_grouped.csv"))
                for csv_file, evaluated_rows in zip(
                    csv_files, self._evaluate_files(csv_files, grammar)
                ):
                    total_files += 1

                    n_correct = sum(
                        1 for row in evaluated_rows if row.get("Correct") == "True"
                    )
                    model_stats[0] += 1
                    model_stats[1] += len(evaluated_rows)
                    model_stats[2] += n_correct
                    for row in evaluated_rows:
                        size = int(row.get("Group Size") or 0)
                        model_stats[3] += size
                        if row.get("Correct") == "True":
                            model_stats[4] += size
                    # One mark per group with its size, e.g. "✓12  ✗5  ✓1"
                    marks = "  ".join(
                        f"{'✓ ' if row.get('Correct') == 'True' else '✗ '}{row.get('Group Size', '?')}"
                        for row in evaluated_rows
                    )
                    logger.info(
                        "    [%d/%d] %s — %d/%d | %s",
                        total_files,
                        n_files,
                        csv_file.name.replace("_grouped.csv", ""),
                        n_correct,
                        len(evaluated_rows),
                        marks,
                    )

                    out_csv = out_model / csv_file.name.replace(
                        "_grouped.csv", "_evaluated.csv"
                    )
                    self._save_evaluated_csv(out_csv, evaluated_rows)

        def _summary(rows: list[list[int]]) -> str:
            _, groups, correct, runs, correct_runs = (
                sum(c) for c in zip([0] * 5, *rows)
            )
            pct = 100 * correct_runs / runs if runs else 0.0
            return (
                f"{correct}/{groups} groups correct, "
                f"{correct_runs}/{runs} runs correct ({pct:.1f}%)"
            )

        logger.info(
            "=== Evaluation finished: %d files — %s ===",
            total_files,
            _summary(list(stats.values())),
        )
        for grammar in dict.fromkeys(g for g, _ in stats):
            logger.info(
                "  %s — %s",
                grammar,
                _summary([s for (g, _), s in stats.items() if g == grammar]),
            )
            for (g, model), s in stats.items():
                if g == grammar:
                    logger.info("    %s — %s", model, _summary([s]))
        return output_root

    def _preload_prompts(self) -> None:
        """Pre-load all available evaluation prompts into the cache."""
        count = 0
        for prompt_file in self.prompts_dir.glob("EVAL_*.prompt.md"):
            self._prompt_cache[prompt_file.name] = prompt_file.read_text(encoding="utf-8")
            count += 1
        logger.info("Pre-loaded %d evaluation prompts.", count)

    # ------------------------------------------------------------------
    # Per-file processing
    # ------------------------------------------------------------------

    def _evaluate_files(
        self, csv_files: list[Path], grammar: str
    ) -> Iterator[list[dict[str, Any]]]:
        """Evaluate up to ``parallel_requests`` files at once, yielding results in file order."""
        with ThreadPoolExecutor(self.config.parallel_requests) as pool:
            yield from pool.map(
                lambda csv_file: self._process_grouped_file(csv_file, grammar), csv_files
            )

    def _process_grouped_file(
        self, csv_file: Path, grammar: str
    ) -> list[dict[str, Any]]:
        """Read a grouped CSV, evaluate each group, and return evaluated rows."""
        rows = []
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

        if not rows:
            return []

        evaluated = []
        for row in rows:
            qid = row.get("QID", "")
            query_text = row.get("Query", "")
            candidate_output = row.get("Representative Output", "")

            # Detect dataset and fetch ground truth
            dataset = self.ground_truth.detect_dataset(qid)
            gt = self.ground_truth.get(qid)

            if gt is None:
                logger.warning(
                    "No ground truth found for QID %s, skipping evaluation.",
                    qid,
                )
                row["Rationale"] = "Ground truth not found"
                row["Hypotheses Covered"] = 0
                row["Correct"] = "False"
                row["LLM Error Category"] = ""
                evaluated.append(row)
                continue

            sys_prompt = prompt_for_grammar(self._prompts_for_dataset(dataset), grammar)
            if not sys_prompt:
                msg = f"Missing required evaluation prompt for '{grammar}' (dataset: {dataset}) in {self.prompts_dir}"
                logger.error(msg)
                raise FileNotFoundError(msg)

            # Build user message
            user_message = self._build_user_message(
                query_text, candidate_output, gt, dataset
            )

            # Call evaluator LLM
            evaluator = self.config.evaluator_model
            content, meta = self._judge(evaluator.name, user_message, sys_prompt)
            # The thinking looped until num_predict: the same model at temperature 0 usually loops again
            if evaluator.fallback_model and meta["done_reason"] == "length" and not content.strip():
                logger.warning("Evaluator ran out of tokens on %s, retrying with %s", qid, evaluator.fallback_model)
                content, _ = self._judge(evaluator.fallback_model, user_message, sys_prompt)

            # Parse the LLM's JSON response (take the last block)
            result = self._parse_eval_response(content)

            row["Rationale"] = result.get("rationale", "")
            row["Hypotheses Covered"] = result.get("hypotheses_covered", 1)
            correct = result.get("correct", False) is True
            row["Correct"] = str(result.get("correct", False))
            row["LLM Error Category"] = (
                "" if result.get("unparseable")
                else self._normalize_error_category(result.get("error_category"), correct)
            )
            evaluated.append(row)

        return evaluated

    def _prompts_for_dataset(self, dataset: str) -> dict[str, str]:
        """The evaluation prompts of one dataset keyed by grammar: EVAL_SEMGIR_GRAILQA.prompt.md -> semgir."""
        suffix = f"_{dataset.upper()}.prompt.md"
        return {
            name[len("EVAL_"):-len(suffix)].lower(): prompt
            for name, prompt in self._prompt_cache.items()
            if name.endswith(suffix)
        }

    def _judge(self, model: str, user_message: str, sys_prompt: str) -> tuple[str, dict]:
        """One evaluator call: returns the response content and the Ollama metadata."""
        content, _, _, meta = self.client.chat_with_metadata(
            model=model,
            query=user_message,
            system_prompt=sys_prompt,
            options=self.config.evaluator_model.ollama_options,
            temperature=self.config.evaluator_model.temperature,
            thinking=self.config.evaluator_model.supports_thinking,
        )
        return content, meta

    # ------------------------------------------------------------------
    # User message construction
    # ------------------------------------------------------------------

    def _build_user_message(
        self,
        query: str,
        candidate: str,
        gt: GroundTruth,
        dataset: str,
    ) -> str:
        """Build the user prompt with query, candidate, and ground truth."""
        parts = [f'[ORIGINAL NATURAL LANGUAGE QUERY]\n"{query}"\n']

        if dataset == "ambrosia":
            parts.append(f"[DATABASE SCHEMA]\n{gt.db_dump}\n")
            parts.append(f"[GROUND TRUTH SQL]\n{gt.gold_queries}\n")
        else:  # grailqa
            parts.append(f"[GROUND TRUTH LISP]\n{gt.s_expression_friendly}\n")

        parts.append(f"[CANDIDATE OUTPUT]\n{candidate}\n")
        parts.append("Assign rationale, correct and error_category in strict JSON format:")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_eval_response(content: str) -> dict:
        """Extract the last JSON block from the LLM response."""
        extracted = last_code_block(content, "json")

        # Hardening: extract just the JSON object bounds if there is garbage text around it
        if "{" in extracted and "}" in extracted:
            start = extracted.find("{")
            end = extracted.rfind("}") + 1
            extracted = extracted[start:end]

        try:
            return json.loads(extracted)
        except json.JSONDecodeError:
            logger.warning("Evaluator returned unparseable JSON. Raw: %r", content)
            return {
                "rationale": f"Unparseable evaluator response: {content[:200]}",
                "hypotheses_covered": 1,
                "correct": False,
                # The judge failed, not the candidate: no error category
                "unparseable": True,
            }

    @staticmethod
    def _normalize_error_category(value: Any, correct: bool) -> str:
        """Map the judge's category to its canonical name ("" if correct, "Other" if unknown)."""
        if correct:
            return ""
        category = canonical_category(value)
        if category == "Other" and str(value or "").strip().lower() != "other":
            logger.warning("Evaluator returned unknown error category %r, using 'Other'.", value)
        return category

    # ------------------------------------------------------------------
    # CSV output
    # ------------------------------------------------------------------

    @staticmethod
    def _save_evaluated_csv(out_path: Path, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        fieldnames = [
            "Model",
            "Thinking",
            "QID",
            "Query",
            "Output Key",
            "Hypotheses Covered",
            "Correct",
            "LLM Error Category",
            "LLM Merged",
            "Group Size",
            "Rationale",
            "Representative Output",
            "Reasoning",
            "Runs",
        ]
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
