import json
import time
from typing import Tuple, Dict, Any
from ollama import Client
import utils


class EvaluatorAgent:
    """
    Acts as the LLM-as-a-Judge to evaluate translation outputs against the ground truths
    using a strict grading rubric and returns scores and rationales.
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

    def _clean_and_parse_json(self, raw_text: str) -> Dict[str, Any]:
        """
        Extracts and parses JSON from raw LLM output, selecting the last JSON block.
        """
        json_str = utils._extract_json_text(raw_text)
        try:
            return json.loads(json_str, strict=False)
        except Exception as e:
            # Fallback regex extraction for poorly escaped JSON
            import re

            score = 0.0
            rationale = ""
            score_match = re.search(r'"score"\s*:\s*([0-9.]+)', json_str)
            rat_match1 = re.search(
                r'"rationale"\s*:\s*"(.*?)"\s*,\s*"score"',
                json_str,
                re.DOTALL | re.IGNORECASE,
            )
            rat_match2 = re.search(
                r'"score".*?,\s*"rationale"\s*:\s*"(.*?)"\s*}',
                json_str,
                re.DOTALL | re.IGNORECASE,
            )

            if score_match:
                score = float(score_match.group(1))
                if rat_match1:
                    rationale = rat_match1.group(1)
                elif rat_match2:
                    rationale = rat_match2.group(1)
                else:
                    rationale = f"Unescaped JSON. Raw: {json_str}"
                return {"score": score, "rationale": rationale.strip()}

            raise ValueError(
                f"Could not parse response as valid JSON object: {raw_text}. Error: {str(e)}"
            )

    def evaluate(
        self,
        query_text: str,
        ground_truth_json: str,
        candidate_raw: str,
        max_retries: int = 3,
    ) -> Tuple[float, str]:
        """
        Evaluates a candidate translation against the ground truth.
        Returns a tuple: (score, rationale)
        """
        user_prompt = (
            f'[ORIGINAL NATURAL LANGUAGE QUERY]\n"{query_text}"\n\n'
            f"[GROUND TRUTH JSON IR]\n{ground_truth_json}\n\n"
            f"[CANDIDATE JSON IR]\n{candidate_raw}\n\n"
            f"Assign score and rationale in strict JSON format:"
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
                parsed = self._clean_and_parse_json(content)

                score = float(parsed.get("score", 0.0))
                rationale = str(parsed.get("rationale", "")).strip()
                return score, rationale
            except Exception as e:
                if attempt == max_retries:
                    # Reraise or return 0.0 on final failure to make sure we don't crash the loop
                    return 0.0, f"Evaluation execution failed: {str(e)}"
                time.sleep(delay)
                delay *= 2.0

        return 0.0, "Evaluation failed to complete."
