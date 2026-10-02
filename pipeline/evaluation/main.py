"""CLI entry point for the Evaluation Module.

Usage::

    python -m pipeline.evaluation.main --config evaluation_config.json --grouping-dir outputs/grouping/011026_011026_0001
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from pipeline.clients.ollama_client import OllamaClient
from pipeline.evaluation.config import EvaluationConfig
from pipeline.evaluation.ground_truth import GroundTruthStore
from pipeline.evaluation.runner import EvaluationRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Suppress excessive HTTP request logs from the underlying Ollama client
logging.getLogger("httpx").setLevel(logging.WARNING)


def main(config_path: str, grouping_dir: str) -> None:
    """Load config, prepare ground truth store, and run the evaluation."""
    grouping_path = Path(grouping_dir)
    if not grouping_path.exists() or not grouping_path.is_dir():
        logger.error("Grouping directory not found: %s", grouping_dir)
        sys.exit(1)

    config = EvaluationConfig.from_json(config_path)
    logger.info("Configuration loaded from %s", config_path)

    # Load ground truth from both datasets
    ground_truth = GroundTruthStore(
        ambrosia_path=config.dataset_paths.ambrosia,
        grailqa_path=config.dataset_paths.grailqa,
        ambrosia_qid_prefix=config.ambrosia_qid_prefix,
    )

    # Prepare Ollama client
    client = OllamaClient(
        host=config.ollama_host,
        max_retries=config.max_retries,
        wait_seconds=config.retry_wait_seconds,
    )

    # Run evaluation
    runner = EvaluationRunner(
        config=config,
        client=client,
        ground_truth=ground_truth,
        prompts_dir=Path(config.prompts_dir),
        grouping_dir=grouping_path,
    )
    output_dir = runner.run()
    logger.info("Evaluation successfully saved to: %s", output_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="TLNCSG Evaluation Module — LLM-as-a-judge for grouped outputs"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="evaluation_config.json",
        help="Path to the evaluation configuration JSON file",
    )
    parser.add_argument(
        "--grouping-dir",
        type=str,
        required=True,
        help="Path to the grouping output directory (e.g. outputs/grouping/011026_011026_0001)",
    )
    args = parser.parse_args()
    main(args.config, args.grouping_dir)
