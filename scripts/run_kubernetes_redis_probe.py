"""Run Redis capability checks from the ForgeOS backend Pod."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path


POD_PROBE = r'''
import asyncio, json, time, uuid
from localforge.services.redis_manager import RedisManager

async def main():
    manager = RedisManager()
    peer = RedisManager()
    key = "forgeos:compliance:" + uuid.uuid4().hex
    client = await manager._get_client()
    if client is None:
        print(json.dumps({"status":"BLOCKED","available":False}))
        return
    cache_ok = await manager.set(key + ":cache", "ok", ttl_seconds=20) and await manager.get(key + ":cache") == "ok"
    channel = key + ":events"
    subscriber = client.pubsub()
    await subscriber.subscribe(channel)
    await manager.publish(channel, "event")
    pubsub_ok = False
    deadline = asyncio.get_running_loop().time() + 2
    while asyncio.get_running_loop().time() < deadline:
        message = await subscriber.get_message(ignore_subscribe_messages=True, timeout=0.2)
        if message and message.get("data") == "event":
            pubsub_ok = True
            break
        await asyncio.sleep(0.05)
    await subscriber.unsubscribe(channel)
    await subscriber.close()
    async with manager.acquire_lock(key + ":lock", timeout_seconds=3) as first:
        async with peer.acquire_lock(key + ":lock", timeout_seconds=3) as second:
            lock_exclusive = bool(first) and not bool(second)
    async with manager.acquire_lock(key + ":lease", timeout_seconds=1) as first:
        await asyncio.sleep(1.2)
    async with peer.acquire_lock(key + ":lease", timeout_seconds=1) as after_expiry:
        lease_expiry = bool(first) and bool(after_expiry)
    unavailable = RedisManager(redis_url="redis://127.0.0.1:63999/0")
    fail_closed = await unavailable._get_client() is None and not unavailable.is_available
    await unavailable.close()
    await manager.close()
    await peer.close()
    checks = {"cache": cache_ok, "pubsub": pubsub_ok, "lock_exclusive": lock_exclusive, "lease_expiry": lease_expiry, "fail_closed": fail_closed}
    print(json.dumps({"status":"PASS" if all(checks.values()) else "BLOCKED", "available":True, "checks":checks}, indent=2))

asyncio.run(main())
'''


def run(output: Path, *, namespace: str, deployment: str) -> int:
    kubectl = shutil.which("kubectl") or shutil.which("kubectl.exe")
    if not kubectl:
        raise SystemExit("kubectl is required for an in-cluster Redis probe")
    completed = subprocess.run(
        [kubectl, "exec", "-i", "-n", namespace, f"deploy/{deployment}", "--", "python", "-"],
        input=POD_PROBE,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        payload = {"schema": "forgeos.kubernetes_redis_compliance.v1", "status": "NOT_PROVEN", "stderr": completed.stderr[-4000:]}
    else:
        payload = json.loads(completed.stdout)
        payload["schema"] = "forgeos.kubernetes_redis_compliance.v1"
        payload["generated_at"] = datetime.now(UTC).isoformat()
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

