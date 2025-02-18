import logging
from typing import Optional, Generator

from app.llm.base import BaseLLMProvider
from app.llm.providers import (
    OpenAIProvider,
    OllamaProvider,
    GeminiProvider,
    BedrockProvider,
    OpenAILikeProvider,
)

logger = logging.getLogger(__name__)


class LLMInterface:
    def __init__(self, provider: str, model: str, **kwargs):
        self.provider = self._get_provider(provider.lower(), model, **kwargs)

    def _get_provider(self, provider: str, model: str, **kwargs) -> BaseLLMProvider:
        if provider == "openai":
            return OpenAIProvider(model, **kwargs)
        elif provider == "openai_like":
            return OpenAILikeProvider(model, **kwargs)
        elif provider == "ollama":
            return OllamaProvider(model, **kwargs)
        elif provider == "gemini":
            return GeminiProvider(model, **kwargs)
        elif provider == "bedrock":
            return BedrockProvider(model, **kwargs)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    def generate(
        self, prompt: str, context: Optional[str] = None, **kwargs
    ) -> Optional[str]:
        try:
            return self.provider.generate(prompt, context, **kwargs)
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise e

    def evaluate_condition(
        self, prompt: str, context: Optional[str] = None
    ) -> Optional[str]:
        return self.generate(prompt, context)

    def generate_stream(
        self, prompt: str, context: Optional[str] = None, **kwargs
    ) -> Generator[str, None, None]:
        """
        Generate streaming response from the LLM.

        Args:
            prompt (str): The prompt to send to the LLM
            context (Optional[str]): Optional context to prepend to the prompt
            **kwargs: Additional arguments to pass to the LLM

        Yields:
            str: Chunks of the generated text
        """
        try:
            for chunk in self.provider.generate_stream(prompt, context, **kwargs):
                yield chunk
        except Exception as e:
            logger.error(f"LLM streaming generation failed: {e}")
            yield f"Error: {str(e)}"
