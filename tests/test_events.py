"""Tests for python/events.py — event system."""

import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python.events import EventEmitter, EventType, Event


class TestEventType:
    """Test event type enum."""

    def test_values_are_strings(self):
        assert EventType.SESSION_START.value == "session_start"
        assert EventType.RLM_COMPLETE.value == "rlm_complete"
        assert EventType.ITERATION_START.value == "iteration_start"

    def test_all_types_exist(self):
        expected = [
            "session_start", "session_end",
            "rlm_start", "rlm_complete", "rlm_error",
            "iteration_start", "iteration_complete",
            "subcall_start", "subcall_complete",
            "classify_result", "progress",
        ]
        actual = [e.value for e in EventType]
        for exp in expected:
            assert exp in actual, f"Missing event type: {exp}"


class TestEvent:
    """Test Event dataclass."""

    def test_to_json(self):
        event = Event(
            type=EventType.RLM_START,
            timestamp=1234567890.123,
            data={"query": "test", "context_size": 5000},
        )
        j = event.to_json()
        parsed = json.loads(j)
        assert parsed["type"] == "rlm_start"
        assert parsed["timestamp"] == 1234567890.123
        assert parsed["data"]["query"] == "test"

    def test_to_json_unicode(self):
        event = Event(
            type=EventType.PROGRESS,
            timestamp=0.0,
            data={"message": "Анализ кода 🔍"},
        )
        j = event.to_json()
        parsed = json.loads(j)
        assert "Анализ" in parsed["data"]["message"]
        assert "🔍" in parsed["data"]["message"]


class TestEventEmitter:
    """Test event emitter."""

    def _make_emitter(self) -> tuple[EventEmitter, io.StringIO]:
        stream = io.StringIO()
        emitter = EventEmitter(stream=stream)
        return emitter, stream

    def _get_events(self, stream: io.StringIO) -> list[dict]:
        stream.seek(0)
        events = []
        for line in stream:
            line = line.strip()
            if line:
                events.append(json.loads(line))
        return events

    def test_emit_basic(self):
        emitter, stream = self._make_emitter()
        emitter.emit(EventType.PROGRESS, message="hello")
        events = self._get_events(stream)
        assert len(events) == 1
        assert events[0]["type"] == "progress"
        assert events[0]["data"]["message"] == "hello"

    def test_emit_has_timestamp(self):
        emitter, stream = self._make_emitter()
        before = time.time()
        emitter.emit(EventType.PROGRESS, message="test")
        after = time.time()
        events = self._get_events(stream)
        assert before <= events[0]["timestamp"] <= after

    def test_session_start(self):
        emitter, stream = self._make_emitter()
        emitter.session_start(config={"model": "test"})
        events = self._get_events(stream)
        assert events[0]["type"] == "session_start"
        assert events[0]["data"]["config"]["model"] == "test"

    def test_rlm_complete(self):
        emitter, stream = self._make_emitter()
        emitter.rlm_complete(
            execution_time=5.5,
            tokens=1000,
            cost=0.05,
            iterations=3,
        )
        events = self._get_events(stream)
        assert events[0]["data"]["execution_time"] == 5.5
        assert events[0]["data"]["tokens"] == 1000
        assert events[0]["data"]["cost"] == 0.05

    def test_classify_result(self):
        emitter, stream = self._make_emitter()
        emitter.classify_result(
            use_rlm=True,
            reason="large context",
            confidence=0.9,
        )
        events = self._get_events(stream)
        assert events[0]["data"]["use_rlm"] is True
        assert events[0]["data"]["confidence"] == 0.9

    def test_elapsed(self):
        emitter, _ = self._make_emitter()
        time.sleep(0.1)
        elapsed = emitter.elapsed()
        assert elapsed >= 0.1

    def test_make_callbacks(self):
        emitter, stream = self._make_emitter()
        callbacks = emitter.make_callbacks()
        assert "on_iteration_start" in callbacks
        assert "on_iteration_complete" in callbacks
        assert "on_subcall_start" in callbacks
        assert "on_subcall_complete" in callbacks

        # Test that callbacks emit events
        callbacks["on_iteration_start"](0, 1)
        callbacks["on_iteration_complete"](0, 1, 2.5)
        callbacks["on_subcall_start"](1, "gpt-4o", "analyze auth")
        callbacks["on_subcall_complete"](1, "gpt-4o", 3.0, None)

        events = self._get_events(stream)
        assert len(events) == 4
        assert events[0]["type"] == "iteration_start"
        assert events[1]["type"] == "iteration_complete"
        assert events[1]["data"]["duration"] == 2.5
        assert events[2]["type"] == "subcall_start"
        assert events[3]["type"] == "subcall_complete"

    def test_multiple_events(self):
        emitter, stream = self._make_emitter()
        for i in range(10):
            emitter.progress(f"Step {i}", depth=0)
        events = self._get_events(stream)
        assert len(events) == 10

    def test_broken_stream(self):
        """Emitter should not crash on broken stream."""

        class BrokenStream:
            def write(self, _):
                raise BrokenPipeError()

            def flush(self):
                raise BrokenPipeError()

        emitter = EventEmitter(stream=BrokenStream())
        # Should not raise
        emitter.emit(EventType.PROGRESS, message="test")