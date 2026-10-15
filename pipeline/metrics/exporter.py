"""Export functionality for the Metrics Module."""

from __future__ import annotations

import csv
import logging
from pathlib import Path

import pandas as pd
import numpy as np

from .config import MetricsConfig
from .stats import calculate_mcnemar, calculate_wilcoxon

logger = logging.getLogger(__name__)

class MetricsExporter:
    """Aggregates summaries, runs statistical tests, and writes outputs."""
    
    def __init__(self, config: MetricsConfig):
        self.config = config
        
    def export(self, run_dir_name: str, query_metrics: list[dict], error_distributions: list[dict]) -> Path:
        """Export all computed metrics to their respective CSV files."""
        out_dir = Path(self.config.output_dir) / run_dir_name
        out_dir.mkdir(parents=True, exist_ok=True)
        
        if not query_metrics:
            logger.warning("No metrics to export.")
            return out_dir
            
        df_queries = pd.DataFrame(query_metrics)
        
        self._export_query_level(df_queries, out_dir)
        self._export_model_summary(df_queries, out_dir)
        self._export_error_distribution(error_distributions, out_dir)
        self._export_significance_tests(df_queries, out_dir)
            
        return out_dir

    def _export_query_level(self, df_queries: pd.DataFrame, out_dir: Path) -> None:
        """Export granular query-level metrics."""
        path = out_dir / "query_level_metrics.csv"
        df_queries.to_csv(path, index=False, encoding="utf-8")
        logger.info("Exported query_level_metrics.csv")

    def _export_model_summary(self, df_queries: pd.DataFrame, out_dir: Path) -> None:
        """Export macro-averaged metrics grouped by model and grammar."""
        cols_to_mean = [
            "Success Rate", "Hypothesis Coverage", "Inference Time (s)", "Completion Tokens"
        ]
        for k in self.config.k_values:
            cols_to_mean.extend([f"Pass@{k}", f"Pass^{k}"])
            
        summary_df = df_queries.groupby(["Grammar", "Model"])[cols_to_mean].mean().reset_index()
        
        rename_map = {
            c: f"Avg {c}" if c in ["Success Rate", "Hypothesis Coverage", "Inference Time (s)", "Completion Tokens"] else c
            for c in cols_to_mean
        }
        summary_df = summary_df.rename(columns=rename_map)

        # Readable, fixed precision: rates with 4 decimals, time and tokens with 2
        # (padded, e.g. 1.0000). Only this file is formatted; query_level_metrics.csv
        # keeps full precision for analysis.
        for c in rename_map.values():
            fmt = "{:.2f}" if c in ("Avg Inference Time (s)", "Avg Completion Tokens") else "{:.4f}"
            summary_df[c] = summary_df[c].map(fmt.format)

        path = out_dir / "model_summary_metrics.csv"
        summary_df.to_csv(path, index=False, encoding="utf-8")
        logger.info("Exported model_summary_metrics.csv")

    def _export_error_distribution(self, error_distributions: list[dict], out_dir: Path) -> None:
        """Export the distribution and percentages of error categories.

        Always written (header only when there are no categorized errors), so every
        run folder has the same files for the analysis notebook.
        """
        columns = ["Grammar", "Model", "Error Category", "Count", "Percentage"]
        if error_distributions:
            df_err = pd.DataFrame(error_distributions)
            df_err = df_err.groupby(["Grammar", "Model", "Error Category"])["Count"].sum().reset_index()

            total_errors = df_err.groupby(["Grammar", "Model"])["Count"].transform("sum")
            df_err["Percentage"] = (df_err["Count"] / total_errors * 100).round(2)
        else:
            df_err = pd.DataFrame(columns=columns)
        
        path = out_dir / "error_distribution.csv"
        df_err.to_csv(path, index=False, encoding="utf-8")
        logger.info("Exported error_distribution.csv")

    def _export_significance_tests(self, df_queries: pd.DataFrame, out_dir: Path) -> None:
        """Export statistical comparisons between the baseline and other grammars."""
        # Always written (header only when no grammar pair could be compared)
        columns = [
            "Model", "Metric", f"Baseline ({self.config.reference_grammar})", "Comparison Grammar",
            "Test Used", "p-value", "Significant (p<0.05)",
        ]
        df_sig = pd.DataFrame(self._run_significance_tests(df_queries), columns=columns)
        path = out_dir / "significance_tests.csv"
        df_sig.to_csv(path, index=False, encoding="utf-8")
        logger.info("Exported significance_tests.csv")

    def _run_significance_tests(self, df: pd.DataFrame) -> list[dict]:
        """Compute McNemar and Wilcoxon statistical tests."""
        results = []
        models = df["Model"].unique()
        baseline_grammar = self.config.reference_grammar.lower()
        comparison_grammars = [g for g in df["Grammar"].unique() if g.lower() != baseline_grammar]
        
        for model in models:
            df_model = df[df["Model"] == model]
            df_base = df_model[df_model["Grammar"].str.lower() == baseline_grammar]
            
            if df_base.empty:
                continue
                
            for comp_grammar in comparison_grammars:
                df_comp = df_model[df_model["Grammar"] == comp_grammar]
                if df_comp.empty:
                    continue
                    
                merged = pd.merge(df_base, df_comp, on="QID", suffixes=("_base", "_comp"))
                if merged.empty:
                    continue
                    
                results.extend(self._compute_mcnemar_tests(model, baseline_grammar, comp_grammar, merged))
                results.extend(self._compute_wilcoxon_tests(model, baseline_grammar, comp_grammar, merged))
                    
        return results

    def _compute_mcnemar_tests(self, model: str, baseline: str, comp: str, merged: pd.DataFrame) -> list[dict]:
        """Run McNemar's test for binary Pass@30 limits."""
        y1 = (merged["Pass@30_base"] >= 0.99).astype(int).tolist()
        y2 = (merged["Pass@30_comp"] >= 0.99).astype(int).tolist()
        chi2, p_mcnemar = calculate_mcnemar(y1, y2)
        
        return [{
            "Model": model,
            "Metric": "Pass@30",
            f"Baseline ({self.config.reference_grammar})": baseline,
            "Comparison Grammar": comp,
            "Test Used": "McNemar",
            "p-value": round(p_mcnemar, 4),
            "Significant (p<0.05)": p_mcnemar < 0.05
        }]

    def _compute_wilcoxon_tests(self, model: str, baseline: str, comp: str, merged: pd.DataFrame) -> list[dict]:
        """Run Wilcoxon Signed-Rank test for continuous metrics."""
        results = []
        cont_metrics = ["Success Rate", "Hypothesis Coverage"] + [f"Pass^{k}" for k in self.config.k_values]
        
        for metric in cont_metrics:
            x = merged[f"{metric}_base"].tolist()
            y = merged[f"{metric}_comp"].tolist()
            
            stat, p_wilcox = calculate_wilcoxon(x, y)
            results.append({
                "Model": model,
                "Metric": metric,
                f"Baseline ({self.config.reference_grammar})": baseline,
                "Comparison Grammar": comp,
                "Test Used": "Wilcoxon",
                "p-value": round(p_wilcox, 4),
                "Significant (p<0.05)": p_wilcox < 0.05
            })
            
        return results
