from __future__ import annotations
import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from .models import Principal

@dataclass(frozen=True)
class ApiCredential:
    credential_id: str
    principal_id: str
    tenant_id: str
    salt_b64: str
    verifier_b64: str
    iterations: int
    created_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None

class CredentialManager:
    """PBKDF2-backed API-key verification; never persist plaintext secrets."""
    def __init__(self, iterations: int = 310_000) -> None:
        if iterations < 100_000:
            raise ValueError("iterations too low")
        self.iterations = iterations

    def create(
        self,
        credential_id: str,
        principal_id: str,
        tenant_id: str,
        secret: str,
        expires_in_days: int | None = None,
    ) -> ApiCredential:
        if len(secret) < 24:
            raise ValueError("credential is too short")
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt, self.iterations, 32)
        expires = None if expires_in_days is None else datetime.now(UTC) + timedelta(days=expires_in_days)
        return ApiCredential(
            credential_id, principal_id, tenant_id,
            base64.urlsafe_b64encode(salt).decode(),
            base64.urlsafe_b64encode(digest).decode(),
            self.iterations, datetime.now(UTC), expires, None,
        )

    def verify(self, secret: str, credential: ApiCredential, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        if credential.revoked_at is not None:
            return False
        if credential.expires_at and credential.expires_at <= now:
            return False
        try:
            salt = base64.urlsafe_b64decode(credential.salt_b64.encode())
            expected = base64.urlsafe_b64decode(credential.verifier_b64.encode())
        except Exception:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt, credential.iterations, len(expected))
        return hmac.compare_digest(actual, expected)

    @staticmethod
    def parse_header(value: str | None) -> str | None:
        if not value:
            return None
        value = value.strip()
        if value.lower().startswith("bearer "):
            value = value[7:].strip()
        return value or None

    @staticmethod
    def principal_from_credential(credential: ApiCredential, roles: set[str], scopes: set[str]) -> Principal:
        return Principal(
            principal_id=credential.principal_id,
            tenant_id=credential.tenant_id,
            roles=frozenset(roles),
            scopes=frozenset(scopes),
            credential_id=credential.credential_id,
        )

INSECURE_DEFAULTS = {
    "cortex_api",
    "super_secret_jwt_signing_key_replace_in_production",
    "mock_operator_jwt_token_123",
    "friday_secret",
    "change-me",
    "changeme",
    "password",
    "secret",
}

def validate_production_secrets(environment: str, values: dict[str, str | None]) -> None:
    if environment != "production":
        return
    unsafe = [
        name for name, value in values.items()
        if not value or value.strip().lower() in INSECURE_DEFAULTS or len(value) < 32
    ]
    if unsafe:
        raise RuntimeError("unsafe or missing production secrets: " + ",".join(unsafe))
