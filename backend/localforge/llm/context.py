from contextvars import ContextVar

# ContextVar tracking the active task_run_id in the execution thread/context
active_task_run_id: ContextVar[int | None] = ContextVar("active_task_run_id", default=None)

# Thread-safe dictionary tracking the count of LLM calls per task run
# Key: task_run_id (int), Value: call_count (int)
_llm_call_counters: dict[int, int] = {}


def get_active_task_run_id() -> int | None:
    """Retrieve the current task run ID from the active context."""
    return active_task_run_id.get()


def set_active_task_run_id(task_run_id: int | None) -> None:
    """Set the current task run ID in the active context."""
    active_task_run_id.set(task_run_id)


def reset_llm_call_counter(task_run_id: int) -> None:
    """Reset the LLM call counter for a specific task run."""
    _llm_call_counters[task_run_id] = 0


def get_llm_call_count(task_run_id: int) -> int:
    """Get the current LLM call count for a specific task run."""
    return _llm_call_counters.get(task_run_id, 0)


_llm_limits: dict[int, int] = {}


def set_llm_limit(task_run_id: int, limit: int) -> None:
    """Set custom LLM call limit for a specific task run."""
    _llm_limits[task_run_id] = limit


def get_llm_limit(task_run_id: int, default_limit: int = 50) -> int:
    """Get LLM call limit for a specific task run."""
    return _llm_limits.get(task_run_id, default_limit)


async def check_and_increment_llm_calls(task_run_id: int, limit: int) -> None:
    """Increment the LLM call counter for a task run.

    Raises ValueError if the limit is exceeded.
    """
    current = _llm_call_counters.get(task_run_id, 0)
    if current >= limit:
        raise ValueError(
            f"Task run {task_run_id} exceeded maximum LLM call budget of {limit} calls."
        )
    _llm_call_counters[task_run_id] = current + 1
