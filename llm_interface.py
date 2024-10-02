import os
from typing import Optional, Dict, List, Any
import openai
from config import LLM_MODEL
from utils import parse_plan

class LLMInterface:
    def __init__(self, model: str):
        self.model = model
        openai.api_key = os.getenv('OPENAI_API_KEY')
        if not openai.api_key:
            raise ValueError("OpenAI API key not set. Please set the OPENAI_API_KEY environment variable.")
        self.client = openai.OpenAI()

    def generate(self, prompt: str, context: Optional[str] = None) -> Optional[str]:
        try:
            if context:
                full_prompt = f"{context}\n{prompt}"
            else:
                full_prompt = prompt

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": full_prompt}
                ],
                temperature=0
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"LLM generation failed: {e}")
            return None

    def evaluate_condition(self, prompt: str, context: Optional[str] = None) -> Optional[str]:
        try:
            if context:
                full_prompt = f"{context}\n{prompt}"
            else:
                full_prompt = prompt

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant. Respond with 'true' or 'false' only."},
                    {"role": "user", "content": full_prompt}
                ],
                temperature=0
            )
            result = response.choices[0].message.content.strip().lower()
            if result in ['true', 'false']:
                return result
            else:
                print(f"Invalid condition response: '{result}'. Expected 'true' or 'false'.")
                return None
        except Exception as e:
            print(f"Condition evaluation failed: {e}")
            return None