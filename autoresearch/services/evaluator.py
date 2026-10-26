import json
import re
from typing import Any, Dict, Optional, Tuple

from autoresearch.services.services_utils import _extract_json_text
from pipeline.clients import OllamaClient
from pipeline.evaluation.error_categories import canonical_category


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
        fallback_model: Optional[str] = None,
    ):
        self.client = OllamaClient(ollama_url)
        self.model_name = model_name
        self.temperature = temperature
        self.options = {"num_ctx": num_ctx, "num_predict": num_predict}
        self.thinking = thinking
        self.fallback_model = fallback_model

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

    def _chat(self, model: str, user_prompt: str) -> Tuple[str, Optional[str]]:
        """One judge call: the answer and Ollama's done_reason. Raises RuntimeError if Ollama is unreachable."""
        content, _, _, meta = self.client.chat_with_metadata(
            model, user_prompt, self.system_prompt, self.options, self.temperature, self.thinking
        )
        return content.strip(), meta["done_reason"]

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

        # An unreachable judge raises RuntimeError from the client instead of counting as a verdict
        for attempt in range(1, max_retries + 1):
            content, done_reason = self._chat(self.model_name, user_prompt)
            # The thinking looped until num_predict: the same model at temperature 0 usually loops again
            stuck = done_reason == "length" and not content
            if stuck and self.fallback_model:
                content, _ = self._chat(self.fallback_model, user_prompt)

            try:
                verdict = self._parse_verdict(content)
            except ValueError as e:
                # An unparseable verdict counts as incorrect; a stuck call is not retried
                if attempt == max_retries or stuck:
                    return False, "Other", f"Evaluation failed: {e}"
                continue

            # Accept the boolean or its string form ("true")
            correct = str(verdict.get("correct")).strip().lower() == "true"
            category = None if correct else canonical_category(verdict.get("error_category"))
            rationale = str(verdict.get("rationale", "")).strip()
            return correct, category, rationale
