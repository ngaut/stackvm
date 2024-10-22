import json
from dataclasses import dataclass
from enum import Enum
from typing import Union, Optional, List


# Chat stream response event types
class EventType(str, Enum):
    TEXT_PART = "0"
    DATA_PART = "2"
    ERROR_PART = "3"
    MESSAGE_ANNOTATION_PART = "8"
    TOOL_CALL_PART = "9"
    TOOL_RESULT_PART = "a"
    STEP_FINISH_PART = "e"
    FINISH_MESSAGE_PART = "d"


@dataclass
class ExecutionEvent:
    event_type: EventType
    payload: str| dict | list| None= None

    def encode(self, charset: str = 'utf-8') -> bytes:
        body = self.payload
        body = json.dumps(body, separators=(",", ":"))
        return f"{self.event_type.value}:{body}\n".encode(charset)


class StreamingProtocol:
    """
    Implements the streaming protocol for transporting chat events using Vercel AI SDK Data Stream Protocol.
    """

    def __init__(self):
        self.events: List[bytes] = []

    def send_text_part(self, text: str):
        event = ExecutionEvent(event_type=EventType.TEXT_PART, payload=text)
        event_bytes = event.encode()
        self.events.append(event_bytes)
        return event_bytes

    def send_data_part(self, data: str):
        event = ExecutionEvent(event_type=EventType.DATA_PART, payload=data)
        event_bytes = event.encode()
        self.events.append(event_bytes)
        return event_bytes

    def send_plan(self, plan: list):
        event = ExecutionEvent(event_type=EventType.MESSAGE_ANNOTATION_PART, payload=plan)
        event_bytes = event.encode()
        self.events.append(event_bytes)
        return event_bytes

    def send_tool_call(self, tool_name: str, input: dict):
        event = ExecutionEvent(event_type=EventType.TOOL_CALL_PART, payload={
            "tool": tool_name,
            "input": input
        })
        event_bytes = event.encode()
        self.events.append(event_bytes)
        return event_bytes

    def send_tool_result(self, tool_name: str, input: dict, result: dict):
        event = ExecutionEvent(event_type=EventType.TOOL_RESULT_PART, payload={
            "tool": tool_name,
            "input": input,
            "result": result
        })
        event_bytes = event.encode()
        self.events.append(event_bytes)
        return event_bytes

    def send_state(self, state: dict):
        event = ExecutionEvent(event_type=EventType.MESSAGE_ANNOTATION_PART, payload={
            "state": state
        })
        event_bytes = event.encode()
        self.events.append(event_bytes)
        return event_bytes

    def send_step_finish(self, step: int, reason: str = 'stop'):
        payload = {
            "step": step,
            "finishReason": reason,
            "usage":{
                "promptTokens": 0,
                "completionTokens": 0
            }
        }
        event = ExecutionEvent(event_type=EventType.STEP_FINISH_PART, payload=payload)
        event_bytes = event.encode()
        self.events.append(event_bytes)
        return event_bytes

    def send_finish_message(self, reason: str = "stop"):
        payload = {
            "finishReason": reason,
            "usage":{
                "promptTokens": 0,
                "completionTokens": 0
            }
        }
        event = ExecutionEvent(event_type=EventType.FINISH_MESSAGE_PART, payload=payload)
        event_bytes = event.encode()
        self.events.append(event_bytes)
        return event_bytes

    def send_error(self, error: str):
        event = ExecutionEvent(event_type=EventType.ERROR_PART, payload=error)
        event_bytes = event.encode()
        self.events.append(event_bytes)
        return event_bytes

    def get_stream(self) -> bytes:
        """
        Concatenates all encoded events into a single byte stream.
        """
        stream = b''.join(self.events)
        self.events.clear()  # Clear events after streaming
        return stream
