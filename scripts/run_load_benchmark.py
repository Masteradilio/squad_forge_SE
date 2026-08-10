"""Run a bounded HTTP load probe and persist SLO/backpressure evidence."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _request(url: str, timeout: float) -> dict[str, object]:
    started = time.perf_counter()
    try:
        request = Request(url, headers={"Accept": "application/json"})
        with urlopen(request, timeout=timeout) as response:
            response.read(1024)
            return {"status": response.status, "latency_ms": round((time.perf_counter() - started) * 1000, 3)}
    except HTTPError as exc:
        return {"status": exc.code, "latency_ms": round((time.perf_counter() - started) * 1000, 3), "error": "http"}
    except (URLError, TimeoutError, OSError) as exc:
        return {"status": 0, "latency_ms": round((time.perf_counter() - started) * 1000, 3), "error": type(exc).__name__}


def run_probe(url: str, requests: int, concurrency: int, timeout: float) -> dict[str, object]:
    started = time.perf_counter()
    results: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = [pool.submit(_request, url, timeout) for _ in range(max(1, requests))]
        for future in as_completed(futures):
            results.append(future.result())
    latencies = [float(item["latency_ms"]) for item in results]
    statuses = [int(item["status"]) for item in results]
    successful = sum(status == 200 for status in statuses)
    p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies, default=0.0)
    return {
        "schema": "forgeos.load_benchmark.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "url": url,
        "requests": len(results),
        "concurrency": concurrency,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "successful_responses": successful,
        "status_counts": {str(status): statuses.count(status) for status in sorted(set(statuses))},
        "latency_ms": {"min": min(latencies, default=0.0), "median": statistics.median(latencies) if latencies else 0.0, "p95": round(p95, 3), "max": max(latencies, default=0.0)},
        "status": "PASS" if successful == len(results) else "PARTIAL",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000/ready")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--output", type=Path, default=Path(".localforge/artifacts/load/load_benchmark.json"))
    args = parser.parse_args()
    if args.requests < 1 or args.requests > 1000 or args.concurrency < 1 or args.concurrency > 32:
        parser.error("requests must be 1..1000 and concurrency must be 1..32")
    payload = run_probe(args.url, args.requests, args.concurrency, args.timeout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
