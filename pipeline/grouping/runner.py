"""Runner for the Grouping Module."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

from .config import GroupingConfig
from .llm_grouper import LLMGrouper
from .normalizers import normalize_output

logger = logging.getLogger(__name__)


class GroupingRunner:
    """Orchestrates reading Execution output, grouping, and saving grouped CSVs."""

    def __init__(
        self,
        config: GroupingConfig,
        llm_grouper: LLMGrouper | None,
        execution_dir: str | Path,
    ):
        self.config = config
        self.llm_grouper = llm_grouper
        self.execution_dir = Path(execution_dir)

    def run(self) -> Path:
        """Executes the grouping pipeline."""
        start_date = self.execution_dir.name.split("_")[0]
        end_date = self.execution_dir.name.split("_")[1]
        exec_id = self.execution_dir.name.split("_")[-1]

        output_root = (
            Path(self.config.output_dir) / f"{start_date}_{end_date}_{exec_id}"
        )
        output_root.mkdir(parents=True, exist_ok=True)

        logger.info("Starting grouping for execution: %s", self.execution_dir.name)

        total_files = 0
        total_rows_before = 0
        total_rows_after = 0

        # Traverse: GRAMMAR / model / Q1.csv
        for grammar_dir in [d for d in self.execution_dir.iterdir() if d.is_dir()]:
            grammar = grammar_dir.name
            out_grammar = output_root / grammar

            for model_dir in [d for d in grammar_dir.iterdir() if d.is_dir()]:
                model = model_dir.name
                out_model = out_grammar / model
                out_model.mkdir(parents=True, exist_ok=True)

                for csv_file in model_dir.glob("*.csv"):
                    if "summary" in csv_file.name.lower():
                        continue  # Skip only summary files

                    total_files += 1
                    grouped_rows = self._process_query_file(csv_file, grammar)

                    total_rows_before += sum(row["Group Size"] for row in grouped_rows)
                    total_rows_after += len(grouped_rows)

                    out_csv = out_model / csv_file.name.replace(".csv", "_grouped.csv")
                    self._save_grouped_csv(out_csv, grouped_rows)

        logger.info(
            "Grouping complete. Processed %d files. Reduced %d rows down to %d groups.",
            total_files,
            total_rows_before,
            total_rows_after,
        )
        return output_root

    def _process_query_file(self, csv_file: Path, grammar: str) -> list[dict[str, Any]]:
        """Reads a QX.csv file, groups the 30 runs, and returns grouped rows."""
        runs = []
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                runs.append(row)

        if not runs:
            return []

        # Phase 1: Deterministic Normalization
        groups: dict[str, list[dict]] = {}
        for run in runs:
            raw_out = run.get("Response", "")
            norm_out = normalize_output(raw_out, grammar)

            if norm_out not in groups:
                groups[norm_out] = []
            groups[norm_out].append(run)

        # Phase 2: LLM Fallback (Merge Singletons)
        if self.config.enable_llm_fallback and self.llm_grouper:
            groups = self._apply_llm_fallback(groups, grammar)

        # Convert groups to the output schema format
        final_rows = []
        for norm_out, cluster in groups.items():
            first_run = cluster[0]

            # Extract run IDs and sort them numerically if possible
            run_ids = []
            for r in cluster:
                try:
                    run_ids.append(int(r["Run"]))
                except ValueError:
                    run_ids.append(r["Run"])
            run_ids = sorted(run_ids, key=lambda x: (isinstance(x, str), x))

            final_rows.append(
                {
                    "Model": first_run.get("Model", ""),
                    "Thinking": first_run.get("Thinking", ""),
                    "QID": first_run.get("QID", ""),
                    "Query": first_run.get("Query", ""),
                    "Group Size": len(cluster),
                    "Representative Output": first_run.get("Response", ""),
                    "Reasoning": first_run.get("Reasoning", ""),
                    "LLM Merged": cluster[0].get("_llm_merged", False),
                    "Runs": ", ".join(str(x) for x in run_ids),
                }
            )

        # Sort final rows by group size (descending)
        final_rows.sort(key=lambda x: x["Group Size"], reverse=True)
        return final_rows

    def _apply_llm_fallback(
        self, groups: dict[str, list[dict]], grammar: str
    ) -> dict[str, list[dict]]:
        """Find singletons and try to merge them into larger groups using the LLM."""

        if self.llm_grouper is None:
            return groups

        # Separate into small groups (size <= threshold) and core groups (size > threshold)
        threshold = self.config.llm_fallback_max_group_size
        small_groups = {k: v for k, v in groups.items() if len(v) <= threshold}
        core_groups = {k: v for k, v in groups.items() if len(v) > threshold}

        # If everything is a small group, treat the first one as a core group
        if not core_groups and small_groups:
            first_key = list(small_groups.keys())[0]
            core_groups[first_key] = small_groups.pop(first_key)

        for small_norm, small_cluster in small_groups.items():
            small_run = small_cluster[0]
            query_text = small_run.get("Query", "")
            small_out = small_run.get("Response", "")

            merged = False
            for core_norm, core_cluster in core_groups.items():
                core_out = core_cluster[0].get("Response", "")

                # Ask LLM if they are equivalent
                if self.llm_grouper.is_equivalent(
                    query_text, small_out, core_out, grammar
                ):
                    logger.debug(
                        "LLM merged small group into core group for query %s", small_run.get("QID", "unknown")
                    )
                    # Mark all as merged for reporting
                    for r in small_cluster:
                        r["_llm_merged"] = True
                    core_cluster.extend(small_cluster)
                    merged = True
                    break

            if not merged:
                # Keep it as a small group if no match found
                core_groups[small_norm] = small_cluster

        return core_groups

    def _save_grouped_csv(self, out_path: Path, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        fieldnames = [
            "Model",
            "Thinking",
            "QID",
            "Query",
            "Group Size",
            "Representative Output",
            "Reasoning",
            "LLM Merged",
            "Runs",
        ]
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
