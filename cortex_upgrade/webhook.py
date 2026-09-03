from __future__ import annotations
import hashlib
import hmac
import json
from dataclasses import dataclass

@dataclass(frozen=True)
class Verification:
    ok: bool
    reason: str

def verify_hmac(raw_body: bytes, signature: str, secret: str) -> Verification:
    if not signature or not secret:
        return Verification(False, "missing signature or secret")
    supplied = signature.removeprefix("sha256=").strip()
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    ok = hmac.compare_digest(supplied, expected)
    return Verification(ok, "ok" if ok else "invalid signature")

def verify_timestamp(timestamp: int, now: int, max_skew: int = 300) -> Verification:
    if abs(now - timestamp) > max_skew:
        return Verification(False, "replay window exceeded")
    return Verification(True, "ok")

def canonical_json(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
