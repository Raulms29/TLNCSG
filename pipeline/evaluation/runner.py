"""Runner for the Evaluation Module."""

from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path
from typing import Any

from pipeline.clients.ollama_client import OllamaClient
from .config import EvaluationConfig
from pipeline.grouping.normalizers import decode_breakdown, split_breakdown_key
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

        n_files = sum(1 for _ in self.grouping_dir.glob("*/*_grouped.csv"))
        logger.info(
            "=== Evaluation started: %s (%d files, evaluator: %s) ===",
            dir_name,
            n_files,
            self.config.evaluator_model.name,
        )

        # Pre-load prompts to memory
        self._preload_prompts()

        total_files = 0
        # [files, groups, correct groups, runs, correct runs], per grammar and per
        # (grammar, model). A pooled group counts once for its grammar and once for
        # every model in its Run Breakdown, with that model's runs only.
        grammar_stats: dict[str, list[int]] = {}
        model_stats: dict[tuple[str, str], list[int]] = {}

        # Traverse: GRAMMAR / Q1_grouped.csv
        grammar_dirs = sorted(d for d in self.grouping_dir.iterdir() if d.is_dir())
        for grammar_idx, grammar_dir in enumerate(grammar_dirs, 1):
            grammar = grammar_dir.name
            out_grammar = output_root / grammar
            out_grammar.mkdir(parents=True, exist_ok=True)
            logger.info(
                "--- Grammar: %s [%d/%d] ---", grammar, grammar_idx, len(grammar_dirs)
            )
            g_stats = grammar_stats.setdefault(grammar, [0, 0, 0, 0, 0])

            for csv_file in sorted(grammar_dir.glob("*_grouped.csv")):
                total_files += 1
                evaluated_rows = self._process_grouped_file(csv_file, grammar)

                n_correct = sum(
                    1 for row in evaluated_rows if row.get("Correct") == "True"
                )
                g_stats[0] += 1
                g_stats[1] += len(evaluated_rows)
                g_stats[2] += n_correct
                for row in evaluated_rows:
                    is_correct = row.get("Correct") == "True"
                    size = int(row.get("Group Size") or 0)
                    g_stats[3] += size
                    g_stats[4] += size if is_correct else 0
                    for key, runs in decode_breakdown(row.get("Run Breakdown", "")).items():
                        model_dir, thinking = split_breakdown_key(key)
                        label = f"{model_dir} (Thinking)" if thinking else model_dir
                        m_stats = model_stats.setdefault((grammar, label), [0, 0, 0, 0, 0])
                        m_stats[1] += 1
                        m_stats[2] += int(is_correct)
                        m_stats[3] += len(runs)
                        m_stats[4] += len(runs) if is_correct else 0
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

                out_csv = out_grammar / csv_file.name.replace(
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
            _summary(list(grammar_stats.values())),
        )
        for grammar, g_stats in grammar_stats.items():
            logger.info("  %s — %s", grammar, _summary([g_stats]))
            for (g, model), s in sorted(model_stats.items()):
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
                evaluated.append(row)
                continue

            # Select the correct prompt dynamically
            grammar_clean = grammar.upper()
            dataset_clean = dataset.upper()
            prompt_filename = f"EVAL_{grammar_clean}_{dataset_clean}.prompt.md"

            sys_prompt = self._prompt_cache.get(prompt_filename)
            if not sys_prompt:
                # Fallback: substring match (e.g. semgir_notypes -> semgir)
                for cached_name, cached_prompt in self._prompt_cache.items():
                    # Must match dataset
                    if dataset_clean not in cached_name:
                        continue
                    # Check if any known grammar base is in the current grammar
                    base_grammar = cached_name.replace("EVAL_", "").replace(f"_{dataset_clean}.prompt.md", "").lower()
                    if base_grammar in grammar_clean.lower():
                        sys_prompt = cached_prompt
                        break

            if not sys_prompt:
                msg = f"Missing required evaluation prompt for '{grammar}' (dataset: {dataset}) in {self.prompts_dir}"
                logger.error(msg)
                raise FileNotFoundError(msg)

            # Build user message
            user_message = self._build_user_message(
                query_text, candidate_output, gt, dataset
            )

            # Call evaluator LLM
            content, _, _, _ = self.client.chat_with_metadata(
                model=self.config.evaluator_model.name,
                query=user_message,
                system_prompt=sys_prompt,
                options=self.config.evaluator_model.ollama_options,
                temperature=self.config.evaluator_model.temperature,
                thinking=self.config.evaluator_model.supports_thinking,
            )

            # Parse the LLM's JSON response (take the last block)
            result = self._parse_eval_response(content)

            row["Rationale"] = result.get("rationale", "")
            row["Hypotheses Covered"] = result.get("hypotheses_covered", 1)
            row["Correct"] = str(result.get("correct", False))
            evaluated.append(row)

        return evaluated

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
        parts.append("Assign correct and rationale in strict JSON format:")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_eval_response(content: str) -> dict:
        """Extract the last JSON block from the LLM response."""
        matches = list(
            re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", content, re.IGNORECASE)
        )
        extracted = matches[-1].group(1) if matches else content.strip()

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
            }

    # ------------------------------------------------------------------
    # CSV output
    # ------------------------------------------------------------------

    @staticmethod
    def _save_evaluated_csv(out_path: Path, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        fieldnames = [
            "QID",
            "Query",
            "Output Key",
            "Hypotheses Covered",
            "Correct",
            "LLM Merged",
            "Group Size",
            "Rationale",
            "Representative Output",
            "Reasoning",
            "Run Breakdown",
        ]
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
