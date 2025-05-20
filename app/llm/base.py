import time
import logging
import tiktoken
from abc import ABC, abstractmethod
from typing import Optional, Generator
from app.config.settings import MODEL_CONFIGS

logger = logging.getLogger(__name__)


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """
    Count the number of tokens in a text string.

    :param text: The text to count tokens for
    :param model: The model name to use for token counting (default: gpt-4o)
    :return: Number of tokens
    """
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))


class BaseLLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    """

    def __init__(self, model: str, max_retries: int = 3, retry_delay: float = 1.0):
        self.model = model
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def _retry_with_exponential_backoff(self, func, *args, **kwargs):
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                wait_time = self.retry_delay * (2**attempt)
                print(f"API request failed. Retrying in {wait_time:.2f} seconds...")
                time.sleep(wait_time)

    @abstractmethod
    def generate(
        self, prompt: str, context: Optional[str] = None, **kwargs
    ) -> Optional[str]:
        pass

    @abstractmethod
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
        pass

    def _get_default_model_config(self) -> dict:
        """Get model-specific configuration parameters."""
        # First check if there's a user-defined config in environment variables
        env_config = MODEL_CONFIGS.get(self.model, {})
        if env_config:
            return env_config

        # If no environment config, use default configs
        if self.model == "gpt-4o":
            return {
                "temperature": 0,
            }
        elif self.model == "o3-mini":
            return {"reasoning_effort": "medium"}

        return {}

    def _update_kwargs(self, kwargs: dict) -> dict:
        # if config exists both in default and kwargs, use kwargs
        for key, value in self._get_default_model_config().items():
            if key in kwargs:
                kwargs[key] = kwargs[key]
            else:
                kwargs[key] = value
        return kwargs
