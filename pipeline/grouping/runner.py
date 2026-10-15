"""Runner for the Grouping Module."""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path
from typing import Any

from .config import GroupingConfig
from .llm_grouper import LLMGrouper
from .normalizers import breakdown_key, encode_breakdown, normalize_output, output_key

logger = logging.getLogger(__name__)

GROUPED_COLUMNS = [
    "QID",
    "Query",
    "Output Key",
    "Group Size",
    "Run Breakdown",
    "Representative Output",
    "Reasoning",
    "LLM Merged",
]


def _parse_run(run: str) -> int | str:
    try:
        return int(run)
    except ValueError:
        return run


def _run_sort_key(row: dict) -> tuple:
    """Deterministic order of runs, so the group representative is stable across reruns."""
    run = _parse_run(row.get("Run", ""))
    return (
        row["_model_dir"],
        str(row.get("Thinking", "")).lower() == "true",
        isinstance(run, str),
        run,
    )


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")


class GroupingRunner:
    """Orchestrates reading Execution output, grouping, and saving grouped CSVs.

    Groups pool the runs of every model and thinking mode for the same
    (grammar, query), so each distinct answer is reviewed once. The Run Breakdown
    column keeps track of which model/mode produced which runs.
    """

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

        # Traverse: GRAMMAR / model / Q1.csv, pooling all models per query
        for grammar_dir in (d for d in self.execution_dir.iterdir() if d.is_dir()):
            grammar = grammar_dir.name
            out_grammar = output_root / grammar
            out_grammar.mkdir(parents=True, exist_ok=True)

            runs_by_qid = self._load_runs_by_qid(grammar_dir)

            for qid, runs in runs_by_qid.items():
                total_files += 1
                grouped_rows = self._process_query_runs(runs, grammar)

                total_rows_before += sum(row["Group Size"] for row in grouped_rows)
                total_rows_after += len(grouped_rows)

                out_csv = out_grammar / f"{_safe_name(qid)}_grouped.csv"
                self._save_grouped_csv(out_csv, grouped_rows)

        logger.info(
            "Grouping complete. Processed %d queries. Reduced %d rows down to %d groups.",
            total_files,
            total_rows_before,
            total_rows_after,
        )
        return output_root

    @staticmethod
    def _load_runs_by_qid(grammar_dir: Path) -> dict[str, list[dict]]:
        """Reads every model's QX.csv / QX-R.csv in a grammar and buckets the runs by QID."""
        runs_by_qid: dict[str, list[dict]] = {}
        for model_dir in sorted(d for d in grammar_dir.iterdir() if d.is_dir()):
            for csv_file in sorted(model_dir.glob("*.csv")):
                if "summary" in csv_file.name.lower():
                    continue  # Skip only summary files
                with open(csv_file, "r", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        row["_model_dir"] = model_dir.name
                        runs_by_qid.setdefault(row.get("QID", ""), []).append(row)
        return runs_by_qid

    def _process_query_runs(self, runs: list[dict], grammar: str) -> list[dict[str, Any]]:
        """Groups all runs (every model and mode) of one query and returns grouped rows."""
        if not runs:
            return []

        runs = sorted(runs, key=_run_sort_key)

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

            breakdown: dict[str, list] = {}
            for r in sorted(cluster, key=_run_sort_key):
                key = breakdown_key(r["_model_dir"], r.get("Thinking", ""))
                breakdown.setdefault(key, []).append(_parse_run(r.get("Run", "")))

            final_rows.append(
                {
                    "QID": first_run.get("QID", ""),
                    "Query": first_run.get("Query", ""),
                    "Output Key": output_key(grammar, first_run.get("QID", ""), norm_out),
                    "Group Size": len(cluster),
                    "Run Breakdown": encode_breakdown(breakdown),
                    "Representative Output": first_run.get("Response", ""),
                    "Reasoning": first_run.get("Reasoning", ""),
                    "LLM Merged": any(r.get("_llm_merged", False) for r in cluster),
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
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=GROUPED_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
