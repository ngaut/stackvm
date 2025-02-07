import os
from typing import Optional, Generator
import openai
import logging

from app.llm.base import BaseLLMProvider


logger = logging.getLogger(__name__)


class OpenAIProvider(BaseLLMProvider):
    """
    Provider for OpenAI.
    """

    def __init__(self, model: str, **kwargs):
        super().__init__(model, **kwargs)
        openai.api_key = os.getenv("OPENAI_API_KEY")
        openai.base_url = os.getenv("OPENAI_BASE_URL")
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
            **self._update_kwargs(kwargs),
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
                **self._update_kwargs(kwargs),
            )

            for chunk in response:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.error(f"Error during OpenAI streaming: {e}")
            yield f"Error: {str(e)}"
