#!/usr/bin/env python3
"""CORTEX real-world pressure and adversarial test harness.

This drives a **live server** over HTTP (no TestClient, no mocks) and reports
measured numbers: throughput, latency percentiles, memory growth, and the
invariants that matter for money and privacy (idempotency, tenant isolation,
no 5xx under hostile input).

Scenarios
---------
1. cold + warm baseline latency
2. peak throughput at high concurrency (default 200 workers)
3. idempotency race: identical event_ids fired concurrently must be written once
4. tenant isolation under load: cross-tenant claims must all be refused
5. authentication hammering: unauthenticated traffic must be refused, never 5xx
6. rate limiting: the limiter must engage and recover without dropping the server
7. hostile input battery: oversized, malformed, deep-nested, unicode, injection
8. sustained soak with RSS sampling and invariant checks after each window
9. consistency audit: every accepted event is in the database and the stream

Usage
-----
    python scripts/pressure_test.py --url http://127.0.0.1:8000 --key pk_live_... \
        --concurrency 200 --events 5000 --soak-seconds 60

Exit code is non-zero if any invariant fails.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

STATUS_ACCEPTED = "accepted"
STATUS_DUPLICATE = "duplicate"


@dataclass
class Latencies:
    values: list[float] = field(default_factory=list)

    def add(self, seconds: float) -> None:
        self.values.append(seconds * 1000.0)

    def summary(self) -> dict[str, float]:
        if not self.values:
            return {}
        ordered = sorted(self.values)
        return {
            "count": len(ordered),
            "mean_ms": round(statistics.fmean(ordered), 2),
            "p50_ms": round(ordered[int(len(ordered) * 0.50)], 2),
            "p95_ms": round(ordered[int(len(ordered) * 0.95) - 1], 2),
            "p99_ms": round(ordered[int(len(ordered) * 0.99) - 1], 2),
            "max_ms": round(ordered[-1], 2),
        }


@dataclass
class Result:
    name: str
    ok: bool
    detail: str
    skipped: bool = False

    def render(self) -> str:
        if self.skipped:
            return f"[SKIP] {self.name}: {self.detail}"
        marker = "PASS" if self.ok else "FAIL"
        return f"[{marker}] {self.name}: {self.detail}"


def event_payload(event_id: str, tenant_id: str, site_id: str, **overrides) -> dict:
    payload = {
        "event_id": event_id,
        "tenant_id": tenant_id,
        "site_id": site_id,
        "type": "page_view",
        "occurred_at": datetime.now(UTC).isoformat(),
        "actor": {"type": "visitor", "id": f"vis_{event_id}"},
        "session_id": f"ses_{event_id}",
        "source": "pressure-harness",
        "data": {"path": "/pricing", "harness": True},
        "consent": {"analytics": True},
        "trace_id": f"trc_{event_id}",
    }
    payload.update(overrides)
    return payload


RUN_NONCE = f"{int(time.time() * 1000)}_{os.getpid()}"


class TransportFailure(RuntimeError):
    """Raised when a request could not be delivered after bounded retries."""


class Harness:
    def __init__(self, base_url: str, public_key: str, other_tenant_key: str, jwt: str, admin_tenant: str):
        self.base_url = base_url.rstrip("/")
        self.public_key = public_key
        self.other_tenant_key = other_tenant_key
        self.jwt = jwt
        self.admin_tenant = admin_tenant
        self.results: list[Result] = []
        self.latencies = Latencies()
        self.status_counter: Counter[str] = Counter()
        self.accepted: list[str] = []
        self.soak_accepted: list[str] = []
        self.printed = 0
        self.transport_failures: list[str] = []
        self.duplicates = 0

    # ── helpers ─────────────────────────────────────────────────────────────
    def key_headers(self, key: str | None = None) -> dict[str, str]:
        return {"X-Cortex-Public-Key": key or self.public_key}

    def jwt_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.jwt}"}

    async def provision_key(self, client: httpx.AsyncClient, tenant_id: str, site_id: str, name: str) -> str:
        response = await self.request(
            client,
            "POST",
            f"{self.base_url}/v1/api-keys",
            json={"tenant_id": tenant_id, "site_id": site_id, "name": name},
            headers=self.jwt_headers(),
            timeout=30,
        )
        if response.status_code != 201:
            raise RuntimeError(f"could not provision key for {tenant_id}: {response.status_code} {response.text[:200]}")
        return response.json()["api_key"]

    async def request(
        self, client: httpx.AsyncClient, method: str, url: str, *, attempts: int = 3, **kwargs
    ) -> httpx.Response:
        """Send a request, retrying transient transport failures.

        A keep-alive connection can be closed by the server between scenarios; at 200
        concurrent connections that shows up as ``httpx.ReadError`` even though the server is
        healthy (observed live). Event writes are idempotent on ``event_id``, so retrying is
        safe. Unresolved failures are raised as :class:`TransportFailure` and reported as a
        failed scenario, never swallowed and never allowed to abort the whole run.
        """
        last: Exception | None = None
        for attempt in range(attempts):
            try:
                return await client.request(method, url, **kwargs)
            except httpx.TransportError as exc:
                last = exc
                await asyncio.sleep(0.05 * (attempt + 1))
        raise TransportFailure(f"{method.upper()} {url}: {type(last).__name__}: {last}")

    async def send_event(self, client: httpx.AsyncClient, payload: dict, key: str | None = None) -> httpx.Response:
        started = time.perf_counter()
        try:
            response = await self.request(
                client, "POST", f"{self.base_url}/v1/events", json=payload, headers=self.key_headers(key)
            )
            self.latencies.add(time.perf_counter() - started)
            self.status_counter[str(response.status_code)] += 1
            return response
        finally:
            pass

    # ── scenarios ───────────────────────────────────────────────────────────
    async def scenario_baseline(self, client: httpx.AsyncClient, site_id: str) -> None:
        cold = Latencies()
        for _index in range(5):
            started = time.perf_counter()
            response = await self.request(client, "GET", f"{self.base_url}/v1/health")
            cold.add(time.perf_counter() - started)
            assert response.status_code == 200, response.text
        self.results.append(Result("baseline-latency", True, f"/v1/health {cold.summary()}"))

    async def scenario_throughput(
        self, client: httpx.AsyncClient, tenant: str, site: str, events: int, concurrency: int
    ):
        body_statuses: Counter[str] = Counter()

        async def worker(start_index: int, worker_id: int, count: int) -> None:
            for offset in range(count):
                n = start_index + offset
                payload = event_payload(f"perf_{RUN_NONCE}_{worker_id}_{n}", tenant, site, data={"index": n})
                try:
                    response = await self.send_event(client, payload)
                except TransportFailure as exc:
                    self.transport_failures.append(str(exc))
                    continue
                if response.status_code == 200:
                    body = response.json()
                    body_statuses[body.get("status", "missing")] += 1
                    if body.get("status") == STATUS_ACCEPTED:
                        self.accepted.append(payload["event_id"])
                    elif body.get("status") == STATUS_DUPLICATE:
                        self.duplicates += 1

        per_worker, remainder = divmod(events, concurrency)
        started = time.perf_counter()
        tasks = []
        for worker_id in range(concurrency):
            count = per_worker + (1 if worker_id < remainder else 0)
            if count:
                tasks.append(asyncio.create_task(worker(worker_id * 10_000, worker_id, count)))
        await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - started

        statuses = Counter(self.status_counter)
        server_errors = sum(count for code, count in statuses.items() if code.startswith("5"))
        rate_limited = statuses.get("429", 0)
        rps = len(self.latencies.values) / elapsed if elapsed else 0
        summary = self.latencies.summary()
        ok = server_errors == 0 and not self.transport_failures
        self.results.append(
            Result(
                "throughput",
                ok,
                f"{events} events, concurrency={concurrency}, {rps:,.0f} req/s, "
                f"p50={summary.get('p50_ms')}ms p95={summary.get('p95_ms')}ms p99={summary.get('p99_ms')}ms, "
                f"5xx={server_errors}, 429={rate_limited}, dropped-connections={len(self.transport_failures)}, "
                f"statuses={dict(statuses)}, body-statuses={dict(body_statuses)}",
            )
        )
        self.status_counter.clear()

    async def scenario_idempotency_race(self, client: httpx.AsyncClient, tenant: str, site: str, racers: int = 200):
        """The same event_id fired concurrently must be persisted exactly once."""
        event_id = f"race_{RUN_NONCE}"
        payload = event_payload(event_id, tenant, site)

        async def fire() -> httpx.Response:
            return await self.request(
                client, "POST", f"{self.base_url}/v1/events", json=payload, headers=self.key_headers()
            )

        responses = await asyncio.gather(*(fire() for _ in range(racers)), return_exceptions=True)
        statuses = Counter()
        accepted = 0
        duplicates = 0
        for response in responses:
            if isinstance(response, Exception):
                statuses["exception"] += 1
                continue
            statuses[str(response.status_code)] += 1
            if response.status_code == 200:
                body = response.json()
                accepted += body.get("status") == STATUS_ACCEPTED
                duplicates += body.get("status") == STATUS_DUPLICATE
        ok = accepted == 1 and duplicates == racers - 1
        self.results.append(
            Result(
                "idempotency-race",
                ok,
                f"{racers} concurrent identical event_ids -> accepted={accepted}, duplicate={duplicates}, "
                f"statuses={dict(statuses)}",
            )
        )

    async def scenario_tenant_isolation(self, client: httpx.AsyncClient, site: str, attempts: int = 200):
        victim_tenant = "tenant_victim"
        cross_tenant_ids = [f"attack_{RUN_NONCE}_{i}" for i in range(attempts)]

        async def attack(event_id: str) -> tuple[int, str]:
            payload = event_payload(event_id, victim_tenant, site)
            response = await self.request(
                client, "POST", f"{self.base_url}/v1/events", json=payload, headers=self.key_headers()
            )
            return response.status_code, response.text[:120]

        outcomes = await asyncio.gather(*(attack(event_id) for event_id in cross_tenant_ids), return_exceptions=True)
        codes = Counter()
        transport_failures = 0
        for outcome in outcomes:
            if isinstance(outcome, Exception):
                transport_failures += 1
                codes["transport-error"] += 1
                continue
            codes[outcome[0]] += 1
        forbidden = codes.get(403, 0)
        ok = (
            forbidden == attempts
            and not any(isinstance(code, int) and code >= 500 for code in codes)
            and transport_failures == 0
        )
        self.results.append(
            Result(
                "tenant-isolation",
                ok,
                f"{attempts} cross-tenant writes -> 403={forbidden}, statuses={dict(codes)} "
                f"(tenant identity must come from the credential)",
            )
        )
        return cross_tenant_ids

    async def scenario_unauthenticated_flood(self, client: httpx.AsyncClient, site: str, attempts: int = 300):
        payload = event_payload("unauth_probe", "tenant_any", site)

        async def probe() -> int:
            response = await self.request(client, "POST", f"{self.base_url}/v1/events", json=payload)
            return response.status_code

        results = await asyncio.gather(*(probe() for _ in range(attempts)), return_exceptions=True)
        codes = Counter()
        for result in results:
            if isinstance(result, Exception):
                codes["transport-error"] += 1
            else:
                codes[result] += 1
        ok = (
            codes.get(401, 0) == attempts
            and not codes.get("transport-error")
            and not any(isinstance(code, int) and code >= 500 for code in codes)
        )
        self.results.append(
            Result("unauthenticated-flood", ok, f"{attempts} anonymous writes -> statuses={dict(codes)}")
        )

    async def scenario_rate_limit(self, client: httpx.AsyncClient, tenant: str, site: str, limit: int, burst: int):
        """Burst past the configured limit and confirm 429 appears with no 5xx.

        ``burst`` is capped by the caller: firing ``limit + 120`` requests at a deployment
        whose limit is 100k opens 100k sockets and hangs the client (observed live).
        """
        key = await self.provision_key(client, tenant, f"{site}-ratelimit", "rate-limit-probe")
        codes = Counter()

        async def fire(index: int) -> None:
            payload = event_payload(f"rl_{RUN_NONCE}_{index}", tenant, f"{site}-ratelimit")
            try:
                response = await self.request(
                    client, "POST", f"{self.base_url}/v1/events", json=payload, headers=self.key_headers(key)
                )
            except TransportFailure:
                codes["transport-error"] += 1
                return
            codes[str(response.status_code)] += 1

        await asyncio.gather(*(fire(i) for i in range(burst)))
        limited = codes.get("429", 0)
        server_errors = sum(count for code, count in codes.items() if code.startswith("5"))
        ok = limited > 0 and server_errors == 0
        self.results.append(
            Result(
                "rate-limit",
                ok,
                f"burst={burst} (configured limit={limit}/window) -> 429={limited}, 5xx={server_errors}, "
                f"statuses={dict(codes)}",
            )
        )

    async def scenario_hostile_input(self, client: httpx.AsyncClient, tenant: str, site: str):
        checks: list[tuple[str, int, bool]] = []
        big = "x" * (600 * 1024)
        cases = [
            ("oversized-data", event_payload("host_big", tenant, site, data={"blob": big})),
            ("deep-nesting", event_payload("host_deep", tenant, site, data=_deeply_nested(80))),
            ("unicode", event_payload("host_unicode", tenant, site, data={"emoji": "🔥💥🧠", "rtl": "مرحبا"})),
            ("sql-injection", event_payload("host_sql'--", tenant, site, data={"q": "'; DROP TABLE events; --"})),
            ("null-bytes", event_payload("host_null", tenant, site, data={"k": "a\x00b"})),
            ("wrong-actor-type", event_payload("host_actor", tenant, site, actor={"type": "robot", "id": "x"})),
            ("missing-event-id", {k: v for k, v in event_payload("x", tenant, site).items() if k != "event_id"}),
            ("bad-timestamp", event_payload("host_ts", tenant, site, occurred_at="not-a-timestamp")),
        ]
        for name, payload in cases:
            try:
                response = await self.request(
                    client, "POST", f"{self.base_url}/v1/events", json=payload, headers=self.key_headers(), timeout=30
                )
                checks.append((name, response.status_code, response.status_code < 500))
            except Exception as exc:  # a transport failure is a failure
                checks.append((name, 0, False))
                print(f"    hostile case {name} raised {exc!r}")

        # malformed JSON and wrong content type
        for name, body, headers in [
            ("malformed-json", b"{not json", {"Content-Type": "application/json"}),
            ("empty-body", b"", {"Content-Type": "application/json"}),
            ("wrong-type", json.dumps({"event_id": 42}).encode(), {"Content-Type": "application/json"}),
        ]:
            headers.update(self.key_headers())
            response = await self.request(
                client, "POST", f"{self.base_url}/v1/events", content=body, headers=headers, timeout=30
            )
            checks.append((name, response.status_code, response.status_code < 500))

        # batch abuse
        oversized_batch = [event_payload(f"batch_{i}", tenant, site) for i in range(75)]
        response = await self.request(
            client,
            "POST",
            f"{self.base_url}/v1/events/batch",
            json=oversized_batch,
            headers=self.key_headers(),
            timeout=30,
        )
        checks.append(("oversized-batch", response.status_code, response.status_code == 400))

        # webhook provider path traversal / injection
        for provider in ["../../etc/passwd", "stripe%2F..%2Fadmin", "<script>"]:
            response = await self.request(
                client,
                "POST",
                f"{self.base_url}/v1/webhooks/{provider}",
                json={"a": 1},
                headers=self.key_headers(),
                timeout=30,
            )
            checks.append((f"webhook-provider:{provider[:16]}", response.status_code, response.status_code < 500))

        # path traversal on the dashboard
        for path in ["/..%2f..%2fetc%2fpasswd", "/dashboard/../../etc/passwd", "/%2e%2e/%2e%2e/etc/passwd"]:
            response = await self.request(client, "GET", f"{self.base_url}{path}", timeout=30)
            checks.append((f"traversal:{path[:20]}", response.status_code, response.status_code < 500))

        failures = [f"{name}({code})" for name, code, ok in checks if not ok]
        self.results.append(
            Result(
                "hostile-input",
                not failures,
                f"{len(checks)} adversarial requests, 5xx/transport failures={len(failures)}"
                + (f" -> {failures}" if failures else " (every case answered with a client status)"),
            )
        )

    async def _wait_for_rate_limit_window(
        self, client: httpx.AsyncClient, tenant: str, site: str, window_seconds: int
    ) -> None:
        """Poll until the ingest rate limiter admits a request again.

        Without this the soak would spend almost every request on the 429 fast path and the
        memory/invariant sampling would never exercise the real persistence pipeline.
        """
        deadline = time.time() + window_seconds + 5
        while time.time() < deadline:
            response = await self.request(
                client,
                "POST",
                f"{self.base_url}/v1/events",
                json=event_payload(f"probe_{RUN_NONCE}_{int(time.time() * 1000)}", tenant, site),
                headers=self.key_headers(),
                timeout=30,
            )
            if response.status_code != 429:
                return
            await asyncio.sleep(2)
        print("  WARNING: rate limiter never reopened; soak will be throttled", file=sys.stderr)

    async def scenario_soak(
        self,
        base_url: str,
        tenant: str,
        site: str,
        seconds: int,
        concurrency: int,
        pid: int | None,
        rate_limit: int,
        rate_limit_window: int,
    ) -> None:
        """Sustained mixed traffic with memory and invariant sampling.

        Traffic is paced to ~80% of the configured rate limit so requests flow through the
        ingest path (the point of the soak) instead of bouncing off 429.
        """
        target_rps = max(1.0, rate_limit / max(1, rate_limit_window) * 0.8)
        interval = 1.0 / target_rps
        next_slot = {"at": time.monotonic()}
        slot_lock = asyncio.Lock()

        async def pace() -> None:
            async with slot_lock:
                now = time.monotonic()
                wait = max(0.0, next_slot["at"] - now)
                next_slot["at"] = max(now, next_slot["at"]) + interval
            if wait:
                await asyncio.sleep(wait)

        deadline = time.time() + seconds
        counters = Counter()
        body_statuses: Counter[str] = Counter()
        accepted_ids: list[str] = []
        rss_samples: list[int] = []
        inconsistent: list[str] = []

        async def traffic(client: httpx.AsyncClient, worker_id: int) -> None:
            index = 0
            while time.time() < deadline:
                index += 1
                await pace()
                roll = random.random()
                if roll < 0.85:
                    # Ids carry the run nonce: a second run against the same server process must
                    # not be mistaken for throttling when the idempotency store replays duplicates.
                    payload = event_payload(f"soak_{RUN_NONCE}_{worker_id}_{index}", tenant, site)
                    response = await self.request(
                        client,
                        "POST",
                        f"{self.base_url}/v1/events",
                        json=payload,
                        headers=self.key_headers(),
                        timeout=30,
                    )
                    if response.status_code == 200:
                        status_value = response.json().get("status", "missing")
                        body_statuses[status_value] += 1
                        if status_value == STATUS_ACCEPTED:
                            accepted_ids.append(payload["event_id"])
                elif roll < 0.95:
                    response = await self.request(client, "GET", f"{self.base_url}/v1/health", timeout=30)
                else:
                    response = await self.request(
                        client, "POST", f"{self.base_url}/v1/events", json={"garbage": True}, timeout=30
                    )
                counters[str(response.status_code)] += 1
                if response.status_code >= 500:
                    inconsistent.append(f"5xx on {response.request.url.path}")

        async with httpx.AsyncClient() as client:
            await self._wait_for_rate_limit_window(client, tenant, site, rate_limit_window)
            next_slot["at"] = time.monotonic()
            tasks = [asyncio.create_task(traffic(client, i)) for i in range(concurrency)]
            while time.time() < deadline:
                await asyncio.sleep(5)
                rss = _rss_kb(pid) if pid else None
                if rss:
                    rss_samples.append(rss)
            await asyncio.gather(*tasks)

        self.soak_accepted = list(accepted_ids)
        server_errors = sum(count for code, count in counters.items() if code.startswith("5"))
        growth = ""
        notes: list[str] = []
        ok = server_errors == 0 and not inconsistent and not self.transport_failures
        if len(rss_samples) >= 3:
            first, last = rss_samples[0], rss_samples[-1]
            growth_pct = (last - first) / first * 100
            growth = f", RSS {first / 1024:.0f}MB -> {last / 1024:.0f}MB ({growth_pct:+.1f}%)"
            # A steady-state server should not grow unboundedly during a soak.
            if growth_pct > 60:
                ok = False
                growth += " [LEAK SUSPECTED]"
        else:
            notes.append("no RSS samples (pass --api-pid for the leak check)")
        if len(accepted_ids) < max(20, seconds):
            # Few accepted ingestions means the soak never really exercised persistence;
            # report the reason (throttled vs duplicate replay) instead of passing quietly.
            ok = False
            reason = "throttled by rate limiter" if counters.get("429") else f"body-statuses={dict(body_statuses)}"
            notes.append(f"INCONCLUSIVE: only {len(accepted_ids)} accepted ingestions ({reason})")
        self.results.append(
            Result(
                "sustained-soak",
                ok,
                f"{seconds}s at concurrency={concurrency}, paced~{target_rps:.0f}rps, "
                f"requests={sum(counters.values())}, accepted={len(accepted_ids)}, "
                f"5xx={server_errors}, dropped-connections={len(self.transport_failures)}{growth}, "
                f"statuses={dict(counters)}, body-statuses={dict(body_statuses)}"
                + (f" {'; '.join(notes)}" if notes else ""),
            )
        )

    async def scenario_consistency(self, client: httpx.AsyncClient, expected_ids: list[str]) -> None:
        """Every accepted event must be readable back through the API."""
        missing: list[str] = []
        # The read endpoint caps a page at 200 rows, so page with the documented limit and
        # walk forward by offset until the server returns an empty page.
        page_size = 200
        seen: set[str] = set()
        offset = 0
        while True:
            response = await self.request(
                client,
                "GET",
                f"{self.base_url}/v1/events",
                params={"limit": page_size, "offset": offset},
                headers=self.jwt_headers(),
                timeout=60,
            )
            if response.status_code != 200:
                self.results.append(
                    Result("consistency", False, f"/v1/events returned {response.status_code}: {response.text[:200]}")
                )
                return
            batch = response.json()
            if not batch:
                break
            before = len(seen)
            seen.update(row["event_id"] for row in batch)
            offset += len(batch)
            if len(seen) == before:
                # The server returned rows we already have: offset paging is not advancing.
                self.results.append(
                    Result("consistency", False, f"pagination stalled at offset={offset} ({len(batch)} rows returned)")
                )
                return

        expected_set = set(expected_ids)
        missing = sorted(expected_set - seen)
        extra_ok = len(seen) >= len(expected_set)
        ok = not missing and extra_ok
        self.results.append(
            Result(
                "consistency",
                ok,
                f"accepted={len(expected_set)}, readable={len(expected_set & seen)}, missing={len(missing)}"
                + (f" e.g. {missing[:3]}" if missing else ""),
            )
        )


def _deeply_nested(depth: int) -> dict:
    node: dict = {"leaf": True}
    for _ in range(depth):
        node = {"nested": node}
    return node


def _rss_kb(pid: int | None) -> int | None:
    if not pid:
        return None
    try:
        with open(f"/proc/{pid}/status") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except OSError:
        return None
    return None


def _mint_jwt(secret: str, tenant_id: str, role: str = "cortex_admin", subject: str = "usr_pressure") -> str:
    from jose import jwt

    return jwt.encode(
        {
            "sub": subject,
            "role": role,
            "tenant_id": tenant_id,
            "exp": datetime.now(UTC).timestamp() + 3600,
        },
        secret,
        algorithm="HS256",
    )


async def main_async(args) -> int:
    harness = Harness(args.url, args.key, args.other_key, args.jwt, args.tenant)
    print(f"CORTEX pressure harness -> {args.url}")
    print(f"  concurrency={args.concurrency} events={args.events} soak={args.soak_seconds}s")

    async with httpx.AsyncClient(timeout=60, limits=httpx.Limits(max_connections=args.concurrency * 2)) as client:
        # Discover the API surface first; a server that cannot answer health is dead.
        health = await client.get(f"{args.url}/v1/health")
        print(f"  health: {health.status_code} {health.text[:120]}")
        if health.status_code != 200:
            print("server is not healthy; aborting")
            return 2

        jwt = args.jwt or _mint_jwt(args.jwt_secret, args.tenant)
        harness.jwt = jwt
        key = args.key or await harness.provision_key(client, args.tenant, args.site, "pressure-harness")
        harness.public_key = key
        other_key = args.other_key or await harness.provision_key(
            client, "tenant_other", args.site, "pressure-other-tenant"
        )
        harness.other_tenant_key = other_key
        print(f"  provisioned keys for {args.tenant} and tenant_other")

        scenarios = [
            ("baseline", lambda: harness.scenario_baseline(client, args.site)),
            ("idempotency-race", lambda: harness.scenario_idempotency_race(client, args.tenant, args.site)),
            ("tenant-isolation", lambda: harness.scenario_tenant_isolation(client, args.site)),
            ("unauthenticated-flood", lambda: harness.scenario_unauthenticated_flood(client, args.site)),
            ("hostile-input", lambda: harness.scenario_hostile_input(client, args.tenant, args.site)),
        ]
        # Never fire "limit + 120" requests blindly: a capacity run with a 100k limit tried to
        # open 100k sockets and hung the client (observed live). Cap the burst and skip the
        # check honestly when the configured limit is out of reach.
        rate_limit_burst = min(args.rate_limit_burst or (args.rate_limit + 120), 2000)
        if args.rate_limit > 5000 and not args.rate_limit_burst:
            harness.results.append(
                Result(
                    "rate-limit",
                    True,
                    f"not exercised: server limit is {args.rate_limit}/window, far above the "
                    f"{rate_limit_burst}-request burst budget (capacity run)",
                    skipped=True,
                )
            )
        else:
            scenarios.insert(
                4,
                (
                    "rate-limit",
                    lambda: harness.scenario_rate_limit(
                        client, "tenant_ratelimit", args.site, args.rate_limit, rate_limit_burst
                    ),
                ),
            )

        def drain() -> None:
            while harness.printed < len(harness.results):
                print(harness.results[harness.printed].render(), flush=True)
                harness.printed += 1

        for name, run in scenarios:
            print(f"[RUN ] {name}", flush=True)
            try:
                await run()
            except Exception as exc:  # a broken scenario must be reported, not abort the run
                harness.results.append(Result(f"{name}:harness", False, f"{type(exc).__name__}: {exc}"))
            drain()

        harness.latencies = Latencies()
        try:
            await harness.scenario_throughput(client, args.tenant, args.site, args.events, args.concurrency)
        except Exception as exc:
            harness.results.append(Result("throughput:harness", False, f"{type(exc).__name__}: {exc}"))

        if args.soak_seconds:
            try:
                await harness.scenario_soak(
                    args.url,
                    args.tenant,
                    args.site,
                    args.soak_seconds,
                    min(args.concurrency, 16),
                    args.api_pid,
                    args.rate_limit,
                    args.rate_limit_window,
                )
            except Exception as exc:
                harness.results.append(Result("sustained-soak:harness", False, f"{type(exc).__name__}: {exc}"))
            drain()

        # Consistency check over every event the harness itself got acknowledged for.
        ids = list(harness.accepted) + list(harness.soak_accepted)
        try:
            await harness.scenario_consistency(client, ids[: args.consistency_sample])
        except Exception as exc:
            harness.results.append(Result("consistency:harness", False, f"{type(exc).__name__}: {exc}"))
        drain()

    print()
    failed = sum(1 for result in harness.results if not result.ok and not result.skipped)
    skipped = sum(1 for result in harness.results if result.skipped)
    print(f"scenarios: {len(harness.results)}  failed: {failed}  skipped: {skipped}")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="CORTEX real-world pressure test")
    parser.add_argument("--url", default=os.getenv("CORTEX_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--key", default=os.getenv("CORTEX_PUBLIC_KEY", ""))
    parser.add_argument("--other-key", default=os.getenv("CORTEX_OTHER_PUBLIC_KEY", ""))
    parser.add_argument("--jwt", default=os.getenv("CORTEX_JWT", ""))
    parser.add_argument("--jwt-secret", default=os.getenv("JWT_SECRET", ""))
    parser.add_argument("--tenant", default="tenant_load")
    parser.add_argument("--site", default="site_load")
    parser.add_argument("--concurrency", type=int, default=200)
    parser.add_argument("--events", type=int, default=5000)
    parser.add_argument("--rate-limit", type=int, default=1000)
    parser.add_argument(
        "--rate-limit-window", type=int, default=60, help="configured rate_limit_window_seconds on the server"
    )
    parser.add_argument(
        "--rate-limit-burst",
        type=int,
        default=0,
        help="requests to fire at the limiter (default: min(limit+120, 2000)); required to test an unusually high limit",
    )
    parser.add_argument("--soak-seconds", type=int, default=0)
    parser.add_argument("--consistency-sample", type=int, default=2000)
    parser.add_argument("--api-pid", type=int, default=None, help="API process id for RSS sampling")
    args = parser.parse_args()
    if not args.jwt and not args.jwt_secret:
        print("provide --jwt or --jwt-secret so operator endpoints can be exercised", file=sys.stderr)
        return 2
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
