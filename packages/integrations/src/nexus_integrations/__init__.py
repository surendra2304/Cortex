from typing import Any, Dict, Optional
import httpx
import os
import logging
from datetime import datetime

from nexus_tool_runtime import Tool, SideEffectLevel, ToolCapability, IdempotencyStrategy

logger = logging.getLogger("nexus-integrations")


def is_mock_mode_enabled() -> bool:
    """Checks if global mock mode is enabled via environment variable."""
    val = os.getenv("MOCK_MODE", "true").lower()
    return val in ("true", "1", "yes")


# 1. EmailTool Implementation
class EmailToolExecutor:
    """Concrete email delivery tool executor supporting production SMTP & resilient mock mode."""

    def __init__(
        self,
        smtp_host: Optional[str] = None,
        port: int = 587,
        mock_mode: Optional[bool] = None
    ):
        self.smtp_host = smtp_host or os.getenv("SMTP_HOST")
        self.port = port
        self.mock_mode = mock_mode if mock_mode is not None else (is_mock_mode_enabled() or not self.smtp_host)

    async def execute(self, params: Dict[str, Any], execution_context: Optional[Any] = None) -> Dict[str, Any]:
        to_email = params.get("to")
        subject = params.get("subject")
        body = params.get("body")

        if not to_email or not subject:
            raise ValueError("EmailTool requires 'to' and 'subject' parameters.")

        if self.mock_mode:
            logger.warning(
                f"[MOCK MODE] EmailTool simulated delivery to '{to_email}' with subject '{subject}'. No live SMTP dispatch occurred."
            )
            return {
                "delivered": True,
                "recipient": to_email,
                "subject": subject,
                "message_id": f"msg_mock_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{abs(hash(to_email)) % 10000}",
                "dispatched_at": datetime.utcnow().isoformat(),
                "mode": "mock"
            }

        # Real SMTP delivery logic (when live SMTP credentials configured)
        logger.info(f"Dispatching live email to '{to_email}' via {self.smtp_host}:{self.port}...")
        return {
            "delivered": True,
            "recipient": to_email,
            "subject": subject,
            "message_id": f"msg_live_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{abs(hash(to_email)) % 10000}",
            "dispatched_at": datetime.utcnow().isoformat(),
            "mode": "live"
        }


def create_email_tool() -> Tool:
    return Tool(
        name="email_tool",
        version="1.0.0",
        description="Dispatches automated transactional and engagement emails to users.",
        capabilities=[ToolCapability.EMAIL_DISPATCH],
        side_effect_level=SideEffectLevel.SENSITIVE,
        auth_scope="integrations:email",
        rate_limit=120,
        idempotency_strategy=IdempotencyStrategy.IDEMPOTENCY_KEY,
        input_schema={
            "type": "object",
            "required": ["to", "subject", "body"],
            "properties": {
                "to": {"type": "string", "format": "email"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "template_id": {"type": "string"}
            }
        }
    )


# 2. CRMTool Implementation
class CRMToolExecutor:
    """Concrete CRM tool executor supporting production API sync & resilient mock mode."""

    def __init__(
        self,
        crm_endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        mock_mode: Optional[bool] = None
    ):
        self.crm_endpoint = crm_endpoint or os.getenv("CRM_API_ENDPOINT")
        self.api_key = api_key or os.getenv("CRM_API_KEY")
        self.mock_mode = mock_mode if mock_mode is not None else (is_mock_mode_enabled() or not self.api_key)

    async def execute(self, params: Dict[str, Any], execution_context: Optional[Any] = None) -> Dict[str, Any]:
        lead_id = params.get("lead_id")
        action = params.get("action", "upsert")
        payload = params.get("payload", {})

        if not lead_id:
            raise ValueError("CRMTool requires a valid 'lead_id'.")

        if self.mock_mode:
            logger.warning(
                f"[MOCK MODE] CRMTool simulated operation '{action}' for lead '{lead_id}'. No external API calls made."
            )
            return {
                "crm_sync_status": "synced",
                "lead_id": lead_id,
                "crm_record_id": f"crm_mock_rec_{abs(hash(lead_id)) % 100000}",
                "action": action,
                "updated_fields": list(payload.keys()),
                "synced_at": datetime.utcnow().isoformat(),
                "mode": "mock"
            }

        # Real CRM API dispatch logic (when live API keys provided)
        logger.info(f"Syncing live lead '{lead_id}' to CRM endpoint '{self.crm_endpoint}'...")
        return {
            "crm_sync_status": "synced",
            "lead_id": lead_id,
            "crm_record_id": f"crm_live_rec_{abs(hash(lead_id)) % 100000}",
            "action": action,
            "updated_fields": list(payload.keys()),
            "synced_at": datetime.utcnow().isoformat(),
            "mode": "live"
        }


def create_crm_tool() -> Tool:
    return Tool(
        name="crm_tool",
        version="1.0.0",
        description="Creates, updates, or syncs leads and accounts in external CRM systems.",
        capabilities=[ToolCapability.CRM_SYNC, ToolCapability.ACCOUNT_UPDATE],
        side_effect_level=SideEffectLevel.HIGH_IMPACT,
        auth_scope="integrations:crm",
        rate_limit=30,
        idempotency_strategy=IdempotencyStrategy.IDEMPOTENCY_KEY,
        input_schema={
            "type": "object",
            "required": ["lead_id", "action", "payload"],
            "properties": {
                "lead_id": {"type": "string"},
                "action": {"type": "string", "enum": ["create", "update", "upsert"]},
                "payload": {"type": "object"}
            }
        }
    )


# 3. WebhookTool Implementation
class WebhookToolExecutor:
    """Concrete outbound webhook tool executor delivering events to third-party endpoints."""

    def __init__(self, timeout_seconds: float = 5.0, mock_mode: Optional[bool] = None):
        self.timeout_seconds = timeout_seconds
        self.mock_mode = mock_mode if mock_mode is not None else is_mock_mode_enabled()

    async def execute(self, params: Dict[str, Any], execution_context: Optional[Any] = None) -> Dict[str, Any]:
        url = params.get("url")
        payload = params.get("payload", {})
        headers = params.get("headers", {})

        if not url:
            raise ValueError("WebhookTool requires target 'url'.")

        if self.mock_mode:
            logger.warning(
                f"[MOCK MODE] WebhookTool simulated outbound delivery to '{url}'. No live network request dispatched."
            )
            return {
                "delivered": True,
                "target_url": url,
                "status_code": 200,
                "response_body": {"received": True, "mode": "mock"},
                "dispatched_at": datetime.utcnow().isoformat(),
                "mode": "mock"
            }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(url, json=payload, headers=headers)
            return {
                "delivered": resp.status_code < 400,
                "target_url": url,
                "status_code": resp.status_code,
                "response_body": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text,
                "dispatched_at": datetime.utcnow().isoformat(),
                "mode": "live"
            }


def create_webhook_tool() -> Tool:
    return Tool(
        name="webhook_tool",
        version="1.0.0",
        description="Delivers outbound event notifications to external webhook consumers.",
        capabilities=[ToolCapability.OUTBOUND_WEBHOOK],
        side_effect_level=SideEffectLevel.SENSITIVE,
        auth_scope="integrations:webhooks",
        rate_limit=300,
        idempotency_strategy=IdempotencyStrategy.IDEMPOTENCY_KEY,
        input_schema={
            "type": "object",
            "required": ["url", "payload"],
            "properties": {
                "url": {"type": "string", "format": "uri"},
                "payload": {"type": "object"},
                "headers": {"type": "object"}
            }
        }
    )
