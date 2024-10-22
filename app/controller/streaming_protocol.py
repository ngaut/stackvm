 
import json
from dataclasses import dataclass
from enum import Enum
from typing import Union, Optional, List


# Chat stream response event types
class EventType(str, Enum):
    TEXT_PART = "0"
    DATA_PART = "2"
    ERROR_PART = "3"
    MESSAGE_ANNOTATION_PART = "6"
    TOOL_CALL_PART = "9"
    TOOL_RESULT_PART = "a"
    STEP_FINISH_PART = "e"
    FINISH_MESSAGE_PART = "d"
    EXECUTION_STEP_ANNOTATIONS_PART = "8"  # Existing event type


class ExecutionStep(int, Enum):
    PLAN_GENERATION = 0
    CALLING = 1
    GENERATE_ANSWER = 2
    FINISHED = 3


class StreamPayload:
    def dump(self) -> Union[dict, str]:
        raise NotImplementedError("Must implement dump method")


@dataclass
class TextPayload(StreamPayload):
    text: str

    def dump(self) -> str:
        return self.text


@dataclass
class DataPayload(StreamPayload):
    step: ExecutionStep
    display: str = ""
    context: Union[dict, list, str] = ""
    data: str = ""

    def dump(self) -> List[dict]:
        return [
            {
                "step": self.step.name,
                "display": self.display,
                "context": self.context,
                "data": self.data,
            }
        ]


@dataclass
class MessageAnnotationPayload(StreamPayload):
    annotation: dict

    def dump(self) -> dict:
        return self.annotation


@dataclass
class ToolCallPayload(StreamPayload):
    tool: str
    input: dict

    def dump(self) -> dict:
        return {
            "tool": self.tool,
            "input": self.input
        }


@dataclass
class ToolResultPayload(StreamPayload):
    tool: str
    input: dict
    result: dict

    def dump(self) -> dict:
        return {
            "tool": self.tool,
            "input": self.input,
            "result": self.result
        }


@dataclass
class StepFinishPayload(StreamPayload):
    step: ExecutionStep

    def dump(self) -> dict:
        return {"step_no": self.step.name}


@dataclass
class FinishMessagePayload(StreamPayload):
    final_answer: str

    def dump(self) -> str:
        return self.final_answer


@dataclass
class ExecutionEvent:
    event_type: EventType
    payload: Optional[StreamPayload] = None

    def encode(self, charset: str = 'utf-8') -> bytes:
        if self.payload:
            body = self.payload.dump()
        else:
            body = ""
        body = json.dumps(body, separators=(",", ":")) if body else ""
        return f"{self.event_type.value}:{body}\n".encode(charset)


class StreamingProtocol:
    """
    Implements the streaming protocol for transporting chat events using Vercel AI SDK Data Stream Protocol.
    """

    def __init__(self):
        self.events: List[bytes] = []

    def send_text_part(self, text: str):
        payload = TextPayload(text=text)
        event = ExecutionEvent(event_type=EventType.TEXT_PART, payload=payload)
        self.events.append(event.encode())
        return event

    def send_data_part(self, step: ExecutionStep, display: str = "", context: Union[dict, list, str] = "", data: str = ""):
        payload = DataPayload(step=step, display=display, context=context, data=data)
        event = ExecutionEvent(event_type=EventType.DATA_PART, payload=payload)
        self.events.append(event.encode())
        return event
    def send_message_annotation(self, annotation: dict):
        payload = MessageAnnotationPayload(annotation=annotation)
        event = ExecutionEvent(event_type=EventType.MESSAGE_ANNOTATION_PART, payload=payload)
        self.events.append(event.encode())
        return event

    def send_tool_call(self, tool_name: str, input: dict):
        payload = ToolCallPayload(tool=tool_name, input=input)
        event = ExecutionEvent(event_type=EventType.TOOL_CALL_PART, payload=payload)
        self.events.append(event.encode())
        return event
    def send_tool_result(self, tool_name: str, input: dict, result: dict):
        payload = ToolResultPayload(tool=tool_name, input=input, result=result)
        event = ExecutionEvent(event_type=EventType.TOOL_RESULT_PART, payload=payload)
        self.events.append(event.encode())
        return event

    def send_step_finish(self, step: ExecutionStep):
        payload = StepFinishPayload(step=step)
        event = ExecutionEvent(event_type=EventType.STEP_FINISH_PART, payload=payload)
        self.events.append(event.encode())
        return event

    def send_finish_message(self, final_answer: str):
        payload = FinishMessagePayload(final_answer=final_answer)
        event = ExecutionEvent(event_type=EventType.FINISH_MESSAGE_PART, payload=payload)
        self.events.append(event.encode())
        return event

    def send_error(self, error: dict):
        payload = ErrorPayload(error=error)
        event = ExecutionEvent(event_type=EventType.ERROR_PART, payload=payload)
        self.events.append(event.encode())
        return event
    def get_stream(self) -> bytes:
        """
        Concatenates all encoded events into a single byte stream.
        """
        stream = b''.join(self.events)
        self.events.clear()  # Clear events after streaming
        return stream
