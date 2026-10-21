import json
import re
import time
from typing import Any, Dict, Optional, Tuple

from ollama import Client

from autoresearch.services.services_utils import _extract_json_text
from pipeline.evaluation.error_categories import ERROR_CATEGORIES


class EvaluatorAgent:
    """
    Acts as the LLM-as-a-Judge: decides whether a candidate translation is correct
    against the ground truth and classifies the error when it is not.
    """

    def __init__(
        self,
        ollama_url: str,
        model_name: str,
        temperature: float,
        num_ctx: int,
        num_predict: int,
        prompt_path: str,
        thinking: bool = False,
    ):
        self.client = Client(ollama_url)
        self.model_name = model_name
        self.temperature = temperature
        self.num_ctx = num_ctx
        self.num_predict = num_predict
        self.thinking = thinking

        # Load evaluator prompt directly from disk
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.system_prompt = f.read()

    def _parse_verdict(self, raw_text: str) -> Dict[str, Any]:
        """Extracts the verdict JSON from the raw LLM output, with a regex fallback."""
        json_str = _extract_json_text(raw_text)
        try:
            return json.loads(json_str, strict=False)
        except Exception:
            correct_match = re.search(r'"correct"\s*:\s*(true|false)', json_str, re.IGNORECASE)
            if not correct_match:
                raise ValueError(f"Could not parse evaluator response: {raw_text}")
            category_match = re.search(r'"error_category"\s*:\s*"([^"]*)"', json_str)
            rationale_match = re.search(r'"rationale"\s*:\s*"(.*?)"\s*,', json_str, re.DOTALL)
            return {
                "correct": correct_match.group(1).lower() == "true",
                "error_category": category_match.group(1) if category_match else None,
                "rationale": rationale_match.group(1) if rationale_match else json_str,
            }

    @staticmethod
    def _normalize_category(correct: bool, category: Any) -> Optional[str]:
        """Returns None for correct verdicts and the canonical category name (or 'Other') otherwise."""
        if correct:
            return None
        name = str(category or "").strip().lower()
        return next((known for known in ERROR_CATEGORIES if known.lower() == name), "Other")

    def evaluate(
        self,
        query_text: str,
        ground_truth_json: str,
        candidate_json: str,
        max_retries: int = 3,
    ) -> Tuple[bool, Optional[str], str]:
        """
        Evaluates a candidate translation against the ground truth.
        Returns a tuple: (correct, error_category, rationale)
        """
        user_prompt = (
            f'[ORIGINAL NATURAL LANGUAGE QUERY]\n"{query_text}"\n\n'
            f"[GROUND TRUTH JSON IR]\n{ground_truth_json}\n\n"
            f"[CANDIDATE JSON IR]\n{candidate_json}\n\n"
            f"Return the verdict in strict JSON format:"
        )

        options = {
            "temperature": self.temperature,
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
        }

        delay = 2.0
        for attempt in range(1, max_retries + 1):
            try:
                response = self.client.chat(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    options=options,
                    think=self.thinking,
                )
                content = response.get("message", {}).get("content", "").strip()
            except Exception as e:
                # The judge could not be reached: raise instead of counting it as a verdict
                if attempt == max_retries:
                    raise RuntimeError(f"Judge request failed after {max_retries} attempts: {e}")
                time.sleep(delay)
                delay *= 2.0
                continue

            try:
                verdict = self._parse_verdict(content)
            except ValueError as e:
                # An unparseable verdict counts as incorrect
                if attempt == max_retries:
                    return False, "Other", f"Evaluation failed: {e}"
                continue

            # Accept the boolean or its string form ("true")
            correct = str(verdict.get("correct")).strip().lower() == "true"
            category = self._normalize_category(correct, verdict.get("error_category"))
            rationale = str(verdict.get("rationale", "")).strip()
            return correct, category, rationale

        return False, "Other", "Evaluation failed to complete."
