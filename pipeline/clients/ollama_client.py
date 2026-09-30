"""OllamaClient — encapsulates all interaction with the Ollama API."""

from __future__ import annotations

import logging
import time

from ollama import Client

logger = logging.getLogger(__name__)


class OllamaClient:
    """Encapsulates Ollama API interaction with automatic retry and metadata extraction.

    All LLM calls go through this class so retry logic, message formatting,
    and response parsing are handled in a single place.
    """

    def __init__(
        self,
        host: str,
        max_retries: int = 5,
        wait_seconds: int = 5,
    ):
        self._client = Client(host)
        self._max_retries = max_retries
        self._wait_seconds = wait_seconds

    # ------------------------------------------------------------------
    # Message helpers
    # ------------------------------------------------------------------

    @staticmethod
    def build_chat_messages(
        system_prompt: str, query: str
    ) -> list[dict[str, str]]:
        """Build standard system + user messages for a single query."""
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]

    # ------------------------------------------------------------------
    # Low-level chat with retry
    # ------------------------------------------------------------------

    def _chat_with_retry(self, **kwargs) -> dict:
        """Execute an Ollama chat call, retrying on transient failures."""
        for attempt in range(self._max_retries):
            try:
                return self._client.chat(**kwargs)
            except Exception as e:
                if attempt == self._max_retries - 1:
                    logger.error(
                        "Ollama call failed after %d attempts: %s",
                        self._max_retries,
                        e,
                    )
                    return {"message": {"content": ""}}
                logger.warning(
                    "Ollama call failed (attempt %d/%d): %s. "
                    "Retrying in %d seconds …",
                    attempt + 1,
                    self._max_retries,
                    e,
                    self._wait_seconds,
                )
                time.sleep(self._wait_seconds)
        return {"message": {"content": ""}}

    # ------------------------------------------------------------------
    # High-level helpers
    # ------------------------------------------------------------------

    def chat_with_metadata(
        self,
        model: str,
        query: str,
        system_prompt: str,
        options: dict,
        temperature: float,
        thinking: bool = False,
    ) -> tuple[str, str | None, float, dict]:
        """Execute a chat call and return structured results.

        Returns:
            A tuple of ``(content, reasoning, inference_seconds, metadata)``.
        """
        opts = dict(options)
        opts["temperature"] = float(temperature)

        response = self._chat_with_retry(
            model=model,
            messages=self.build_chat_messages(system_prompt, query),
            options=opts,
            think=thinking,
        )

        content: str = response.get("message", {}).get("content", "")
        reasoning: str | None = (
            response.get("message", {}).get("thinking", None)
            if thinking
            else None
        )

        # ---- Timing from Ollama metadata (nanoseconds → seconds) ----
        total_ns = int(response.get("total_duration", 0) or 0)
        prompt_eval_ns = int(response.get("prompt_eval_duration", 0) or 0)
        eval_ns = int(response.get("eval_duration", 0) or 0)
        inference_ns = total_ns if total_ns > 0 else (prompt_eval_ns + eval_ns)
        inference_seconds = float(inference_ns) / 1_000_000_000.0

        metadata = {
            "done_reason": response.get("done_reason"),
            "prompt_eval_count": int(
                response.get("prompt_eval_count", 0) or 0
            ),
            "prompt_eval_duration_s": round(
                float(prompt_eval_ns) / 1_000_000_000.0, 6
            ),
            "eval_count": int(response.get("eval_count", 0) or 0),
            "eval_duration_s": round(
                float(eval_ns) / 1_000_000_000.0, 6
            ),
            "total_duration_s": round(
                float(total_ns) / 1_000_000_000.0, 6
            ),
        }

        return content, reasoning, inference_seconds, metadata

    def warmup(
        self,
        model: str,
        system_prompt: str,
        options: dict,
        temperature: float,
    ) -> None:
        """Run a single non-measured call to force model loading in Ollama."""
        logger.info("Warming up model: %s", model)
        self.chat_with_metadata(
            model=model,
            query=(
                "This is a warmup call to load the model. "
                "Please respond with the single word 'Warmup'."
            ),
            system_prompt=system_prompt,
            options=options,
            temperature=temperature,
            thinking=False,
        )
