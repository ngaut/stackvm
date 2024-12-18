import os
import time
from typing import Optional, Dict, Any, Generator
import openai
import requests
from abc import ABC, abstractmethod
import json
import logging
from google import genai

logger = logging.getLogger(__name__)


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

    def generate_stream(
        self, prompt: str, context: Optional[str] = None, **kwargs
    ) -> Generator[str, None, None]:
        full_prompt = f"{context}\n{prompt}" if context else prompt
        try:
            response = self._retry_with_exponential_backoff(
                self.client.chat.completions.create,
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": full_prompt},
                ],
                stream=True,  # Enable streaming
                temperature=0,
                **kwargs,
            )

            for chunk in response:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.error(f"Error during OpenAI streaming: {e}")
            yield f"Error: {str(e)}"


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


class GeminiProvider(BaseLLMProvider):
    """
    Provider for Google's Gemini API.
    """

    def __init__(self, model: str, **kwargs):
        super().__init__(model, **kwargs)
        api_key = os.getenv("GOOGLE_API_KEY")

        if not api_key:
            raise ValueError(
                "Google API key not set. Please set the GOOGLE_API_KEY environment variable."
            )

        self.client = genai.Client(api_key=api_key)

    def generate(
        self, prompt: str, context: Optional[str] = None, **kwargs
    ) -> Optional[str]:
        full_prompt = f"{context}\n{prompt}" if context else prompt
        response = self._retry_with_exponential_backoff(
            self.client.models.generate_content,
            model=self.model,
            contents=full_prompt,
            **kwargs,
        )
        return response.text.strip()

    def generate_stream(
        self, prompt: str, context: Optional[str] = None, **kwargs
    ) -> Generator[str, None, None]:
        """
        Generate streaming response from Gemini API.
        """
        full_prompt = f"{context}\n{prompt}" if context else prompt
        try:
            response = self._retry_with_exponential_backoff(
                self.client.models.generate_content_stream,
                model=self.model,
                contents=full_prompt,
                **kwargs,
            )

            for resp in response:
                if not resp.candidates:
                    continue

                for candidate in resp.candidates:
                    for part in candidate.content.parts:
                        if part.text:
                            yield part.text

        except Exception as e:
            logger.error(f"Error during Gemini streaming: {e}")
            yield f"Error: {str(e)}"


class LLMInterface:
    def __init__(self, provider: str, model: str, **kwargs):
        self.provider = self._get_provider(provider.lower(), model, **kwargs)

    def _get_provider(self, provider: str, model: str, **kwargs) -> BaseLLMProvider:
        if provider == "openai":
            return OpenAIProvider(model, **kwargs)
        elif provider == "ollama":
            return OllamaProvider(model, **kwargs)
        elif provider == "gemini":
            return GeminiProvider(model, **kwargs)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    def generate(
        self, prompt: str, context: Optional[str] = None, **kwargs
    ) -> Optional[str]:
        try:
            return self.provider.generate(prompt, context, **kwargs)
        except Exception as e:
            print(f"LLM generation failed: {e}")
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
