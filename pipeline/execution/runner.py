"""ExecutionRunner — orchestrates the full execution loop."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from pipeline.clients import OllamaClient
from pipeline.datasets import Query
from pipeline.execution.config import ExecutionConfig, ModelConfig

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# CSV column definitions
# --------------------------------------------------------------------------

PER_QUERY_COLUMNS = [
    "Run",
    "Model",
    "Thinking",
    "QID",
    "Query",
    "Prompt Tokens",
    "Completion Tokens",
    "Inference Time (s)",
    "Response",
    "Reasoning",
    "Timestamp",
    "Error",
]

SUMMARY_PER_QUERY_COLUMNS = [
    "QID",
    "Query",
    "Thinking",
    "Runs",
    "Mean Inference Time (s)",
    "Std Inference Time (s)",
    "Mean Prompt Tokens",
    "Mean Completion Tokens",
]

SUMMARY_COLUMNS = [
    "Thinking",
    "Total Queries",
    "Total Runs",
    "Mean Inference Time (s)",
    "Std Inference Time (s)",
    "Mean Prompt Tokens",
    "Mean Completion Tokens",
]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _safe_name(name: str) -> str:
    """Build a filesystem-safe name from an arbitrary string."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")


def _load_prompt(prompt_path: str) -> str:
    """Read a system prompt file. Paths are relative to the project root."""
    path = Path(prompt_path)
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def _query_csv_path(model_dir: Path, query_id: str, thinking: bool) -> Path:
    """Return the CSV path for a specific query + thinking-mode combination."""
    safe_id = _safe_name(query_id)
    suffix = "-R" if thinking else ""
    return model_dir / f"{safe_id}{suffix}.csv"


def _next_execution_id(output_dir: Path) -> str:
    """Scan *output_dir* for existing 4-digit IDs and return the next one."""
    existing_ids: list[int] = []
    if output_dir.exists():
        for child in output_dir.iterdir():
            if child.is_dir():
                # Extract trailing 4-digit ID from folder name
                match = re.search(r"_(\d{4})$", child.name)
                if match:
                    existing_ids.append(int(match.group(1)))
    next_id = max(existing_ids, default=0) + 1
    return f"{next_id:04d}"


# --------------------------------------------------------------------------
# ExecutionRunner
# --------------------------------------------------------------------------


