import time
import re
from typing import List, Dict, Any
from ollama import Client


class OptimizerAgent:
    """
    Refines prompt instructions based on evaluation failure logs and historical memory
    of unsuccessful modifications.
    """

    def __init__(
        self,
        ollama_url: str,
        model_name: str,
        temperature: float,
        num_ctx: int,
        num_predict: int,
        memory_size: int,
        prompt_path: str,
    ):
        self.client = Client(ollama_url)
        self.model_name = model_name
        self.temperature = temperature
        self.num_ctx = num_ctx
        self.num_predict = num_predict
        self.memory_size = memory_size
        self.failure_history: List[Dict[str, Any]] = (
            []
        )  # sliding window of rejected attempts

        # Load optimizer prompt directly from disk
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.system_prompt = f.read()

    def add_to_failure_history(self, score: float, instructions: str):
        """Adds an unsuccessful prompt configuration to memory to prevent repeating it."""
        self.failure_history.append(
            {
                "score": score,
                "instructions": instructions,
            }
        )
        # Keep within sliding window size
        if len(self.failure_history) > self.memory_size:
            self.failure_history.pop(0)

    def clear_failure_history(self):
        """Clears memory when a new champion is successfully established."""
        self.failure_history.clear()

    def _build_user_prompt(
        self, current_instructions: str, failures: List[Dict[str, Any]]
    ) -> str:
        # 1. Format failures log
        fail_blocks = []
        for fail in failures:
            tags_str = ", ".join(fail.get("features", []))
            fail_blocks.append(
                f"- Query ID: {fail.get('id')}\n"
                f"  Tested Grammatical Features: [{tags_str}]\n"
                f"  Evaluator Rationale: {fail.get('rationale')}"
            )
        failures_log = "\n\n".join(fail_blocks)

        # 2. Format rejected history
        history_blocks = []
        for idx, item in enumerate(self.failure_history, 1):
            history_blocks.append(
                f"Rejected Attempt #{idx}:\n"
                f"- Resulting Score: {item['score']:.4f}\n"
                f"- Instructions attempted:\n\"\"\"\n{item['instructions']}\n\"\"\""
            )
        history_log = "\n\n".join(history_blocks) if history_blocks else "None."

        user_content = (
            f"### CURRENT ## INSTRUCTIONS SECTION:\n"
            f'"""\n{current_instructions}\n"""\n\n'
            f"### RECENT REJECTED PROMPT CHANGES (DO NOT REPEAT):\n"
            f"{history_log}\n\n"
            f"### CURRENT RUN FAILING LOGS:\n"
            f"{failures_log}\n\n"
            f"Based on the failing rationales, identify the logical ambiguity in the instructions and propose a surgical correction. "
            "Write the updated, complete ## INSTRUCTIONS block:"
        )
        return user_content

    def _clean_optimizer_output(self, raw_text: str) -> str:
        """Cleans LLM response, stripping Markdown wrappers."""
        cleaned = raw_text.strip()

        # Strip markdown code blocks if the model wrapped the instructions
        if cleaned.startswith("```"):
            match = re.search(
                r"```(?:markdown)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE
            )
            if match:
                cleaned = match.group(1).strip()

        # Remove a duplicate ## INSTRUCTIONS heading if the model printed it
        cleaned = re.sub(
            r"^##\s*INSTRUCTIONS\s*", "", cleaned, flags=re.IGNORECASE
        ).strip()

        return cleaned

    def optimize_instructions(
        self,
        current_instructions: str,
        failures: List[Dict[str, Any]],
        max_retries: int = 3,
    ) -> str:
        """
        Generates optimized instructions using Ollama.
        Returns:
            new_instructions: The refined Markdown instructions block.
        """
        system_prompt = self.system_prompt
        user_prompt = self._build_user_prompt(current_instructions, failures)

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
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    options=options,
                )
                content = response.get("message", {}).get("content", "").strip()
                return self._clean_optimizer_output(content)
            except Exception as e:
                if attempt == max_retries:
                    raise RuntimeError(
                        f"Failed to generate optimized instructions: {str(e)}"
                    )
                time.sleep(delay)
                delay *= 2.0

        return current_instructions
