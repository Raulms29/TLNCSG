import time
from ollama import Client


class GeneratorClient:
    """
    Wrapper for calling the target generator model (e.g. gemma4:26b) via Ollama.
    """

    def __init__(
        self,
        ollama_url: str,
        model_name: str,
        temperature: float,
        num_ctx: int,
        num_predict: int,
        thinking: bool = False,
    ):
        self.client = Client(ollama_url)
        self.model_name = model_name
        self.temperature = temperature
        self.num_ctx = num_ctx
        self.num_predict = num_predict
        self.thinking = thinking

    def generate_translation(
        self, system_prompt: str, query_text: str, max_retries: int = 3
    ) -> str:
        """
        Calls Ollama to translate the query_text into SemGIR under the given system_prompt.
        Implements exponential backoff retry logic for robust remote API calls.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f'Input: "{query_text}"\nOutput:'},
        ]

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
                    messages=messages,
                    options=options,
                    think=self.thinking,
                )
                return response.get("message", {}).get("content", "").strip()
            except Exception as e:
                if attempt == max_retries:
                    # Reraise on final failure
                    raise RuntimeError(
                        f"Failed to generate translation after {max_retries} attempts: {str(e)}"
                    )
                time.sleep(delay)
                delay *= 2.0

        return ""
