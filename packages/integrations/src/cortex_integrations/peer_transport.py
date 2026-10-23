"""Real HTTP transport for FRIDAY-Universe peer services (IntelX, Futuris, Sentinel).

Cortex's peer clients used to be deterministic fixtures: ``mock_mode`` existed but no
code path ever made an HTTP call, so "IntelX integration" could never actually fail —
or actually work. This module is the missing transport.

Design rules (they matter):

* **Opt-in by configuration.** A peer is called only when its base URL is configured
  (``INTELX_BASE_URL`` / ``FUTURIS_BASE_URL`` / ``SENTINEL_BASE_URL``). Without one the
  clients keep their documented deterministic behaviour, and say so.
* **Honest degradation.** Every result carries ``source`` ("peer" or "fallback") and, when
  a configured peer could not be reached or refused the call, ``degraded`` with the reason.
  A fallback is never reported as peer intelligence.
* **Bounded.** Short timeouts, one retry on transport errors, and a hard cap on polling, so
  a dead peer cannot wedge a request or the cognitive loop.
* **Read-only by construction.** These helpers only issue the delegation/forecast calls the
  peer services define; nothing here can ask a peer to execute mitigations (Futuris
  explicitly refuses such requests with 403, and Cortex never sends them).
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger("cortex-integrations.peer-transport")

DEFAULT_TIMEOUT_SECONDS = 15.0


@dataclass
class PeerResponse:
    """Outcome of one peer call, with everything needed to explain it."""

    ok: bool
    status_code: int | None = None
    body: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    attempts: int = 0
    url: str = ""

    @property
    def detail(self) -> str:
        if self.ok:
            return f"{self.status_code} from {self.url}"
        if self.status_code is not None:
            return f"{self.status_code} from {self.url}: {self.error or 'peer refused the call'}"
        return f"{self.url}: {self.error or 'peer unreachable'}"


def peer_base_url(name: str) -> str | None:
    """Configured base URL for a peer, or None when the peer is not deployed here."""
    value = os.getenv(f"{name.upper()}_BASE_URL", "").strip()
    return value.rstrip("/") or None


def peer_api_key(name: str, fallback: str = "") -> str:
    """Prefer the peer-specific key, then the fleet-wide FRIDAY key."""
    return (
        os.getenv(f"{name.upper()}_FRIDAY_API_KEY", "").strip()
        or os.getenv(f"{name.upper()}_API_KEY", "").strip()
        or os.getenv("FRIDAY_API_KEY", "").strip()
        or fallback
    )


_SHARED_CLIENT: httpx.AsyncClient | None = None
_CIRCUITS: dict[str, Any] = {}


def get_shared_client(timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> httpx.AsyncClient:
    """Return a shared connection-pooled AsyncClient for all peer outbound requests."""
    global _SHARED_CLIENT
    if _SHARED_CLIENT is None or _SHARED_CLIENT.is_closed:
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=50, keepalive_expiry=30.0)
        _SHARED_CLIENT = httpx.AsyncClient(timeout=timeout_seconds, limits=limits)
    return _SHARED_CLIENT


async def close_shared_client() -> None:
    """Close the shared AsyncClient connection pool gracefully on shutdown."""
    global _SHARED_CLIENT
    if _SHARED_CLIENT is not None and not _SHARED_CLIENT.is_closed:
        await _SHARED_CLIENT.aclose()
        _SHARED_CLIENT = None


def get_circuit_for_peer(name: str):
    """Retrieve or initialize the circuit breaker for a given peer service."""
    if name not in _CIRCUITS:
        from cortex_core.resilience import SubsystemCircuit

        _CIRCUITS[name] = SubsystemCircuit(name=f"peer_{name}", failure_threshold=3, recovery_timeout_seconds=15.0)
    return _CIRCUITS[name]


class PeerTransport:
    """Small async JSON client with connection pooling, circuit breaker, retry and explicit failure reporting."""

    def __init__(
        self, name: str, base_url: str | None = None, api_key: str | None = None, timeout_seconds: float | None = None
    ):
        self.name = name
        self.base_url = (base_url if base_url is not None else peer_base_url(name)) or None
        self.api_key = api_key if api_key is not None else peer_api_key(name)
        self.timeout_seconds = timeout_seconds or float(os.getenv("PEER_HTTP_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))

    @property
    def configured(self) -> bool:
        return self.base_url is not None

    def headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        import uuid

        headers = {
            "Content-Type": "application/json",
            "X-Source-Agent": "cortex",
            "X-Agent-Name": "Cortex",
            "X-Correlation-ID": str(uuid.uuid4()),
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
            headers["Authorization"] = f"Bearer {self.api_key}"
        if extra:
            headers.update(extra)
        return headers

    async def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        retries: int = 1,
        headers: dict[str, str] | None = None,
    ) -> PeerResponse:
        if not self.configured:
            return PeerResponse(ok=False, error=f"{self.name} base URL is not configured", url=path)

        circuit = get_circuit_for_peer(self.name)
        if not await circuit.before():
            return PeerResponse(
                ok=False,
                error=f"Circuit breaker OPEN for {self.name}; failing fast to protect latency",
                url=path,
            )

        url = f"{self.base_url}{path}"
        attempts = 0
        last_error: str | None = None
        last_status: int | None = None
        last_body: dict[str, Any] = {}

        client = get_shared_client(self.timeout_seconds)

        while attempts <= retries:
            attempts += 1
            try:
                response = await client.request(
                    method.upper(), url, json=payload, params=params, headers=self.headers(headers)
                )
                body: dict[str, Any] = {}
                try:
                    parsed = response.json()
                    if isinstance(parsed, dict):
                        body = parsed
                    else:
                        body = {"_payload": parsed}
                except Exception:  # noqa: BLE001 - non-JSON error pages are still informative
                    body = {"_text": response.text[:500]}

                if response.status_code < 400:
                    await circuit.record_success()
                    return PeerResponse(
                        ok=True, status_code=response.status_code, body=body, attempts=attempts, url=url
                    )

                last_status = response.status_code
                last_body = body
                # 4xx (auth/validation/refusal) will not improve on retry.
                if response.status_code < 500:
                    return PeerResponse(
                        ok=False,
                        status_code=response.status_code,
                        body=body,
                        error=str(body.get("detail") or body.get("error") or "peer refused the call")[:300],
                        attempts=attempts,
                        url=url,
                    )
                await circuit.record_failure()
                last_error = f"peer returned {response.status_code}"
            except Exception as exc:  # noqa: BLE001 - transport errors are expected states here
                await circuit.record_failure()
                last_error = f"{type(exc).__name__}: {exc}"

            if attempts <= retries:
                import random

                delay = (0.2 * (2 ** (attempts - 1))) + random.uniform(0.01, 0.05)
                await asyncio.sleep(delay)

        return PeerResponse(
            ok=False,
            status_code=last_status,
            body=last_body,
            error=last_error,
            attempts=attempts,
            url=url,
        )

    async def get(self, path: str, **kwargs: Any) -> PeerResponse:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, payload: dict[str, Any] | None = None, **kwargs: Any) -> PeerResponse:
        return await self.request("POST", path, payload=payload, **kwargs)

    async def health(self) -> PeerResponse:
        """Peer health endpoint (each service exposes /health; IntelX also /api/v1/health)."""
        if not self.configured:
            return PeerResponse(ok=False, error=f"{self.name} base URL is not configured", url="/health")
        primary = await self.get("/health")
        if primary.ok:
            return primary
        if primary.status_code == 404:
            return await self.get("/api/v1/health")
        return primary
