from typing import Any, Dict, List, Optional
from datetime import datetime


class Experiment:
    """
    Represents the result and metadata of a single optimization iteration.
    """

    def __init__(
        self,
        iteration: int,
        score: float,
        delta: float,
        status: str,
        prompt_path: str,
        failures: Optional[List[Dict[str, Any]]] = None,
        rationale: Optional[str] = None,
        timestamp: Optional[str] = None,
        results_file: Optional[str] = None,
    ):
        self.iteration = iteration
        self.score = score
        self.delta = delta
        self.status = status
        self.prompt_path = prompt_path
        self.failures = failures or []
        self.rationale = rationale
        self.timestamp = timestamp or datetime.now().isoformat()
        self.results_file = results_file

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration": self.iteration,
            "timestamp": self.timestamp,
            "score": self.score,
            "delta": self.delta,
            "status": self.status,
            "prompt_path": self.prompt_path,
            "results_file": self.results_file,
            "failures": self.failures,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Experiment":
        return cls(
            iteration=data.get("iteration", 0),
            score=data.get("score", 0.0),
            delta=data.get("delta", 0.0),
            status=data.get("status", "UNKNOWN"),
            prompt_path=data.get("prompt_path", ""),
            failures=data.get("failures", []),
            rationale=data.get("rationale"),
            timestamp=data.get("timestamp"),
            results_file=data.get("results_file"),
        )

    def __repr__(self) -> str:
        return f"Experiment(iter={self.iteration}, score={self.score:.4f}, status={self.status})"
