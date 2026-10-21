import json
from pathlib import Path
from typing import List, Optional
from autoresearch.core.experiment import Experiment


class ExperimentLogger:
    """
    Manages reading and writing optimization iteration data to experiments.json.
    """

    def __init__(self, log_path: str):
        self.log_path = Path(log_path)
        self._ensure_file()

    def _ensure_file(self):
        """Creates the experiments.json file with an empty list if it doesn't exist."""
        if not self.log_path.exists():
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)

    def load_history(self) -> List[Experiment]:
        """Loads and parses the list of experiments from experiments.json."""
        if not self.log_path.exists():
            return []
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [Experiment.from_dict(item) for item in data]
        except (json.JSONDecodeError, KeyError, TypeError):
            # Fallback for corrupted or legacy formats
            return []

    def log_experiment(self, experiment: Experiment):
        """Appends a new experiment to the log file."""
        history = self.load_history()
        history.append(experiment)

        # Serialize list of experiments
        serialized = [exp.to_dict() for exp in history]
        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(serialized, f, indent=2)

    def get_champion(self) -> Optional[Experiment]:
        """Returns the latest kept experiment (the current champion), or None if there is none."""
        kept = [exp for exp in self.load_history() if exp.status in ("CHAMPION_INIT", "KEEP")]
        return kept[-1] if kept else None

    def get_next_iteration_number(self) -> int:
        """Returns the number of the next iteration. The baseline entries are iteration 0, so this is 1 after them."""
        return max((exp.iteration for exp in self.load_history()), default=0) + 1
