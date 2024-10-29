import os
import time
from typing import Optional, Dict, Any
import openai
import requests
from abc import ABC, abstractmethod


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


class OpenAIProvider(BaseLLMProvider):
    """
    Provider for OpenAI.
    """

    def __init__(self, model: str, **kwargs):
        super().__init__(model, **kwargs)
        openai.api_key = os.getenv("OPENAI_API_KEY")
        if not openai.api_key:
            raise ValueError(
                "OpenAI API key not set. Please set the OPENAI_API_KEY environment variable."
            )
        self.client = openai.OpenAI()

    def generate(
        self, prompt: str, context: Optional[str] = None, **kwargs
    ) -> Optional[str]:
        full_prompt = f"{context}\n{prompt}" if context else prompt
        response = self._retry_with_exponential_backoff(
            self.client.chat.completions.create,
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": full_prompt},
            ],
            temperature=0,
            **kwargs,
        )
        return response.choices[0].message.content.strip()


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


class LLMInterface:
    def __init__(self, provider: str, model: str, **kwargs):
        self.provider = self._get_provider(provider.lower(), model, **kwargs)

    def _get_provider(self, provider: str, model: str, **kwargs) -> BaseLLMProvider:
        if provider == "openai":
            return OpenAIProvider(model, **kwargs)
        elif provider == "ollama":
            return OllamaProvider(model, **kwargs)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    def generate(
        self, prompt: str, context: Optional[str] = None, **kwargs
    ) -> Optional[str]:
        try:
            return self.provider.generate(prompt, context, **kwargs)
        except Exception as e:
            print(f"LLM generation failed: {e}")
            return None

    def evaluate_condition(
        self, prompt: str, context: Optional[str] = None
    ) -> Optional[str]:
        return self.generate(prompt, context)
