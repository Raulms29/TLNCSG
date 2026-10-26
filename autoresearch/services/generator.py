from pipeline.clients import OllamaClient


class GeneratorClient:
    """
    Calls the generator model, the parser whose prompt is being optimized, via Ollama.
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
        self.client = OllamaClient(ollama_url)
        self.model_name = model_name
        self.temperature = temperature
        self.options = {"num_ctx": num_ctx, "num_predict": num_predict}
        self.thinking = thinking

    def generate_translation(self, system_prompt: str, query_text: str) -> str:
        """
        Translates query_text into SemGIR under the given system_prompt.
        Raises RuntimeError when Ollama cannot be reached after the client's retries.
        """
        content, _, _, _ = self.client.chat_with_metadata(
            self.model_name, f'Input: "{query_text}"\nOutput:', system_prompt,
            self.options, self.temperature, self.thinking,
        )
        return content.strip()
