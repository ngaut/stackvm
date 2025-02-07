import os
from typing import Optional, Generator
import requests
import json
import logging

from app.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    """
    Provider for Ollama.
    """

    def __init__(self, model: str, **kwargs):
        super().__init__(model, **kwargs)
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    def generate(
        self, prompt: str, context: Optional[str] = None, **kwargs
    ) -> Optional[str]:
        full_prompt = f"{context}\n{prompt}" if context else prompt
        data = {"model": self.model, "prompt": full_prompt, "stream": False, **kwargs}
        response = self._retry_with_exponential_backoff(
            requests.post, f"{self.ollama_base_url}/api/generate", json=data
        )
        response.raise_for_status()
        return response.json()["response"].strip()

    def generate_stream(
        self, prompt: str, context: Optional[str] = None, **kwargs
    ) -> Generator[str, None, None]:
        """
        Generate streaming response from Ollama API.

        Args:
            prompt (str): The prompt to send to Ollama
            context (Optional[str]): Optional context to prepend to the prompt
            **kwargs: Additional arguments to pass to Ollama API

        Yields:
            str: Chunks of the generated text
        """
        full_prompt = f"{context}\n{prompt}" if context else prompt
        try:
            data = {"model": self.model, "prompt": full_prompt, **kwargs}

            response = requests.post(
                f"{self.ollama_base_url}/api/generate", json=data, stream=True
            )

            response.raise_for_status()

            for line in response.iter_lines():
                if not line:
                    continue

                try:
                    chunk = json.loads(line.decode("utf-8"))
                    if chunk.get("done", False):
                        break

                    if "response" in chunk:
                        yield chunk["response"]

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to decode JSON from Ollama response: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error during Ollama streaming: {e}")
            yield f"Error: {str(e)}"
