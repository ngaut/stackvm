import os
import logging
from google import genai
from typing import Optional, Generator

from app.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


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
