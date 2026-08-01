"""OpenTelemetry Tracing Collector — Records agent execution latencies, tool calls & telemetry timeline."""

import time
from typing import Any, Dict, List, Optional
import pydantic


class TraceSpan(pydantic.BaseModel):
    span_id: str
    role_name: str
    action_name: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    tool_calls: List[str] = []
    status: str = "IN_PROGRESS"


class OpenTelemetryTracer:
    """Asynchronous tracer capturing execution spans for visual timeline in UI."""

    def __init__(self):
        self.spans: List[TraceSpan] = []

    def start_span(self, role_name: str, action_name: str) -> TraceSpan:
        """Start a telemetry trace span for a Squad role."""
        span_id = f"span_{role_name.lower().replace(' ', '_')}_{int(time.time() * 1000)}"
        span = TraceSpan(
            span_id=span_id,
            role_name=role_name,
            action_name=action_name,
            start_time=time.time(),
        )
        self.spans.append(span)
        return span

    def end_span(self, span_id: str, tool_calls: Optional[List[str]] = None, status: str = "SUCCESS") -> Optional[TraceSpan]:
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

    def get_timeline(self) -> List[Dict[str, Any]]:
        """Return full execution timeline for UI display."""
        return [span.model_dump() for span in self.spans]
