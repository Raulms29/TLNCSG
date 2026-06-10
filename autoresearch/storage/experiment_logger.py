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

    def get_best_experiment(self) -> Optional[Experiment]:
        """
        Scans the history and returns the Experiment with the highest validation score.
        If multiple have the same score, returns the latest one.
        """
        history = self.load_history()
        if not history:
            return None

        best = history[0]
        for exp in history[1:]:
            # We favor the latest model if scores are tied, or the strictly better score
            if exp.score >= best.score:
                best = exp
        return best

    def get_next_iteration_number(self) -> int:
        """Returns the iteration number for the upcoming run (length of history + 1)."""
        history = self.load_history()
        return len(history) + 1
