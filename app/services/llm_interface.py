import os
import time
from typing import Optional
import openai

class LLMInterface:
    def __init__(self, model: str, max_retries: int = 3, retry_delay: float = 1.0):
        self.model = model
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        openai.api_key = os.getenv('OPENAI_API_KEY')
        if not openai.api_key:
            raise ValueError("OpenAI API key not set. Please set the OPENAI_API_KEY environment variable.")
        self.client = openai.OpenAI()

    def _retry_with_exponential_backoff(self, func, *args, **kwargs):
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except (openai.RateLimitError, openai.APIError, openai.APIConnectionError) as e:
                if attempt == self.max_retries - 1:
                    raise
                wait_time = self.retry_delay * (2 ** attempt)
                print(f"API request failed. Retrying in {wait_time:.2f} seconds...")
                time.sleep(wait_time)

    def generate(self, prompt: str, context: Optional[str] = None, **kwargs) -> Optional[str]:
        try:
            if context:
                full_prompt = f"{context}\n{prompt}"
            else:
                full_prompt = prompt

            response = self._retry_with_exponential_backoff(
                self.client.chat.completions.create,
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": full_prompt}
                ],
                temperature=0,
                **kwargs  # Ensure kwargs are passed as keyword arguments
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"LLM generation failed: {e}")
            return None

    def evaluate_condition(self, prompt: str, context: Optional[str] = None) -> Optional[str]:
        try:
            if context:
                full_prompt = f"prompt: {prompt}\ncontext: {context}"
            else:
                full_prompt = f"prompt: {prompt}"

            response = self._retry_with_exponential_backoff(
                self.client.chat.completions.create,
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": full_prompt}
                ],
                temperature=0
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Condition evaluation failed: {e}")
            return None
