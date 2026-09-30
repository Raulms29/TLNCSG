"""CLI entry point for the Execution Module.

Usage::

    python -m pipeline.execution.main --config execution_config.json
"""

from __future__ import annotations

import argparse
import logging
import sys

from pipeline.clients import OllamaClient
from pipeline.datasets import AmbrosiaDataset, GrailQADataset, QueryDataset
from pipeline.execution.config import ExecutionConfig
from pipeline.execution.runner import ExecutionRunner

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataset factory
# ---------------------------------------------------------------------------

DATASET_LOADERS: dict[str, type[QueryDataset]] = {
    "grailqa": GrailQADataset,
    "ambrosia": AmbrosiaDataset,
}


def _load_queries(config: ExecutionConfig):
    """Instantiate the right dataset loader and sample queries."""
    ds_type = config.dataset.type.lower()
    loader_cls = DATASET_LOADERS.get(ds_type)
    if loader_cls is None:
        raise ValueError(
            f"Unknown dataset type '{ds_type}'. "
            f"Supported: {', '.join(DATASET_LOADERS)}"
        )

    dataset = loader_cls(config.dataset.path)
    queries = dataset.sample(
        n=config.dataset.n_queries, seed=config.dataset.seed
    )
    logger.info(
        "Loaded %d queries from %s dataset (%s)",
        len(queries),
        ds_type,
        config.dataset.path,
    )
    return queries


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(config_path: str) -> None:
    """Load config, prepare queries, and run the execution pipeline."""
    config = ExecutionConfig.from_json(config_path)
    logger.info("Configuration loaded from %s", config_path)

    # ---- Load and sample queries ----
    queries = _load_queries(config)

    # ---- Create Ollama client ----
    client = OllamaClient(
        host=config.ollama_host,
        max_retries=config.max_retries,
        wait_seconds=config.retry_wait_seconds,
    )

    # ---- Run ----
    runner = ExecutionRunner(config=config, client=client, queries=queries)
    output_dir = runner.run()
    logger.info("All results saved to: %s", output_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="TLNCSG Execution Module — run LLM translations"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="execution_config.json",
        help="Path to the execution configuration JSON file",
    )
    args = parser.parse_args()
    main(args.config)
