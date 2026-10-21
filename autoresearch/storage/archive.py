"""Run folders: the timestamp that names the current run and the archive of previous runs."""
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import List

from autoresearch.core.constants import AUTORESEARCH_DIR
from autoresearch.core.experiment import Experiment

logger = logging.getLogger(__name__)

ARCHIVE_DIR = AUTORESEARCH_DIR / "archive"


def run_timestamp(history: List[Experiment]) -> str:
    """Timestamp of the run in the history, so a resumed run keeps writing to its folder, or a new one."""
    if history:
        first = history[0]
        for part in (first.results_file or "").replace("\\", "/").split("/"):
            if part.startswith("run_"):
                return part[4:]
        try:
            return datetime.fromisoformat(first.timestamp).strftime("%Y%m%d_%H%M%S")
        except ValueError:
            pass
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def archive_previous_run(log_path: Path, prompts_dir: Path) -> None:
    """Moves the experiments log and champion prompts of the previous run into its archive folder."""
    history = []
    if log_path.exists():
        try:
            history = [Experiment.from_dict(item) for item in json.loads(log_path.read_text(encoding="utf-8"))]
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass

    # A run stopped before the baseline was logged has nothing to keep. Its folder can't be known from an
    # empty history, so archiving it under the current time would share the folder with the new run.
    if log_path.exists() and not history:
        log_path.unlink()

    files = [log_path] if log_path.exists() else []
    if prompts_dir.exists():
        files += [path for path in prompts_dir.iterdir() if path.is_file()]
    if not files:
        logger.info("No previous run files found to archive. Starting fresh.")
        return

    archive_dir = ARCHIVE_DIR / f"run_{run_timestamp(history)}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    for path in files:
        # The run folder already holds this run's log and results; a file with the same name is replaced
        shutil.move(str(path), str(archive_dir / path.name))
    logger.info("Archived previous run files to: %s", archive_dir)
