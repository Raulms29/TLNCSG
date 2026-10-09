"""CLI entry point for the Grouping Module.

Usage::

    python -m pipeline.grouping.main --config grouping_config.json --execution-dir outputs/execution/300926_300926_0001
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from pipeline.clients.ollama_client import OllamaClient
from pipeline.grouping.config import GroupingConfig
from pipeline.grouping.llm_grouper import LLMGrouper
from pipeline.grouping.runner import GroupingRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Suppress excessive HTTP request logs from the underlying Ollama client
logging.getLogger("httpx").setLevel(logging.WARNING)


def main(config_path: str, execution_dir: str) -> None:
    """Load config, prepare LLM grouper, and run the pipeline."""
    exec_path = Path(execution_dir)
    if not exec_path.exists() or not exec_path.is_dir():
        logger.error("Execution directory not found: %s", execution_dir)
        sys.exit(1)

    config = GroupingConfig.from_json(config_path)
    logger.info("Configuration loaded from %s", config_path)

    # Prepare LLM client for fallback grouping
    llm_grouper = None
    if config.enable_llm_fallback:
        client = OllamaClient(
            host=config.ollama_host,
            max_retries=config.max_retries,
            wait_seconds=config.retry_wait_seconds,
        )
        # Load all grammar-specific system prompts dynamically
        prompts_dir = Path("prompts/grouping")
        system_prompts = {}
        for prompt_file in prompts_dir.glob("SYSTEM_PROMPT_GROUPER_*.prompt.md"):
            # Extract grammar name from filename (e.g. SYSTEM_PROMPT_GROUPER_SEMGIR.prompt.md -> semgir)
            grammar_part = prompt_file.name.replace("SYSTEM_PROMPT_GROUPER_", "").replace(".prompt.md", "")
            system_prompts[grammar_part.lower()] = prompt_file.read_text(encoding="utf-8")

        llm_grouper = LLMGrouper(client, config.grouper_model, system_prompts)

    # Run grouping
    runner = GroupingRunner(
        config=config, llm_grouper=llm_grouper, execution_dir=exec_path
    )
    output_dir = runner.run()
    logger.info("Grouping successfully saved to: %s", output_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="TLNCSG Grouping Module — collapse semantic LLM outputs"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="grouping_config.json",
        help="Path to the grouping configuration JSON file",
    )
    parser.add_argument(
        "--execution-dir",
        type=str,
        required=True,
        help="Path to the execution output directory (e.g. outputs/execution/300926_300926_0001)",
    )
    args = parser.parse_args()
    main(args.config, args.execution_dir)
