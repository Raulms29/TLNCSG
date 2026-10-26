"""Phase 2 Fallback Grouping using an LLM."""

from __future__ import annotations

import json
import logging

from pipeline.clients.ollama_client import OllamaClient
from pipeline.grammars import prompt_for_grammar
from .config import GrouperModelConfig
from .normalizers import last_code_block

logger = logging.getLogger(__name__)


class LLMGrouper:
    """Uses an LLM to determine if a singleton group is equivalent to a larger group."""

    def __init__(self, client: OllamaClient, config: GrouperModelConfig, system_prompts: dict[str, str]):
        self.client = client
        self.config = config
        self.system_prompts = system_prompts

    def is_equivalent(
        self, query: str, output_a: str, output_b: str, grammar: str
    ) -> bool:
        """Ask the LLM if output_a and output_b are equivalent for the given query."""
        user_prompt = (
            f"Query: {query}\n\n"
            f"--- Output A ---\n{output_a}\n\n"
            f"--- Output B ---\n{output_b}\n\n"
            "Are Output A and Output B equivalent? Respond with a JSON block."
        )

        sys_prompt = prompt_for_grammar(self.system_prompts, grammar)
        if not sys_prompt:
            logger.warning("No system prompt found for grammar '%s'. LLM fallback skipped.", grammar)
            return False

        content, _, _, _ = self.client.chat_with_metadata(
            model=self.config.name,
            query=user_prompt,
            system_prompt=sys_prompt,
            options=self.config.ollama_options,
            temperature=self.config.temperature,
            thinking=self.config.supports_thinking,
        )

        # Take the LAST block in case it self-corrected
        extracted_text = last_code_block(content, "json")

        try:
            result = json.loads(extracted_text)
            return bool(result.get("equivalent", False))
        except json.JSONDecodeError:
            logger.warning("LLM Grouper returned unparseable text instead of JSON. Raw output: %r", content)
            return False
