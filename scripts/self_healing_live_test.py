"""Live self-healing test: induce a real Redis outage, observe detection + recovery.

Sequence (all against the running API at :8000):
 1. run a healing cycle with Redis up            -> redis CLOSED, samples > 0
 2. stop the Redis process (real outage)          -> probe fails repeatedly
 3. healing cycle                                  -> redis OPEN, degraded, escalated (no fake fix)
 4. self_model                                     -> realtime_streaming reports degraded
 5. restart Redis, healing cycle                   -> probe succeeds, breaker CLOSED (self-healed)
 6. self_model                                     -> operational again
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
_DEFAULT_H = {"Content-Type": "application/json", "X-Friday-Api-Key": "friday-service-token-for-local-pressure-testing"}


def _resolve_friday_headers() -> dict[str, str]:
    """Probe once for a FRIDAY credential this API accepts, then fall back to the
    development bypass (no header). A hardcoded key that the API rejects made
    every call 401 and crashed the script on the error body (same pattern fixed
    in scripts/self_integrity_live_test.py)."""
    try:
        req = urllib.request.Request(BASE + "/v1/friday/self_model", headers=_DEFAULT_H, method="GET")
        with urllib.request.urlopen(req, timeout=10) as response:
            response.read()
            return _DEFAULT_H
    except urllib.error.HTTPError:
        pass
    req = urllib.request.Request(BASE + "/v1/friday/self_model", method="GET")
    with urllib.request.urlopen(req, timeout=10) as response:
        response.read()
        return {"Content-Type": "application/json"}


H = _resolve_friday_headers()


def call(method: str, path: str, body: dict | None = None) -> tuple[int, dict | str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=H, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.status, json.loads(response.read().decode() or "null")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:300]


def redis_state() -> dict:
    _status, snapshot = call("GET", "/v1/friday/self_healing")
    circuit = snapshot["subsystems"]["redis"]
    return {
        "state": circuit["state"],
        "samples": circuit["samples"],
        "consecutive_failures": circuit["consecutive_failures"],
        "outage_for": circuit["outage_for_seconds"],
    }


def step(label: str) -> None:
    print(f"\n── {label} ──")


step("1. baseline: Redis up, probe observes a healthy sample")
call("POST", "/v1/friday/self_healing/run", {})
print("   redis circuit:", redis_state())

step("2. induce a REAL outage: stop the Redis process")
subprocess.run(["pkill", "-f", "dev_redis.py"], check=False)
time.sleep(1.5)
for _ in range(4):
    call("POST", "/v1/friday/self_healing/run", {})  # repeated probe failures trip the breaker
print("   redis circuit:", redis_state())

step("3. self-healing cycle during the outage (must DETECT, keep repairs bounded by cooldown)")
_status, run = call("POST", "/v1/friday/self_healing/run", {})
print("   checked:", run["checked"])
print("   unhealthy:", run["unhealthy"])
print("   repairs:")
for repair in run["repairs"]:
    print("     ", repair)
print("   escalated:", run["escalated"])

step("4. self-model while degraded (must not claim operational)")
_status, model = call("GET", "/v1/friday/self_model")
print("   realtime_streaming:", model["capabilities"]["realtime_streaming"])
print("   gaps:", model["gaps"])

step("5. restore Redis and let self-healing verify the repair")
import os

subprocess.Popen(
    [
        sys.executable,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "dev_redis.py"),
        "--host",
        "0.0.0.0",
        "--port",
        "6379",
    ],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
time.sleep(3)
for attempt in range(6):
    _status, run = call("POST", "/v1/friday/self_healing/run", {})
    state = redis_state()
    print(f"   attempt {attempt + 1}: {state} | repaired={run['repaired']} escalated={run['escalated']}")
    if state["state"] == "CLOSED":
        break
    time.sleep(2)

step("6. self-model after recovery")
_status, model = call("GET", "/v1/friday/self_model")
print("   realtime_streaming:", model["capabilities"]["realtime_streaming"])
print("   gaps:", model["gaps"])

# The live API must still be serving while all of this happened.
_status, health = call("GET", "/v1/health")
print("\nAPI liveness during/after the outage:", health if isinstance(health, str) else health.get("status"))
sys.exit(0)
