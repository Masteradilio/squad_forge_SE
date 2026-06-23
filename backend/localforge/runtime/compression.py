import hashlib


def compress_tool_output(text: str, *, max_chars: int = 1_000) -> str:
    """Bound old tool output while keeping traceability metadata."""
    if len(text) <= max_chars:
        return text
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    head_budget = max(80, max_chars // 2)
    tail_budget = max(80, max_chars - head_budget - 120)
    return (
        f"[compressed output sha256={digest} original_chars={len(text)}]\n"
        f"{text[:head_budget].rstrip()}\n"
        "[...compressed...]\n"
        f"{text[-tail_budget:].lstrip()}"
    )
