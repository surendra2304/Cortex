#!/usr/bin/env python
"""Live proof that escalations reach a real operator channel — or say they could not.

Starts a real HTTP receiver on localhost, points a supervisor's EscalationNotifier at it, and
forces a subsystem to fail past its repair budget. Asserts:

* with a channel configured the escalation arrives with the right JSON,
* a repeated escalation for the same subsystem+reason is suppressed (no operator spam),
* a *different* escalation still goes through,
* with no channel configured the record says "no escalation channel configured" instead of
  pretending a notification happened,
* a receiver that returns 500 is reported as not delivered with the status code.

Usage: python scripts/escalation_delivery_live_test.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

_root = os.path.abspath(".")
sys.path.insert(0, _root)
for _name in sorted(os.listdir(os.path.join(_root, "packages"))):
    _path = os.path.join(_root, "packages", _name, "src")
    if os.path.isdir(_path):
        sys.path.insert(0, _path)

from cortex_core.resilience import EscalationNotifier, HealthRegistry, SelfHealingSupervisor  # noqa: E402

received: list[dict] = []
fail_next = {"value": False}


class _Receiver(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        try:
            received.append(json.loads(body or b"{}"))
        except json.JSONDecodeError:
            received.append({"_raw": body.decode("utf-8", "replace")})
        if fail_next["value"]:
            self.send_response(500)
        else:
            self.send_response(204)
        self.end_headers()

    def log_message(self, *args) -> None:  # silence the default stderr logging
        return


results: list[tuple[bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((ok, name))
    print(f"   {'[PASS]' if ok else '[FAIL]'} {name}" + (f" — {detail}" if detail else ""))
    return ok


async def main_async(port: int) -> int:
    print("\n── 1. a real HTTP receiver is listening ──")
    server = HTTPServer(("127.0.0.1", port), _Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    check("receiver started", server.server_address[1] == port, f"port={port}")

    print("\n── 2. delivery with a configured channel ──")
    notifier = EscalationNotifier(webhook_url=f"http://127.0.0.1:{port}/ops/alerts", dedupe_window_seconds=600)
    delivered = await notifier.deliver({"subsystem": "redis", "reason": "3 repair attempts did not restore health"})
    check("escalation delivered", delivered.get("delivered") is True, f"{delivered}")
    check("receiver got the payload", len(received) == 1 and received[0].get("subsystem") == "redis", f"{received}")

    print("\n── 3. duplicate suppression (an operator must not be spammed) ──")
    for _ in range(3):
        await notifier.deliver({"subsystem": "redis", "reason": "3 repair attempts did not restore health"})
    check("repeats suppressed", len(received) == 1, f"receiver calls={len(received)}")
    check("suppression is counted", notifier.status()["suppressed_duplicates"] == 3, f"{notifier.status()}")
    other = await notifier.deliver({"subsystem": "database", "reason": "3 repair attempts did not restore health"})
    check("a different escalation still goes out", other.get("delivered") is True and len(received) == 2)

    print("\n── 4. a channel that fails is reported as not delivered ──")
    fail_next["value"] = True
    broken = await notifier.deliver({"subsystem": "schema", "reason": "no repair action registered"})
    fail_next["value"] = False
    check("500 from the channel is not reported as delivered", broken.get("delivered") is False, f"{broken}")
    check("the status code is recorded", broken.get("status_code") == 500)

    print("\n── 5. no channel configured is stated plainly ──")
    silent = EscalationNotifier(webhook_url="")
    record = await silent.deliver({"subsystem": "ai_universe", "reason": "3 repair attempts did not restore health"})
    check("not falsely delivered", record.get("delivered") is False)
    check(
        "reason names the missing channel",
        record.get("detail") == "no escalation channel configured",
        f"{record.get('detail')}",
    )
    check("status admits the channel is missing", silent.status()["channel_configured"] is False)

    print("\n── 6. the supervisor escalates through the channel for real ──")
    registry = HealthRegistry()

    async def failing_probe() -> bool:
        return False

    registry.register_probe("comms", failing_probe)
    supervisor = SelfHealingSupervisor(
        registry,
        repair_cooldown_seconds=0.0,
        max_repairs_per_subsystem=1,
        notifier=EscalationNotifier(webhook_url=f"http://127.0.0.1:{port}/ops/alerts", dedupe_window_seconds=0),
    )
    await supervisor.run_cycle()  # fail 1 (no repair registered -> immediate escalation)
    run = await supervisor.run_cycle()
    check("cycle escalated the subsystem", run.escalated == ["comms"], f"escalated={run.escalated}")
    check("supervisor reported the delivery", bool(run.escalations_delivered), f"{run.escalations_delivered}")
    check(
        "the operator receiver actually saw 'comms'",
        any(item.get("subsystem") == "comms" for item in received),
        f"receiver calls={[item.get('subsystem') for item in received]}",
    )

    server.shutdown()
    passed = sum(1 for ok, _ in results if ok)
    print(f"\n{'=' * 62}\n{passed}/{len(results)} checks passed")
    for ok, name in results:
        if not ok:
            print(f"  FAILED: {name}")
    print("=" * 62)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async(8099)))
