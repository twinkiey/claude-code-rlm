"""
claude-code-rlm: Event system

Translates RLM callbacks into structured JSON events
that can be consumed by the TypeScript layer or displayed
in the terminal.
"""

import json
import sys
import time
from dataclasses import dataclass, asdict
from enum import Enum
from typing import TextIO


class EventType(str, Enum):
    # Lifecycle
    SESSION_START = "session_start"
    SESSION_END = "session_end"

    # RLM processing
    RLM_START = "rlm_start"
    RLM_COMPLETE = "rlm_complete"
    RLM_ERROR = "rlm_error"

    # Iterations
    ITERATION_START = "iteration_start"
    ITERATION_COMPLETE = "iteration_complete"

    # Sub-calls (recursive)
    SUBCALL_START = "subcall_start"
    SUBCALL_COMPLETE = "subcall_complete"

    # Classification
    CLASSIFY_RESULT = "classify_result"

    # Progress
    PROGRESS = "progress"


@dataclass
class Event:
    type: EventType
    timestamp: float
    data: dict

    def to_json(self) -> str:
        return json.dumps({
            "type": self.type.value,
            "timestamp": self.timestamp,
            "data": self.data,
        }, ensure_ascii=False)


class EventEmitter:
    """
    Emits structured events as JSON lines to a stream.

    Used for communication between Python bridge and
    TypeScript plugin layer. Each event is a single
    JSON line on the output stream.

    Protocol:
      {"type": "iteration_start", "timestamp": 1234567890.123, "data": {...}}
    """

    def __init__(self, stream: TextIO | None = None):
        """
        Args:
            stream: output stream for events. Default: sys.stderr
                    (stdout is reserved for final results)
        """
        self._stream = stream or sys.stderr
        self._start_time = time.time()

    def emit(self, event_type: EventType, **data):
        """Emit a single event."""
        event = Event(
            type=event_type,
            timestamp=time.time(),
            data=data,
        )
        try:
            line = event.to_json()
            self._stream.write(line + "\n")
            self._stream.flush()
        except (BrokenPipeError, OSError):
            pass  # Stream closed, silently ignore

    def elapsed(self) -> float:
        """Seconds since emitter was created."""
        return time.time() - self._start_time

    # ── Convenience methods ───────────────────────────────

    def session_start(self, config: dict):
        self.emit(EventType.SESSION_START, config=config)

    def session_end(self, reason: str = "normal"):
        self.emit(EventType.SESSION_END, reason=reason, elapsed=self.elapsed())

    def rlm_start(self, query: str, context_size: int | None = None):
        self.emit(
            EventType.RLM_START,
            query=str(query)[:200],  # Truncate for event
            context_size=context_size,
        )

    def rlm_complete(
        self,
        execution_time: float,
        tokens: int,
        cost: float | None,
        iterations: int | None = None,
    ):
        self.emit(
            EventType.RLM_COMPLETE,
            execution_time=execution_time,
            tokens=tokens,
            cost=cost,
            iterations=iterations,
        )

    def rlm_error(self, error: str, partial_answer: str | None = None):
        self.emit(
            EventType.RLM_ERROR,
            error=error,
            has_partial=partial_answer is not None,
        )

    def classify_result(self, use_rlm: bool, reason: str, confidence: float):
        self.emit(
            EventType.CLASSIFY_RESULT,
            use_rlm=use_rlm,
            reason=reason,
            confidence=confidence,
        )

    def progress(self, message: str, depth: int = 0):
        self.emit(
            EventType.PROGRESS,
            message=message,
            depth=depth,
        )

    # ── RLM Callback factories ────────────────────────────

    def make_callbacks(self) -> dict:
        """
        Create callback functions compatible with RLM constructor.

        Returns:
            dict with keys: on_iteration_start, on_iteration_complete,
                           on_subcall_start, on_subcall_complete
        """
        return {
            "on_iteration_start": self._on_iteration_start,
            "on_iteration_complete": self._on_iteration_complete,
            "on_subcall_start": self._on_subcall_start,
            "on_subcall_complete": self._on_subcall_complete,
        }

    def _on_iteration_start(self, depth: int, iteration_num: int):
        self.emit(
            EventType.ITERATION_START,
            depth=depth,
            iteration=iteration_num,
        )

    def _on_iteration_complete(
        self, depth: int, iteration_num: int, duration: float
    ):
        self.emit(
            EventType.ITERATION_COMPLETE,
            depth=depth,
            iteration=iteration_num,
            duration=round(duration, 2),
        )

    def _on_subcall_start(
        self, depth: int, model: str, prompt_preview: str
    ):
        self.emit(
            EventType.SUBCALL_START,
            depth=depth,
            model=model,
            preview=str(prompt_preview)[:100],
        )

    def _on_subcall_complete(
        self, depth: int, model: str, duration: float, error: str | None
    ):
        self.emit(
            EventType.SUBCALL_COMPLETE,
            depth=depth,
            model=model,
            duration=round(duration, 2),
            error=error,
        )