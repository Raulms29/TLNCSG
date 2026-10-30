from typing import Any, Dict, Optional
from datetime import datetime


class Experiment:
    """
    Represents the result and metadata of a single optimization iteration.
    score is the mean correct rate on val, train_score on train; net_val and net_train are the
    queries fixed minus the queries broken against the champion on each set.
    """

    def __init__(
        self,
        iteration: int,
        score: float,
        delta: float,
        status: str,
        prompt_path: str,
        train_score: float = 0.0,
        query_results: Optional[Dict[str, Dict[str, Any]]] = None,
        net_train: int = 0,
        net_val: int = 0,
        instructions_words: int = 0,
        instructions: Optional[str] = None,
        rationale: Optional[str] = None,
        timestamp: Optional[str] = None,
        results_file: Optional[str] = None,
        reference_results: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        self.iteration = iteration
        self.score = score
        self.train_score = train_score
        self.delta = delta
        self.status = status
        self.prompt_path = prompt_path
        self.query_results = query_results or {}
        self.net_train = net_train
        self.net_val = net_val
        self.instructions_words = instructions_words
        self.instructions = (
            instructions  # candidate instructions proposed in this iteration
        )
        self.rationale = rationale
        self.timestamp = timestamp or datetime.now().isoformat()
        self.results_file = results_file
        # Champions only: the results later candidates are compared to
        self.reference_results = reference_results or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration": self.iteration,
            "timestamp": self.timestamp,
            "score": self.score,
            "train_score": self.train_score,
            "delta": self.delta,
            "status": self.status,
            "net_train": self.net_train,
            "net_val": self.net_val,
            "instructions_words": self.instructions_words,
            "prompt_path": self.prompt_path,
            "results_file": self.results_file,
            "query_results": self.query_results,
            "reference_results": self.reference_results,
            "rationale": self.rationale,
            "instructions": self.instructions,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Experiment":
        return cls(
            iteration=data.get("iteration", 0),
            score=data.get("score", 0.0),
            train_score=data.get("train_score", 0.0),
            delta=data.get("delta", 0.0),
            status=data.get("status", "UNKNOWN"),
            prompt_path=data.get("prompt_path", ""),
            query_results=data.get("query_results", {}),
            net_train=data.get("net_train", 0),
            net_val=data.get("net_val", 0),
            instructions_words=data.get("instructions_words", 0),
            instructions=data.get("instructions"),
            rationale=data.get("rationale"),
            timestamp=data.get("timestamp"),
            results_file=data.get("results_file"),
            reference_results=data.get("reference_results", {}),
        )

    def __repr__(self) -> str:
        return f"Experiment(iter={self.iteration}, score={self.score:.4f}, status={self.status})"
