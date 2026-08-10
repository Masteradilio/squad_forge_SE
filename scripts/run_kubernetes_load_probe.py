"""Run bounded small/medium/sustained HTTP probes from a Kubernetes Pod."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path


POD_PROBE = r'''
import concurrent.futures, json, statistics, time, urllib.request

def probe(url, requests, concurrency):
    def one(_):
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                response.read(256)
                return response.status, (time.perf_counter() - started) * 1000
        except Exception:
            return 0, (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(one, range(requests)))
    latencies = [item[1] for item in results]
    statuses = [item[0] for item in results]
    return {
        "requests": requests,
        "concurrency": concurrency,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "successful_responses": sum(status == 200 for status in statuses),
        "status_counts": {str(status): statuses.count(status) for status in sorted(set(statuses))},
        "latency_ms": {
            "min": round(min(latencies, default=0), 3),
            "median": round(statistics.median(latencies) if latencies else 0, 3),
            "p95": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)] if latencies else 0, 3),
            "max": round(max(latencies, default=0), 3),
        },
        "status": "PASS" if all(status == 200 for status in statuses) else "PARTIAL",
    }

url = "http://forgeos-forgeos-cloud-backend:8000/ready"
levels = {
    "small": probe(url, 10, 2),
    "medium": probe(url, 60, 8),
    "sustained": probe(url, 200, 16),
}
unavailable = probe("http://forgeos-forgeos-cloud-backend-missing:8000/ready", 2, 1)
print(json.dumps({"url": url, "levels": levels, "unavailable_dependency": unavailable}, indent=2))
'''


def run(output: Path, *, namespace: str, deployment: str) -> int:
    kubectl = shutil.which("kubectl") or shutil.which("kubectl.exe")
    if not kubectl:
        raise SystemExit("kubectl is required for an in-cluster load probe")
    completed = subprocess.run(
        [kubectl, "exec", "-i", "-n", namespace, f"deploy/{deployment}", "--", "python", "-"],
        input=POD_PROBE,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    if completed.returncode != 0:
        payload = {"schema": "forgeos.kubernetes_load_compliance.v1", "status": "NOT_PROVEN", "stderr": completed.stderr[-4000:]}
    else:
        payload = json.loads(completed.stdout)
        payload["schema"] = "forgeos.kubernetes_load_compliance.v1"
        payload["generated_at"] = datetime.now(UTC).isoformat()
        payload["status"] = "PASS" if all(item["status"] == "PASS" for item in payload["levels"].values()) and payload["unavailable_dependency"]["successful_responses"] == 0 else "PARTIAL"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--namespace", default="forgeos")
    parser.add_argument("--deployment", default="forgeos-forgeos-cloud-backend")
    args = parser.parse_args()
    raise SystemExit(run(args.output, namespace=args.namespace, deployment=args.deployment))

