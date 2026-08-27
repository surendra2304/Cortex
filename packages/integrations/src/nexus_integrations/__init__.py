from typing import Any, Dict, Optional
import httpx
import logging
from datetime import datetime

from nexus_tool_runtime import Tool, SideEffectLevel, ToolCapability, IdempotencyStrategy

logger = logging.getLogger("nexus-integrations")


# 1. EmailTool Implementation
class EmailToolExecutor:
    """Concrete email delivery tool executor with SMTP / mail provider dispatch simulation."""

    def __init__(self, smtp_host: str = "smtp.nexus.local", port: int = 587):
        self.smtp_host = smtp_host
        self.port = port

    async def execute(self, params: Dict[str, Any], execution_context: Optional[Any] = None) -> Dict[str, Any]:
        to_email = params.get("to")
        subject = params.get("subject")
        body = params.get("body")

        if not to_email or not subject:
            raise ValueError("EmailTool requires 'to' and 'subject' parameters.")

        logger.info(f"Simulating email dispatch to '{to_email}' with subject '{subject}'.")

        return {
            "delivered": True,
            "recipient": to_email,
            "subject": subject,
            "message_id": f"msg_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{abs(hash(to_email)) % 10000}",
            "dispatched_at": datetime.utcnow().isoformat()
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
    """Concrete CRM tool executor for syncing leads, deals, and accounts (HubSpot/Salesforce stubs)."""

    def __init__(self, crm_endpoint: str = "https://api.crm-provider.com/v1", api_key: Optional[str] = None):
        self.crm_endpoint = crm_endpoint
        self.api_key = api_key

    async def execute(self, params: Dict[str, Any], execution_context: Optional[Any] = None) -> Dict[str, Any]:
        lead_id = params.get("lead_id")
        action = params.get("action", "upsert")
        payload = params.get("payload", {})

        if not lead_id:
            raise ValueError("CRMTool requires a valid 'lead_id'.")

        logger.info(f"Simulating CRM operation '{action}' for lead '{lead_id}'.")

        return {
            "crm_sync_status": "synced",
            "lead_id": lead_id,
            "crm_record_id": f"crm_rec_{abs(hash(lead_id)) % 100000}",
            "action": action,
            "updated_fields": list(payload.keys()),
            "synced_at": datetime.utcnow().isoformat()
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

    def __init__(self, timeout_seconds: float = 5.0):
        self.timeout_seconds = timeout_seconds

    async def execute(self, params: Dict[str, Any], execution_context: Optional[Any] = None) -> Dict[str, Any]:
        url = params.get("url")
        payload = params.get("payload", {})
        headers = params.get("headers", {})

        if not url:
            raise ValueError("WebhookTool requires target 'url'.")

        logger.info(f"Simulating outbound webhook dispatch to '{url}'.")

        # In production with internet, httpx async client dispatches here:
        # async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
        #     resp = await client.post(url, json=payload, headers=headers)
        return {
            "delivered": True,
            "target_url": url,
            "status_code": 200,
            "response_body": {"received": True},
            "dispatched_at": datetime.utcnow().isoformat()
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
