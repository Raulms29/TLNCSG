"""CLI entry point for the Metrics Module.

Usage::

    python -m pipeline.metrics.main --config metrics_config.json --run-dir outputs/review/300926_300926_0001
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from pipeline.evaluation.ground_truth import GroundTruthStore
from .config import MetricsConfig
from .unroller import Unroller
from .exporter import MetricsExporter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main(config_path: str, run_dir_path: str) -> None:
    """Load config, process CSVs, and export metrics."""
    run_dir = Path(run_dir_path)
    if not run_dir.exists() or not run_dir.is_dir():
        logger.error("Run directory not found: %s", run_dir_path)
        sys.exit(1)

    config = MetricsConfig.from_json(config_path)
    logger.info("Configuration loaded from %s", config_path)
    
    # Load ground truth
    gt_store = GroundTruthStore(
        ambrosia_path=config.dataset_paths.ambrosia,
        grailqa_path=config.dataset_paths.grailqa,
    )

    unroller = Unroller(config, gt_store)
    exporter = MetricsExporter(config)

    logger.info("Processing run: %s", run_dir.name)
    query_metrics, error_distributions = unroller.unroll_run(run_dir)
    
    out_dir = exporter.export(run_dir.name, query_metrics, error_distributions)
    logger.info("Metrics successfully saved to: %s", out_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="TLNCSG Metrics Module — compute Pass@k and statistical significance"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="metrics_config.json",
        help="Path to the metrics configuration JSON file",
    )
    parser.add_argument(
        "--run-dir",
        type=str,
        required=True,
        help="Path to the review output directory (e.g. outputs/review/300926_300926_0001)",
    )
    args = parser.parse_args()
    main(args.config, args.run_dir)
