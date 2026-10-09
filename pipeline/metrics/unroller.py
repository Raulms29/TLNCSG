"""Unrolls reviewed outputs to compute query-level metrics."""

from __future__ import annotations

import csv
import logging
from pathlib import Path

import pandas as pd

from pipeline.evaluation.ground_truth import GroundTruthStore
from .config import MetricsConfig
from .stats import calc_pass_at_k, calc_pass_power_k

logger = logging.getLogger(__name__)

class Unroller:
    """Unrolls reviewed outputs, merges with execution metrics, and computes query-level stats."""
    
    def __init__(self, config: MetricsConfig, gt_store: GroundTruthStore):
        self.config = config
        self.gt_store = gt_store
        
    def unroll_run(self, run_dir: Path) -> tuple[list[dict], list[dict]]:
        """
        Process a single run directory (e.g. outputs/review/300926_300926_0001).
        Returns:
            query_metrics: list of dicts for query_level_metrics.csv
            error_distributions: list of dicts for error_distribution.csv
        """
        run_id = run_dir.name
        exec_run_dir = Path("outputs/execution") / run_id
        
        query_metrics = []
        error_distributions = []
        
        for grammar_dir in (d for d in run_dir.iterdir() if d.is_dir()):
            grammar = grammar_dir.name
            
            for model_dir in (d for d in grammar_dir.iterdir() if d.is_dir()):
                model_name = model_dir.name
                
                time_tokens_map = self._load_execution_summaries(exec_run_dir, grammar, model_name)
                        
                for csv_file in model_dir.glob("*_reviewed.csv"):
                    metrics, errors = self._process_reviewed_file(csv_file, grammar, model_name, time_tokens_map)
                    if metrics:
                        query_metrics.append(metrics)
                    error_distributions.extend(errors)
                    
        return query_metrics, error_distributions

    def _load_execution_summaries(self, exec_run_dir: Path, grammar: str, model_name: str) -> dict[tuple[str, bool], dict]:
        """Loads inference time and tokens from the execution module's summary."""
        summary_csv = exec_run_dir / grammar / model_name / "summary_per_query.csv"
        time_tokens_map = {}
        
        if summary_csv.exists():
            try:
                df = pd.read_csv(summary_csv, encoding="utf-8")
                for _, row in df.iterrows():
                    qid = str(row["QID"])
                    # Default to False if the column is missing or unparseable
                    thinking_str = str(row.get("Thinking", "False")).strip().lower()
                    thinking = thinking_str == "true"
                    
                    time_tokens_map[(qid, thinking)] = {
                        "Inference Time (s)": row.get("Mean Inference Time (s)", 0.0),
                        "Completion Tokens": row.get("Mean Completion Tokens", 0.0)
                    }
            except Exception as e:
                logger.warning("Failed to read %s: %s", summary_csv, e)
                
        return time_tokens_map

    def _process_reviewed_file(self, csv_path: Path, grammar: str, model: str, time_tokens_map: dict) -> tuple[dict, list]:
        """Reads a specific query's reviewed CSV and returns its metrics and errors."""
        rows = self._read_csv_rows(csv_path)
        if not rows:
            return {}, []
            
        qid = rows[0].get("QID", "")
        thinking = str(rows[0].get("Thinking", "False")).strip().lower() == "true"
        
        # Adjust model name for downstream aggregations
        if thinking:
            model = f"{model} (Thinking)"
            
        n, c, error_counts = self._aggregate_counts(rows)
        if n == 0:
            return {}, []
            
        success_rate = c / n
        h_coverage = self._calculate_hypothesis_coverage(qid, rows, n)
        
        tt = time_tokens_map.get((qid, thinking), {})
        inf_time = tt.get("Inference Time (s)", 0.0)
        tokens = tt.get("Completion Tokens", 0.0)
        
        metrics = {
            "QID": qid,
            "Grammar": grammar,
            "Model": model,
            "Success Rate": success_rate,
            "Hypothesis Coverage": h_coverage,
            "Inference Time (s)": inf_time,
            "Completion Tokens": tokens
        }
        
        for k in self.config.k_values:
            metrics[f"Pass@{k}"] = calc_pass_at_k(n, c, k)
            metrics[f"Pass^{k}"] = calc_pass_power_k(n, c, k)
            
        errors = self._format_error_distributions(grammar, model, error_counts)
        return metrics, errors

    def _read_csv_rows(self, csv_path: Path) -> list[dict]:
        """Helper to read CSV into a list of dicts."""
        rows = []
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        return rows

    def _aggregate_counts(self, rows: list[dict]) -> tuple[int, int, dict[str, int]]:
        """Extract total attempts (n), correct attempts (c), and errors."""
        n = 0
        c = 0
        error_counts = {}
        
        for row in rows:
            try:
                group_size = int(row.get("Group Size", 0))
            except ValueError:
                group_size = 0
                
            n += group_size
            
            is_correct = str(row.get("Human Correct", "")).strip().lower() == "true"
            if is_correct:
                c += group_size
            else:
                err = row.get("Error Category", "Unknown")
                if err:
                    error_counts[err] = error_counts.get(err, 0) + group_size
                    
        return n, c, error_counts

    def _calculate_hypothesis_coverage(self, qid: str, rows: list[dict], n: int) -> float:
        """Calculates the average hypothesis coverage per run across all n runs."""
        gt = self.gt_store.get(qid)
        total_gt_hypotheses = gt.num_interpretations if gt else 1
        
        total_covered_hypotheses = 0.0
        for row in rows:
            is_correct = str(row.get("Human Correct", "")).strip().lower() == "true"
            if is_correct:
                try:
                    group_size = int(row.get("Group Size", 0))
                    h = float(row.get("Human Hypotheses Covered", 0))
                    total_covered_hypotheses += h * group_size
                except ValueError:
                    pass
                    
        if n * total_gt_hypotheses > 0:
            return total_covered_hypotheses / (n * total_gt_hypotheses)
        return 0.0

    def _format_error_distributions(self, grammar: str, model: str, error_counts: dict[str, int]) -> list[dict]:
        """Formats the collected errors for the exporter."""
        errors = []
        for err_cat, count in error_counts.items():
            errors.append({
                "Grammar": grammar,
                "Model": model,
                "Error Category": err_cat,
                "Count": count
            })
        return errors
