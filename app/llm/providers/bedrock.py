import os
from typing import Optional, Generator
import json
import logging
import boto3

from app.llm.base import BaseLLMProvider, count_tokens

logger = logging.getLogger(__name__)


class BedrockProvider(BaseLLMProvider):

    @staticmethod
    def get_credentials() -> dict:
        required_vars = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]
        missing_vars = [var for var in required_vars if not os.getenv(var)]

        if missing_vars:
            raise ValueError(
                f"Missing required AWS environment variables: {', '.join(missing_vars)}"
            )

        region = os.getenv("AWS_DEFAULT_REGION", "us-west-2")

        return {
            "aws_access_key_id": os.getenv("AWS_ACCESS_KEY_ID"),
            "aws_secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
            "region_name": region,
        }

    @staticmethod
    def is_configured() -> bool:
        try:
            BedrockProvider.get_credentials()
            return True
        except ValueError:
            return False

    def __init__(self, model: str, **kwargs):
        super().__init__(model)

        if not self.is_configured():
            raise ValueError(
                "AWS credentials not configured. Please set AWS_ACCESS_KEY_ID and "
                "AWS_SECRET_ACCESS_KEY environment variables."
            )

        credentials = self.get_credentials()
        self.client = boto3.client("bedrock-runtime", **credentials)

        # TODO: support more models
        self.model_map = {
            "claude-3-sonnet": "anthropic.claude-3-sonnet-20240229-v1:0",
            "claude-3-5-sonnet": "anthropic.claude-3-5-sonnet-20240620-v1:0",
            "claude-3-5-sonnet-v2": "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "claude-3-7-sonnet": "anthropic.claude-3-7-sonnet-20250219-v1:0",
        }

        self.model = self.model_map.get(model.lower(), model)

    def generate(
        self, prompt: str, context: Optional[str] = None, **kwargs
    ) -> Optional[str]:
        full_prompt = f"{context}\n{prompt}" if context else prompt
        token_count = count_tokens(full_prompt)
        if token_count > 65536:
            logger.warning(f"Prompt is too long. Token count: {token_count}")
            full_prompt = f"{context[:65536]}\n{prompt}" if context else prompt
            token_count = count_tokens(full_prompt)

        messages = [{"role": "user", "content": [{"text": full_prompt}]}]

        response = self.client.converse(
            modelId=self.model,
            inferenceConfig={
                "maxTokens": kwargs.get("max_tokens", token_count + 100),
                "temperature": kwargs.get("temperature", 0.6),
            },
            messages=messages,
        )

        answer = None
        reasoning = None
        for message in response["output"]["message"]["content"]:
            if "text" in message:
                answer = message["text"]
            elif "reasoningContent" in message:
                reasoning = message["reasoningContent"]["reasoningText"]["text"]
        if reasoning:
            return f"<think>{reasoning}</think>\n{answer}"
        else:
            return answer

    def generate_stream(
        self, prompt: str, context: Optional[str] = None, **kwargs
    ) -> Generator[str, None, None]:
        full_prompt = f"{context}\n{prompt}" if context else prompt
        token_count = count_tokens(full_prompt)
        if token_count > 65536:
            logger.warning(f"Prompt is too long. Token count: {token_count}")
            full_prompt = f"{context[:65536]}\n{prompt}" if context else prompt
            token_count = count_tokens(full_prompt)

        messages = [{"role": "user", "content": [{"text": full_prompt}]}]

        try:
            response_stream = self.client.converse_stream(
                modelId=self.model,
                inferenceConfig={
                    "maxTokens": kwargs.get("max_tokens", token_count + 100),
                    "temperature": kwargs.get("temperature", 0.6),
                },
                messages=messages,
            )

            # The response['stream'] is an iterable
            stream = response_stream.get("stream")
            if stream:
                for event in stream:
                    if "contentBlockStart" in event:
                        # Indicates the start of a new content block
                        # event['contentBlockStart']['start']['text'] could be present for some models/cases
                        logger.debug(
                            f"\nContent block started. Index: {event['contentBlockStart']['contentBlockIndex']}"
                        )

                    elif "contentBlockDelta" in event:
                        # This event provides a delta of the content for a content block.
                        # The actual content is within event['contentBlockDelta']['delta']
                        # For text, it's event['contentBlockDelta']['delta']['text']
                        delta = event["contentBlockDelta"]["delta"]
                        if "text" in delta:
                            yield delta["text"]

                    elif "contentBlockStop" in event:
                        # Indicates the end of a content block
                        logger.debug(
                            f"Content block stopped. Index: {event['contentBlockStop']['contentBlockIndex']}"
                        )

                    elif "messageStop" in event:
                        # Indicates the end of the message from the model
                        # Contains the reason why the message stopped (e.g., 'end_turn', 'tool_use', 'max_tokens')
                        logger.debug(
                            f"Message stopped. Reason: {event['messageStop']['stopReason']}"
                        )

                    elif (
                        "internalServerException" in event
                        or "modelStreamErrorException" in event
                        or "throttlingException" in event
                        or "validationException" in event
                    ):
                        # Handle various error types that can occur during streaming
                        error_key = next(iter(event))  # Gets the top-level error key
                        logger.debug(
                            f"An error occurred during streaming: {error_key}, {event[error_key]}"
                        )
                        break  # Stop processing on error

            else:
                logger.info("No stream returned in the response.")
                yield "Error: No stream returned in the response."

        except boto3.exceptions.Boto3Error as e:  # More specific Boto3 error
            logger.error(f"A Boto3 error occurred: {e}")
            yield f"Error: {str(e)}"
        except Exception as e:
            logger.error(f"Error during Bedrock streaming: {e}")
            yield f"Error: {str(e)}"
