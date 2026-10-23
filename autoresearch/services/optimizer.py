import difflib
import time
import re
from collections import defaultdict
from typing import List, Dict, Any, Tuple
from ollama import Client

OPTIMIZE_REQUEST = (
    "Based on the failing queries, propose the smallest change to the instructions that addresses them. "
    "Removing or merging text is a valid change."
)
SIMPLIFY_REQUEST = (
    "This is a simplification step. Make the instructions shorter by merging, shortening or removing rules, "
    "without adding new rules and without changing what they ask the parser to do."
)


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
        thinking: bool = False,
    ):
        self.client = Client(ollama_url)
        self.model_name = model_name
        self.temperature = temperature
        self.num_ctx = num_ctx
        self.num_predict = num_predict
        self.memory_size = memory_size
        self.thinking = thinking
        self.failure_history: List[Dict[str, Any]] = []  # sliding window of rejected attempts

        # Load optimizer prompt directly from disk
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.system_prompt = f.read()

    def add_to_failure_history(
        self, champion_instructions: str, rejected_instructions: str, net: int, broken: List[Dict[str, str]]
    ):
        """Adds a rejected change, as a diff against the champion with the queries it broke, to memory
        to prevent repeating it."""
        diff = "\n".join(
            difflib.unified_diff(
                champion_instructions.splitlines(),
                rejected_instructions.splitlines(),
                "champion",
                "rejected",
                lineterm="",
            )
        )
        self.failure_history.append({"net": net, "diff": diff or "(no change)", "broken": broken})
        if len(self.failure_history) > self.memory_size:
            self.failure_history.pop(0)

    def clear_failure_history(self):
        """Clears memory when a new champion is successfully established."""
        self.failure_history.clear()

    @staticmethod
    def _format_failures(failures: List[Dict[str, Any]]) -> str:
        """Groups failures by error category, largest group first."""
        groups = defaultdict(list)
        for fail in failures:
            groups[fail.get("error_category") or "Other"].append(fail)

        blocks = []
        for category, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            lines = [f"#### {category} ({len(items)} queries)"]
            for fail in items:
                lines.append(
                    f"- Query {fail['id']} | correct rate: {fail['rate']:.2f}"
                    f" | features: [{', '.join(fail['features'])}]"
                    f" | rubric features: [{'; '.join(fail['rubric_features'])}]\n"
                    f"  Evaluator rationale: {fail['rationale']}"
                )
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks) if blocks else "None."

    @staticmethod
    def _format_rejected(idx: int, item: Dict[str, Any]) -> str:
        text = f"Rejected change #{idx} (net queries fixed: {item['net']}):\n{item['diff']}"
        if item["broken"]:
            text += "\nQueries this change broke:\n" + "\n".join(
                f"- Query {query['id']} | Evaluator rationale: {query['rationale']}" for query in item["broken"]
            )
        return text

    def _build_user_prompt(
        self, current_instructions: str, prompt_context: str, failures: List[Dict[str, Any]], mode: str
    ) -> str:
        history = "\n\n".join(
            self._format_rejected(idx, item) for idx, item in enumerate(self.failure_history, 1)
        ) or "None."

        sections = [
            f'### READ-ONLY PROMPT CONTEXT (rest of the parser prompt, not editable):\n"""\n{prompt_context}\n"""',
            f'### CURRENT ## INSTRUCTIONS SECTION:\n"""\n{current_instructions}\n"""',
            f"### RECENT REJECTED CHANGES (DO NOT REPEAT):\n{history}",
        ]
        if mode == "simplify":
            sections.append(SIMPLIFY_REQUEST)
        else:
            sections.append(f"### FAILING QUERIES BY ERROR CATEGORY:\n{self._format_failures(failures)}")
            sections.append(OPTIMIZE_REQUEST)
        return "\n\n".join(sections)

    def _clean_optimizer_output(self, raw_text: str) -> Tuple[str, str]:
        """Cleans LLM response, extracting rationale and instructions."""
        cleaned = raw_text.strip()

        rationale = ""
        rat_match = re.search(
            r"<rationale>\s*([\s\S]*?)\s*</rationale>", cleaned, re.IGNORECASE
        )
        if rat_match:
            rationale = rat_match.group(1).strip()

        # Extract content inside <instructions> tags; anything else is a malformed answer and is retried
        match = re.search(
            r"<instructions>\s*([\s\S]*?)</instructions>", cleaned, re.IGNORECASE
        )
        if not match:
            raise ValueError(
                "Optimizer output has no complete <instructions>...</instructions> block. "
                "Generation was likely cut off or ignored the output format."
            )
        cleaned = match.group(1).strip()

        # Remove a duplicate ## INSTRUCTIONS heading if the model printed it
        cleaned = re.sub(
            r"^##\s*INSTRUCTIONS\s*", "", cleaned, flags=re.IGNORECASE
        ).strip()

        return cleaned, rationale

    def optimize_instructions(
        self,
        current_instructions: str,
        prompt_context: str,
        failures: List[Dict[str, Any]],
        mode: str = "optimize",
        max_retries: int = 3,
    ) -> Tuple[str, str]:
        """
        Generates optimized instructions using Ollama.
        Returns:
            Tuple[str, str]: (new_instructions, rationale)
        """
        user_prompt = self._build_user_prompt(current_instructions, prompt_context, failures, mode)

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
                return self._clean_optimizer_output(content)
            except Exception as e:
                if attempt == max_retries:
                    raise RuntimeError(
                        f"Failed to generate optimized instructions: {str(e)}"
                    )
                time.sleep(delay)
                delay *= 2.0

        return current_instructions, ""
