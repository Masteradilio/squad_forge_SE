"""OpenTelemetry Tracing Collector — Records agent execution latencies, tool calls & telemetry timeline."""

import time
from typing import Any
from uuid import uuid4

import pydantic


class TraceSpan(pydantic.BaseModel):
    span_id: str
    role_name: str
    action_name: str
    parent_span_id: str | None = None
    root_span_id: str | None = None
    start_time: float
    end_time: float | None = None
    duration_ms: float | None = None
    tool_calls: list[str] = pydantic.Field(default_factory=list)
    metadata: dict[str, Any] = pydantic.Field(default_factory=dict)
    status: str = "IN_PROGRESS"


class TraceEvent(pydantic.BaseModel):
    """Ordered lifecycle event emitted by the shared Agent Harness."""

    event_id: str
    event_type: str
    span_id: str
    root_span_id: str
    role_name: str
    action_name: str
    timestamp: float
    payload: dict[str, Any] = pydantic.Field(default_factory=dict)


class OpenTelemetryTracer:
    """Asynchronous tracer capturing execution spans for visual timeline in UI."""

    def __init__(self):
        self.spans: list[TraceSpan] = []
        self.events: list[TraceEvent] = []

    def start_span(
        self,
        role_name: str,
        action_name: str,
        *,
        parent_span_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TraceSpan:
        """Start a telemetry trace span for a Squad role."""
        span_id = f"span_{role_name.lower().replace(' ', '_')}_{uuid4().hex}"
        parent = next((item for item in self.spans if item.span_id == parent_span_id), None)
        span = TraceSpan(
            span_id=span_id,
            role_name=role_name,
            action_name=action_name,
            parent_span_id=parent_span_id,
            root_span_id=(parent.root_span_id or parent.span_id) if parent else span_id,
            start_time=time.time(),
            metadata=dict(metadata or {}),
        )
        self.spans.append(span)
        return span

    def emit_event(
        self,
        event_type: str,
        *,
        span_id: str,
        payload: dict[str, Any] | None = None,
    ) -> TraceEvent:
        """Append one lifecycle event while retaining span ordering."""

        span = next((item for item in self.spans if item.span_id == span_id), None)
        if span is None:
            raise ValueError(f"Unknown trace span: {span_id}")
        event = TraceEvent(
            event_id=f"trace_event_{uuid4().hex}",
            event_type=event_type,
            span_id=span.span_id,
            root_span_id=span.root_span_id or span.span_id,
            role_name=span.role_name,
            action_name=span.action_name,
            timestamp=time.time(),
            payload=dict(payload or {}),
        )
        self.events.append(event)
        return event

    def end_span(self, span_id: str, tool_calls: list[str] | None = None, status: str = "SUCCESS") -> TraceSpan | None:
        """End a telemetry span and compute latency duration."""
        for span in self.spans:
            if span.span_id == span_id:
                span.end_time = time.time()
                span.duration_ms = round((span.end_time - span.start_time) * 1000, 2)
                if tool_calls:
                    span.tool_calls.extend(tool_calls)
                span.status = status
                return span
        return None

    def get_timeline(self) -> list[dict[str, Any]]:
        """Return full execution timeline for UI display."""
        return [span.model_dump() for span in self.spans]

    def get_events(self) -> list[dict[str, Any]]:
        """Return ordered agent lifecycle events for API/SSE consumers."""
        return [event.model_dump() for event in self.events]

    def clear(self) -> None:
        """Reset spans and lifecycle events for a new local run."""
        self.spans.clear()
        self.events.clear()
