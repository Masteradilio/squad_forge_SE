"""OpenTelemetry Tracing Collector — Records agent execution latencies, tool calls & telemetry timeline."""

import time
from typing import Any
from uuid import uuid4

import pydantic


class TraceSpan(pydantic.BaseModel):
    span_id: str
    role_name: str
    action_name: str
    start_time: float
    end_time: float | None = None
    duration_ms: float | None = None
    tool_calls: list[str] = pydantic.Field(default_factory=list)
    status: str = "IN_PROGRESS"


class OpenTelemetryTracer:
    """Asynchronous tracer capturing execution spans for visual timeline in UI."""

    def __init__(self):
        self.spans: list[TraceSpan] = []

    def start_span(self, role_name: str, action_name: str) -> TraceSpan:
        """Start a telemetry trace span for a Squad role."""
        span_id = f"span_{role_name.lower().replace(' ', '_')}_{uuid4().hex}"
        span = TraceSpan(
            span_id=span_id,
            role_name=role_name,
            action_name=action_name,
            start_time=time.time(),
        )
        self.spans.append(span)
        return span

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