class ExecutionRunner:
    """Orchestrates the Execution Module loop:
    ``Grammar → Model → ThinkingMode → Query → Repetition``.
    """

    def __init__(
        self,
        config: ExecutionConfig,
        client: OllamaClient,
        queries: list[Query],
    ):
        self.config = config
        self.client = client
        self.queries = queries

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> Path:
        """Run the full execution pipeline.

        Returns:
            The final output directory path.
        """
        start_time = datetime.now()
        output_root_parent = Path(self.config.output_dir)
        output_root_parent.mkdir(parents=True, exist_ok=True)

        execution_id = _next_execution_id(output_root_parent)
        start_stamp = start_time.strftime("%d%m%y")
        run_dir_name = f"{start_stamp}_{execution_id}"
        run_dir = output_root_parent / run_dir_name
        run_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "=== Execution started: %s (%d queries, %d runs/model) ===",
            run_dir_name,
            len(self.queries),
            self.config.runs_per_model,
        )

        enabled_models = self.config.enabled_models

        # Collect the union of all grammar names across enabled models
        all_grammars: set[str] = set()
        for model in enabled_models:
            all_grammars.update(model.grammars.keys())

        for grammar_name in sorted(all_grammars):
            grammar_dir = run_dir / grammar_name
            grammar_dir.mkdir(parents=True, exist_ok=True)

            # Models configured for this grammar
            grammar_models = [
                m for m in enabled_models if grammar_name in m.grammars
            ]

            logger.info(
                "--- Grammar: %s (%d model(s)) ---",
                grammar_name,
                len(grammar_models),
            )

            for model_idx, model_cfg in enumerate(grammar_models, 1):
                self._run_model_on_grammar(
                    grammar_name=grammar_name,
                    grammar_dir=grammar_dir,
                    model_cfg=model_cfg,
                    model_idx=model_idx,
                    total_models=len(grammar_models),
                )

        # ---- Finalize ----
        end_time = datetime.now()
        self._save_manifest(run_dir, execution_id, start_time, end_time)

        # Rename directory to include end timestamp
        end_stamp = end_time.strftime("%d%m%y")
        final_name = f"{start_stamp}_{end_stamp}_{execution_id}"
        final_dir = output_root_parent / final_name
        run_dir.rename(final_dir)

        logger.info("=== Execution finished: %s ===", final_name)
        return final_dir

    # ------------------------------------------------------------------
    # Per-model-on-grammar logic
    # ------------------------------------------------------------------

    def _run_model_on_grammar(
        self,
        grammar_name: str,
        grammar_dir: Path,
        model_cfg: ModelConfig,
        model_idx: int,
        total_models: int,
    ) -> None:
        """Process one model against one grammar (IR)."""
        prompt_path = model_cfg.grammars[grammar_name]
        system_prompt = _load_prompt(prompt_path)

        model_dir = grammar_dir / _safe_name(model_cfg.name)
        model_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "  [%d/%d] Model: %s (%s)",
            model_idx,
            total_models,
            model_cfg.display_name,
            model_cfg.name,
        )

        # Warmup
        self.client.warmup(
            model=model_cfg.name,
            system_prompt=system_prompt,
            options=self.config.ollama_options,
            temperature=model_cfg.temperature,
        )

        # Determine thinking modes
        modes = [False]
        if model_cfg.supports_thinking:
            modes.append(True)

        all_records: list[dict] = []

        for thinking in modes:
            mode_label = "Thinking" if thinking else "Standard"
            logger.info("    Mode: %s", mode_label)

            for q_idx, query in enumerate(self.queries, 1):
                csv_path = _query_csv_path(model_dir, query.id, thinking)

                # ---- Resumability: skip completed queries ----
                if csv_path.exists():
                    logger.info(
                        "      [%d/%d] %s — already completed, skipping",
                        q_idx,
                        len(self.queries),
                        query.id,
                    )
                    existing = pd.read_csv(csv_path, encoding="utf-8")
                    all_records.extend(existing.to_dict("records"))
                    continue

                if q_idx % 10 == 1 or q_idx == len(self.queries):
                    logger.info(
                        "      [%d/%d] %s",
                        q_idx,
                        len(self.queries),
                        query.id,
                    )

                records = self._run_query(
                    model_cfg=model_cfg,
                    query=query,
                    system_prompt=system_prompt,
                    thinking=thinking,
                )

                # Save per-query CSV
                pd.DataFrame(records, columns=PER_QUERY_COLUMNS).to_csv(
                    csv_path, index=False, encoding="utf-8"
                )
                all_records.extend(records)

        # ---- Summary CSVs ----
        self._save_summaries(model_dir, all_records)

    # ------------------------------------------------------------------
    # Per-query execution
    # ------------------------------------------------------------------

    def _run_query(
        self,
        model_cfg: ModelConfig,
        query: Query,
        system_prompt: str,
        thinking: bool,
    ) -> list[dict]:
        """Execute all repetitions of a single query and return records."""
        records: list[dict] = []

        for run in range(1, self.config.runs_per_model + 1):
            try:
                content, reasoning, inference_s, meta = (
                    self.client.chat_with_metadata(
                        model=model_cfg.name,
                        query=query.text,
                        system_prompt=system_prompt,
                        options=self.config.ollama_options,
                        temperature=model_cfg.temperature,
                        thinking=thinking,
                    )
                )
                error = None
            except Exception as e:
                logger.error(
                    "Unexpected error (model=%s, query=%s, run=%d): %s",
                    model_cfg.name,
                    query.id,
                    run,
                    e,
                )
                content, reasoning, inference_s, meta = "", None, 0.0, {
                    "prompt_eval_count": 0,
                    "eval_count": 0,
                }
                error = str(e)

            records.append(
                {
                    "Run": run,
                    "Model": model_cfg.name,
                    "Thinking": thinking,
                    "QID": query.id,
                    "Query": query.text,
                    "Prompt Tokens": meta.get("prompt_eval_count", 0),
                    "Completion Tokens": meta.get("eval_count", 0),
                    "Inference Time (s)": round(inference_s, 6),
                    "Response": content,
                    "Reasoning": reasoning or "",
                    "Timestamp": datetime.now().isoformat(),
                    "Error": error,
                }
            )

        return records

    # ------------------------------------------------------------------
    # Summary generation
    # ------------------------------------------------------------------

    @staticmethod
    def _save_summaries(model_dir: Path, records: list[dict]) -> None:
        """Generate and save summary CSVs from execution records."""
        if not records:
            return

        df = pd.DataFrame(records)

        # ---- Per-query summary ----
        per_query = (
            df.groupby(["QID", "Query", "Thinking"])
            .agg(
                Runs=("Run", "count"),
                **{
                    "Mean Inference Time (s)": ("Inference Time (s)", "mean"),
                    "Std Inference Time (s)": ("Inference Time (s)", "std"),
                    "Mean Prompt Tokens": ("Prompt Tokens", "mean"),
                    "Mean Completion Tokens": ("Completion Tokens", "mean"),
                },
            )
            .reset_index()
        )
        per_query.to_csv(
            model_dir / "summary_per_query.csv",
            index=False,
            encoding="utf-8",
        )

        # ---- Overall summary (one row per thinking mode) ----
        overall = (
            df.groupby("Thinking")
            .agg(
                **{
                    "Total Queries": ("QID", "nunique"),
                    "Total Runs": ("Run", "count"),
                    "Mean Inference Time (s)": ("Inference Time (s)", "mean"),
                    "Std Inference Time (s)": ("Inference Time (s)", "std"),
                    "Mean Prompt Tokens": ("Prompt Tokens", "mean"),
                    "Mean Completion Tokens": ("Completion Tokens", "mean"),
                },
            )
            .reset_index()
        )
        overall.to_csv(
            model_dir / "summary.csv", index=False, encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # Manifest
    # ------------------------------------------------------------------

    def _save_manifest(
        self,
        run_dir: Path,
        execution_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        """Write a JSON manifest capturing execution metadata and config."""
        manifest = {
            "execution_id": execution_id,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": round(
                (end_time - start_time).total_seconds(), 2
            ),
            "n_queries": len(self.queries),
            "config": self.config.to_dict(),
        }
        manifest_path = run_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        logger.info("Manifest saved: %s", manifest_path)
