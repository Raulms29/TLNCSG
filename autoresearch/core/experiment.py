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
        mode: str = "optimize",
        query_results: Optional[Dict[str, Dict[str, Any]]] = None,
        hidden_ids: Optional[List[str]] = None,
        net: int = 0,
        net_hidden: int = 0,
        instructions_words: int = 0,
        instructions: Optional[str] = None,
        rationale: Optional[str] = None,
        timestamp: Optional[str] = None,
        results_file: Optional[str] = None,
        reference_results: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        self.iteration = iteration
        self.score = score
        self.delta = delta
        self.status = status
        self.prompt_path = prompt_path
        self.mode = mode
        self.query_results = query_results or {}
        self.hidden_ids = hidden_ids or []
        self.net = net
        self.net_hidden = net_hidden
        self.instructions_words = instructions_words
        self.instructions = instructions  # candidate instructions proposed in this iteration
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
            "delta": self.delta,
            "status": self.status,
            "mode": self.mode,
            "net": self.net,
            "net_hidden": self.net_hidden,
            "instructions_words": self.instructions_words,
            "prompt_path": self.prompt_path,
            "results_file": self.results_file,
            "hidden_ids": self.hidden_ids,
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
            delta=data.get("delta", 0.0),
            status=data.get("status", "UNKNOWN"),
            prompt_path=data.get("prompt_path", ""),
            mode=data.get("mode", "optimize"),
            query_results=data.get("query_results", {}),
            hidden_ids=data.get("hidden_ids", []),
            net=data.get("net", 0),
            net_hidden=data.get("net_hidden", 0),
            instructions_words=data.get("instructions_words", 0),
            instructions=data.get("instructions"),
            rationale=data.get("rationale"),
            timestamp=data.get("timestamp"),
            results_file=data.get("results_file"),
            reference_results=data.get("reference_results", {}),
        )

    def __repr__(self) -> str:
        return f"Experiment(iter={self.iteration}, score={self.score:.4f}, status={self.status})"
