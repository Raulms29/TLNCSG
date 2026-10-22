"""Entry point of the autoresearch loop: reads the configuration, builds the services and runs the loop."""
import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict

# Bootstrap: Add project root to path so absolute imports work
sys.path.append(str(Path(__file__).resolve().parent.parent))

from project_config import get_ollama_host
from autoresearch.core.constants import AUTORESEARCH_DIR, PROJECT_ROOT
from autoresearch.loop import OptimizationLoop
from autoresearch.services import EvaluatorAgent, GeneratorClient, OptimizerAgent, ValidationRunner
from autoresearch.storage import ExperimentLogger, PromptStore
from autoresearch.storage.archive import ARCHIVE_DIR, archive_previous_run, run_timestamp

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=DATE_FORMAT,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Suppress excessive HTTP request logs from the underlying Ollama client
logging.getLogger("httpx").setLevel(logging.WARNING)


def resolve(path: str) -> Path:
    """Resolves a config path relative to the project root, like the pipeline configs, whatever the working directory."""
    return (PROJECT_ROOT / path).resolve()


def add_file_logging(timestamp: str) -> None:
    """Writes the log of this run to its archive folder, next to the validation results."""
    run_dir = ARCHIVE_DIR / f"run_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(run_dir / "autoresearch.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logging.getLogger().addHandler(file_handler)
    logger.info("Logging to %s", run_dir / "autoresearch.log")


def build_runner(config: Dict[str, Any], ollama_url: str) -> ValidationRunner:
    """The generator and the judge, and the runner that evaluates a prompt with them."""
    generator_cfg, evaluator_cfg = config["generator"], config["evaluator"]
    generator = GeneratorClient(
        ollama_url=ollama_url,
        model_name=generator_cfg["model"],
        temperature=generator_cfg["temperature"],
        num_ctx=generator_cfg["num_ctx"],
        num_predict=generator_cfg["num_predict"],
        thinking=generator_cfg.get("thinking", False),
    )
    evaluator = EvaluatorAgent(
        ollama_url=ollama_url,
        model_name=evaluator_cfg["model"],
        temperature=evaluator_cfg["temperature"],
        num_ctx=evaluator_cfg["num_ctx"],
        num_predict=evaluator_cfg["num_predict"],
        thinking=evaluator_cfg.get("thinking", False),
        fallback_model=evaluator_cfg.get("fallback_model"),
        prompt_path=str(resolve(config["paths"]["evaluator_prompt"])),
    )
    return ValidationRunner(
        ground_truths_path=str(resolve(config["paths"]["ground_truths"])),
        generator=generator,
        evaluator=evaluator,
        runs_per_query=generator_cfg.get("runs_per_query", 1),
        pass_threshold=config["acceptance"]["pass_threshold"],
        parallel_requests=config["loop_settings"].get("parallel_requests", 1),
    )


def build_optimizer(config: Dict[str, Any], ollama_url: str) -> OptimizerAgent:
    optimizer_cfg = config["optimizer"]
    return OptimizerAgent(
        ollama_url=ollama_url,
        model_name=optimizer_cfg["model"],
        temperature=optimizer_cfg["temperature"],
        num_ctx=optimizer_cfg["num_ctx"],
        num_predict=optimizer_cfg["num_predict"],
        thinking=optimizer_cfg.get("thinking", False),
        memory_size=optimizer_cfg["failure_memory_size"],
        prompt_path=str(resolve(config["paths"]["optimizer_prompt"])),
    )


def main():
    parser = argparse.ArgumentParser(description="Autoresearch evaluation loop.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Start from scratch by archiving the current experiments log and prompts into an archive folder.",
    )
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "autoresearch_config.json"),
        help="Path to the configuration file (default: autoresearch_config.json).",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        logger.error("Configuration file not found at %s", config_path)
        sys.exit(1)
    config = json.loads(config_path.read_text(encoding="utf-8"))

    log_path = AUTORESEARCH_DIR / "experiments.json"
    prompts_dir = resolve(config["paths"]["prompts_dir"])
    if args.reset:
        archive_previous_run(log_path, prompts_dir)

    experiments = ExperimentLogger(str(log_path))
    timestamp = run_timestamp(experiments.load_history())
    add_file_logging(timestamp)

    ollama_url = get_ollama_host()
    OptimizationLoop(
        config=config,
        runner=build_runner(config, ollama_url),
        optimizer=build_optimizer(config, ollama_url),
        prompt_store=PromptStore(str(resolve(config["paths"]["generator_prompt"])), str(prompts_dir)),
        experiments=experiments,
        run_timestamp=timestamp,
    ).run()


if __name__ == "__main__":
    main()
