import faulthandler
import os
import platform
import sys
import threading
import tracemalloc
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from typing import Any, TextIO

import pytest
import pytest_asyncio
from localforge.storage.bootstrap import bootstrap_database
from localforge.storage.database import DatabaseManager
from sqlalchemy.ext.asyncio import AsyncSession

_DEBUG_LOG_ENV = "LOCALFORGE_TEST_DEBUG_LOG"
_DEBUG_TRACEMALLOC_ENV = "LOCALFORGE_TEST_DEBUG_TRACEMALLOC"
_debug_file: TextIO | None = None
_debug_stop = threading.Event()
_debug_thread: threading.Thread | None = None
_debug_current_test = "<session>"


def _debug_log_path() -> str | None:
    value = os.getenv(_DEBUG_LOG_ENV)
    if not value:
        return None
    if value == "1":
        return os.path.abspath("debug.log")
    return os.path.abspath(value)


def _win_process_memory() -> dict[str, int]:
    if os.name != "nt":
        return {}
    try:
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        win_dll = ctypes.__dict__["WinDLL"]
        ok = win_dll("psapi.dll").GetProcessMemoryInfo(
            win_dll("kernel32.dll").GetCurrentProcess(),
            ctypes.byref(counters),
            counters.cb,
        )
        if not ok:
            return {}
        return {
            "rss": int(counters.WorkingSetSize),
            "rss_peak": int(counters.PeakWorkingSetSize),
            "pagefile": int(counters.PagefileUsage),
            "pagefile_peak": int(counters.PeakPagefileUsage),
        }
    except Exception:
        return {}


def _win_system_memory() -> dict[str, int]:
    if os.name != "nt":
        return {}
    try:
        import ctypes
        from ctypes import wintypes

        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(status)
        win_dll = ctypes.__dict__["WinDLL"]
        ok = win_dll("kernel32.dll").GlobalMemoryStatusEx(ctypes.byref(status))
        if not ok:
            return {}
        return {
            "memory_load_pct": int(status.dwMemoryLoad),
            "phys_total": int(status.ullTotalPhys),
            "phys_avail": int(status.ullAvailPhys),
            "page_total": int(status.ullTotalPageFile),
            "page_avail": int(status.ullAvailPageFile),
        }
    except Exception:
        return {}


def _debug_metrics() -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "pid": os.getpid(),
        "threads": threading.active_count(),
    }
    if tracemalloc.is_tracing():
        current, peak = tracemalloc.get_traced_memory()
        metrics["tracemalloc_current"] = current
        metrics["tracemalloc_peak"] = peak
    metrics.update({f"proc_{k}": v for k, v in _win_process_memory().items()})
    metrics.update({f"sys_{k}": v for k, v in _win_system_memory().items()})
    return metrics


def _debug_write(event: str, **fields: Any) -> None:
    if _debug_file is None:
        return
    payload = {
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds") + "Z",
        "event": event,
        "current_test": _debug_current_test,
        **fields,
        **_debug_metrics(),
    }
    line = " ".join(f"{key}={value!r}" for key, value in payload.items())
    _debug_file.write(line + "\n")
    _debug_file.flush()
    os.fsync(_debug_file.fileno())


def _debug_heartbeat() -> None:
    tick = 0
    while not _debug_stop.wait(1.0):
        tick += 1
        thread_names = [thread.name for thread in threading.enumerate()]
        _debug_write("HEARTBEAT", tick=tick, thread_names=thread_names)


def pytest_sessionstart(session: pytest.Session) -> None:
    global _debug_file, _debug_thread
    log_path = _debug_log_path()
    if not log_path:
        return
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    _debug_file = open(log_path, "w", encoding="utf-8", buffering=1)
    if os.getenv(_DEBUG_TRACEMALLOC_ENV):
        tracemalloc.start(10)
    faulthandler.enable(file=_debug_file, all_threads=True)
    faulthandler.dump_traceback_later(15.0, repeat=True, file=_debug_file)
    _debug_stop.clear()
    _debug_thread = threading.Thread(
        target=_debug_heartbeat,
        name="localforge-test-debug-heartbeat",
        daemon=True,
    )
    _debug_thread.start()
    _debug_write(
        "SESSION_START",
        argv=sys.argv,
        cwd=os.getcwd(),
        python=sys.version,
        platform=platform.platform(),
        log_path=log_path,
    )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    global _debug_file, _debug_thread
    _debug_write("SESSION_FINISH", exitstatus=exitstatus)
    _debug_stop.set()
    if _debug_thread is not None:
        _debug_thread.join(timeout=2.0)
        _debug_thread = None
    if _debug_file is not None:
        faulthandler.cancel_dump_traceback_later()
        faulthandler.disable()
        _debug_file.flush()
        os.fsync(_debug_file.fileno())
        _debug_file.close()
        _debug_file = None


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    _debug_write(
        "TEST_REPORT",
        nodeid=report.nodeid,
        phase=report.when,
        outcome=report.outcome,
        duration=round(report.duration, 6),
    )


@pytest.fixture(autouse=True)
def _debug_test_scope(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    global _debug_current_test
    previous = _debug_current_test
    _debug_current_test = request.node.nodeid
    _debug_write("TEST_ENTER", nodeid=request.node.nodeid)
    try:
        yield
    finally:
        _debug_write("TEST_EXIT", nodeid=request.node.nodeid)
        _debug_current_test = previous


def pytest_runtest_setup(item: pytest.Item) -> None:
    global _debug_current_test
    _debug_current_test = item.nodeid
    _debug_write("TEST_SETUP_START", nodeid=item.nodeid)


def pytest_runtest_call(item: pytest.Item) -> None:
    global _debug_current_test
    _debug_current_test = item.nodeid
    _debug_write("TEST_CALL_START", nodeid=item.nodeid)


def pytest_runtest_teardown(item: pytest.Item) -> None:
    global _debug_current_test
    _debug_current_test = item.nodeid
    _debug_write("TEST_TEARDOWN_START", nodeid=item.nodeid)


@pytest.fixture
def anyio_backend() -> str:
    """Run async tests only on asyncio, which is the runtime used by LocalForge."""
    return "asyncio"


@pytest_asyncio.fixture
async def db_manager():
    """Fixture providing an isolated DatabaseManager backed by an in-memory SQLite DB."""
    _debug_write("DB_MANAGER_CREATE_START")
    manager = DatabaseManager("sqlite+aiosqlite:///:memory:")
    # Bootstrap the tables
    await bootstrap_database(manager)
    _debug_write("DB_MANAGER_BOOTSTRAPPED", manager_id=id(manager))
    yield manager
    _debug_write("DB_MANAGER_CLOSE_START", manager_id=id(manager))
    await manager.close()
    _debug_write("DB_MANAGER_CLOSE_DONE", manager_id=id(manager))


@pytest_asyncio.fixture
async def db_session(db_manager) -> AsyncGenerator[AsyncSession, None]:
    """Fixture providing a transactional AsyncSession for each test."""
    _debug_write("DB_SESSION_OPEN_START", manager_id=id(db_manager))
    async with await db_manager.get_session() as session:
        _debug_write("DB_SESSION_OPEN_DONE", session_id=id(session))
        yield session
        # Session rollback is implicitly handled on exit/failure by SQLAlchemy,
        # but since we are testing CRUD we want to ensure transactions clean up.
        _debug_write("DB_SESSION_ROLLBACK_START", session_id=id(session))
        await session.rollback()
        _debug_write("DB_SESSION_ROLLBACK_DONE", session_id=id(session))
