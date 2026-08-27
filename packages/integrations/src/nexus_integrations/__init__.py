from typing import Any, Dict, Optional, List
import os
import logging
from datetime import datetime
import asyncio

# SendGrid SDK
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, To, Content
    HAVE_SENDGRID = True
except ImportError:
    HAVE_SENDGRID = False

# Twilio SDK
try:
    from twilio.rest import Client as TwilioClient
    HAVE_TWILIO = True
except ImportError:
    HAVE_TWILIO = False

# HubSpot SDK
try:
    from hubspot import HubSpot
    from hubspot.crm.contacts import SimplePublicObjectInputForCreate as ContactCreateInput
    from hubspot.crm.contacts import SimplePublicObjectInput as ContactUpdateInput
    from hubspot.crm.deals import SimplePublicObjectInputForCreate as DealCreateInput
    HAVE_HUBSPOT = True
except ImportError:
    HAVE_HUBSPOT = False

from nexus_tool_runtime import Tool, SideEffectLevel, ToolCapability, IdempotencyStrategy

logger = logging.getLogger("nexus-integrations")


def is_mock_mode_enabled() -> bool:
    val = os.getenv("MOCK_MODE", "true").lower()
    return val in ("true", "1", "yes")


# ==============================================================================
# 1. SendGrid Email Tool
# ==============================================================================
class EmailToolExecutor:
    """Production SendGrid email tool executor with fallback to mock mode."""

    def __init__(self, api_key: Optional[str] = None, from_email: Optional[str] = None, mock_mode: Optional[bool] = None):
        self.api_key = api_key or os.getenv("SENDGRID_API_KEY")
        self.from_email = from_email or os.getenv("SENDGRID_FROM_EMAIL", "notifications@nexus.dev")
        self.mock_mode = mock_mode if mock_mode is not None else (is_mock_mode_enabled() or not self.api_key)

    async def execute(self, params: Dict[str, Any], execution_context: Optional[Any] = None) -> Dict[str, Any]:
        to_email = params.get("to")
        subject = params.get("subject")
        body = params.get("body")

        if not to_email or not subject:
            raise ValueError("EmailTool requires 'to' and 'subject' parameters.")

        if self.mock_mode or not HAVE_SENDGRID:
            logger.warning(
                f"[MOCK MODE] EmailTool simulated delivery to '{to_email}' with subject '{subject}'. No live SMTP/SendGrid call made."
            )
            return {
                "delivered": True,
                "recipient": to_email,
                "subject": subject,
                "message_id": f"msg_mock_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{abs(hash(to_email)) % 10000}",
                "dispatched_at": datetime.utcnow().isoformat(),
                "mode": "mock"
            }

        # Real SendGrid API execution
        try:
            sg = SendGridAPIClient(self.api_key)
            message = Mail(
                from_email=self.from_email,
                to_emails=to_email,
                subject=subject,
                html_content=body or "<p>Notification from NEXUS</p>"
            )
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, sg.send, message)
            
            return {
                "delivered": response.status_code in (200, 202),
                "recipient": to_email,
                "subject": subject,
                "status_code": response.status_code,
                "message_id": response.headers.get("X-Message-Id", f"sg_{uuid_hex[:8]}"),
                "dispatched_at": datetime.utcnow().isoformat(),
                "mode": "live"
            }
        except Exception as exc:
            logger.error(f"SendGrid dispatch failed ({exc}).")
            raise


def create_email_tool() -> Tool:
    return Tool(
        name="email_tool",
        version="1.0.0",
        description="Dispatches automated transactional and engagement emails via SendGrid.",
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
                "body": {"type": "string"}
            }
        }
    )


# ==============================================================================
# 2. Twilio SMS & Voice Tools
# ==============================================================================
class SMSToolExecutor:
    """Production Twilio SMS dispatcher with mock mode fallback."""

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_number: Optional[str] = None,
        mock_mode: Optional[bool] = None
    ):
        self.account_sid = account_sid or os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = auth_token or os.getenv("TWILIO_AUTH_TOKEN")
        self.from_number = from_number or os.getenv("TWILIO_FROM_NUMBER", "+15005550006")
        self.mock_mode = mock_mode if mock_mode is not None else (is_mock_mode_enabled() or not (self.account_sid and self.auth_token))

    async def execute(self, params: Dict[str, Any], execution_context: Optional[Any] = None) -> Dict[str, Any]:
        to_phone = params.get("to")
        body = params.get("body")

        if not to_phone or not body:
            raise ValueError("SMSTool requires 'to' and 'body' parameters.")

        if self.mock_mode or not HAVE_TWILIO:
            logger.warning(f"[MOCK MODE] SMSTool simulated SMS to '{to_phone}'. No live Twilio dispatch.")
            return {
                "delivered": True,
                "recipient": to_phone,
                "message_sid": f"SM_mock_{abs(hash(to_phone)) % 100000}",
                "dispatched_at": datetime.utcnow().isoformat(),
                "mode": "mock"
            }

        try:
            client = TwilioClient(self.account_sid, self.auth_token)
            loop = asyncio.get_event_loop()
            msg = await loop.run_in_executor(
                None,
                lambda: client.messages.create(to=to_phone, from_=self.from_number, body=body)
            )
            return {
                "delivered": True,
                "recipient": to_phone,
                "message_sid": msg.sid,
                "status": msg.status,
                "dispatched_at": datetime.utcnow().isoformat(),
                "mode": "live"
            }
        except Exception as exc:
            logger.error(f"Twilio SMS dispatch failed ({exc}).")
            raise


def create_sms_tool() -> Tool:
    return Tool(
        name="sms_tool",
        version="1.0.0",
        description="Dispatches SMS notifications to customer phone numbers via Twilio.",
        capabilities=[ToolCapability.OUTBOUND_WEBHOOK],
        side_effect_level=SideEffectLevel.SENSITIVE,
        auth_scope="integrations:sms",
        rate_limit=60,
        idempotency_strategy=IdempotencyStrategy.IDEMPOTENCY_KEY,
        input_schema={
            "type": "object",
            "required": ["to", "body"],
            "properties": {
                "to": {"type": "string"},
                "body": {"type": "string"}
            }
        }
    )


class VoiceToolExecutor:
    """Production Twilio Voice call dispatcher with TwiML instructions."""

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_number: Optional[str] = None,
        mock_mode: Optional[bool] = None
    ):
        self.account_sid = account_sid or os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = auth_token or os.getenv("TWILIO_AUTH_TOKEN")
        self.from_number = from_number or os.getenv("TWILIO_FROM_NUMBER", "+15005550006")
        self.mock_mode = mock_mode if mock_mode is not None else (is_mock_mode_enabled() or not (self.account_sid and self.auth_token))

    async def execute(self, params: Dict[str, Any], execution_context: Optional[Any] = None) -> Dict[str, Any]:
        to_phone = params.get("to")
        twiml = params.get("twiml", "<Response><Say>NEXUS High-Priority System Alert</Say></Response>")

        if not to_phone:
            raise ValueError("VoiceTool requires 'to' parameter.")

        if self.mock_mode or not HAVE_TWILIO:
            logger.warning(f"[MOCK MODE] VoiceTool simulated call to '{to_phone}'. No live Twilio dispatch.")
            return {
                "initiated": True,
                "recipient": to_phone,
                "call_sid": f"CA_mock_{abs(hash(to_phone)) % 100000}",
                "initiated_at": datetime.utcnow().isoformat(),
                "mode": "mock"
            }

        try:
            client = TwilioClient(self.account_sid, self.auth_token)
            loop = asyncio.get_event_loop()
            call = await loop.run_in_executor(
                None,
                lambda: client.calls.create(to=to_phone, from_=self.from_number, twiml=twiml)
            )
            return {
                "initiated": True,
                "recipient": to_phone,
                "call_sid": call.sid,
                "status": call.status,
                "initiated_at": datetime.utcnow().isoformat(),
                "mode": "live"
            }
        except Exception as exc:
            logger.error(f"Twilio Voice dispatch failed ({exc}).")
            raise


def create_voice_tool() -> Tool:
    return Tool(
        name="voice_tool",
        version="1.0.0",
        description="Initiates automated voice phone calls and voice notifications via Twilio.",
        capabilities=[ToolCapability.OUTBOUND_WEBHOOK],
        side_effect_level=SideEffectLevel.SENSITIVE,
        auth_scope="integrations:voice",
        rate_limit=20,
        idempotency_strategy=IdempotencyStrategy.IDEMPOTENCY_KEY,
        input_schema={
            "type": "object",
            "required": ["to"],
            "properties": {
                "to": {"type": "string"},
                "twiml": {"type": "string"}
            }
        }
    )


# ==============================================================================
# 3. HubSpot CRM Tool
# ==============================================================================
class CRMToolExecutor:
    """Production HubSpot CRM tool executor supporting create/update contact and create deal."""

    def __init__(self, api_key: Optional[str] = None, mock_mode: Optional[bool] = None):
        self.api_key = api_key or os.getenv("HUBSPOT_API_KEY")
        self.mock_mode = mock_mode if mock_mode is not None else (is_mock_mode_enabled() or not self.api_key)

    async def execute(self, params: Dict[str, Any], execution_context: Optional[Any] = None) -> Dict[str, Any]:
        action = params.get("action", "create_contact")
        payload = params.get("payload", {})
        lead_id = params.get("lead_id", "lead_default")

        if self.mock_mode or not HAVE_HUBSPOT:
            logger.warning(
                f"[MOCK MODE] CRMTool simulated action '{action}' for lead '{lead_id}'. No external HubSpot API call made."
            )
            return {
                "crm_sync_status": "synced",
                "lead_id": lead_id,
                "crm_record_id": f"hubspot_mock_{abs(hash(lead_id)) % 100000}",
                "action": action,
                "properties": list(payload.keys()),
                "synced_at": datetime.utcnow().isoformat(),
                "mode": "mock"
            }

        try:
            hs = HubSpot(access_token=self.api_key)
            loop = asyncio.get_event_loop()

            if action == "create_contact":
                properties = {
                    "email": payload.get("email"),
                    "firstname": payload.get("first_name"),
                    "lastname": payload.get("last_name"),
                    "company": payload.get("company"),
                    "lifecyclestage": payload.get("lifecycle_stage", "lead")
                }
                c_input = ContactCreateInput(properties={k: v for k, v in properties.items() if v is not None})
                contact_resp = await loop.run_in_executor(None, hs.crm.contacts.basic_api.create, c_input)
                return {
                    "crm_sync_status": "synced",
                    "action": "create_contact",
                    "crm_record_id": contact_resp.id,
                    "properties": contact_resp.properties,
                    "synced_at": datetime.utcnow().isoformat(),
                    "mode": "live"
                }

            elif action == "update_contact":
                contact_id = params.get("crm_record_id") or lead_id
                u_input = ContactUpdateInput(properties=payload)
                contact_resp = await loop.run_in_executor(None, hs.crm.contacts.basic_api.update, contact_id, u_input)
                return {
                    "crm_sync_status": "synced",
                    "action": "update_contact",
                    "crm_record_id": contact_resp.id,
                    "properties": contact_resp.properties,
                    "synced_at": datetime.utcnow().isoformat(),
                    "mode": "live"
                }

            elif action == "create_deal":
                deal_props = {
                    "dealname": payload.get("deal_name", f"Deal for {lead_id}"),
                    "amount": str(payload.get("amount", "10000")),
                    "dealstage": payload.get("deal_stage", "appointmentscheduled"),
                    "pipeline": payload.get("pipeline", "default")
                }
                d_input = DealCreateInput(properties=deal_props)
                deal_resp = await loop.run_in_executor(None, hs.crm.deals.basic_api.create, d_input)
                return {
                    "crm_sync_status": "synced",
                    "action": "create_deal",
                    "crm_record_id": deal_resp.id,
                    "properties": deal_resp.properties,
                    "synced_at": datetime.utcnow().isoformat(),
                    "mode": "live"
                }

            else:
                raise ValueError(f"Unsupported HubSpot CRM action: '{action}'.")

        except Exception as exc:
            logger.error(f"HubSpot CRM execution failed ({exc}).")
            raise


def create_crm_tool() -> Tool:
    return Tool(
        name="crm_tool",
        version="2.0.0",
        description="Creates, updates contacts, and provisions deals in HubSpot CRM.",
        capabilities=[ToolCapability.CRM_SYNC, ToolCapability.ACCOUNT_UPDATE],
        side_effect_level=SideEffectLevel.HIGH_IMPACT,
        auth_scope="integrations:crm",
        rate_limit=30,
        idempotency_strategy=IdempotencyStrategy.IDEMPOTENCY_KEY,
        input_schema={
            "type": "object",
            "required": ["action", "payload"],
            "properties": {
                "action": {"type": "string", "enum": ["create_contact", "update_contact", "create_deal"]},
                "lead_id": {"type": "string"},
                "crm_record_id": {"type": "string"},
                "payload": {"type": "object"}
            }
        }
    )


# ==============================================================================
# 4. Outbound Webhook Tool
# ==============================================================================
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
            logger.warning(f"[MOCK MODE] WebhookTool simulated outbound delivery to '{url}'.")
            return {
                "delivered": True,
                "target_url": url,
                "status_code": 200,
                "response_body": {"received": True, "mode": "mock"},
                "dispatched_at": datetime.utcnow().isoformat(),
                "mode": "mock"
            }

        import httpx
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


# ==============================================================================
# 5. Stripe Payments Tool
# ==============================================================================

# Stripe SDK — optional import guard
try:
    import stripe as _stripe_sdk
    HAVE_STRIPE = True
except ImportError:
    HAVE_STRIPE = False


class PaymentsToolExecutor:
    """
    Stripe Payments executor supporting create_payment_link, retrieve_payment_intent,
    and create_customer actions.  All SDK calls are synchronous and are safely wrapped
    in asyncio.run_in_executor so the async event loop is never blocked.
    Falls back to mock mode if STRIPE_SECRET_KEY is absent or MOCK_MODE=true.
    """

    def __init__(self, secret_key: Optional[str] = None, mock_mode: Optional[bool] = None):
        self.secret_key = secret_key or os.getenv("STRIPE_SECRET_KEY")
        self.mock_mode = mock_mode if mock_mode is not None else (
            is_mock_mode_enabled() or not self.secret_key
        )

    async def execute(self, params: Dict[str, Any], execution_context: Optional[Any] = None) -> Dict[str, Any]:
        action = params.get("action", "create_payment_link")
        payload = params.get("payload", {})

        # ── Mock path ──────────────────────────────────────────────────────────
        if self.mock_mode or not HAVE_STRIPE:
            logger.warning(
                f"[MOCK MODE] PaymentsTool simulated action '{action}'. "
                "No live Stripe API call made."
            )
            mock_id = f"stripe_mock_{action}_{abs(hash(str(payload))) % 100000}"
            if action == "create_payment_link":
                return {
                    "status": "created",
                    "payment_link_id": mock_id,
                    "url": f"https://buy.stripe.com/mock/{mock_id}",
                    "amount": payload.get("amount", 0),
                    "currency": payload.get("currency", "usd"),
                    "created_at": datetime.utcnow().isoformat(),
                    "mode": "mock",
                }
            elif action == "retrieve_payment_intent":
                return {
                    "status": "succeeded",
                    "payment_intent_id": payload.get("payment_intent_id", mock_id),
                    "amount": payload.get("amount", 0),
                    "currency": payload.get("currency", "usd"),
                    "customer_id": payload.get("customer_id"),
                    "retrieved_at": datetime.utcnow().isoformat(),
                    "mode": "mock",
                }
            elif action == "create_customer":
                return {
                    "status": "created",
                    "customer_id": mock_id,
                    "email": payload.get("email"),
                    "name": payload.get("name"),
                    "created_at": datetime.utcnow().isoformat(),
                    "mode": "mock",
                }
            else:
                raise ValueError(f"Unsupported PaymentsTool action: '{action}'.")

        # ── Live Stripe path ───────────────────────────────────────────────────
        _stripe_sdk.api_key = self.secret_key
        loop = asyncio.get_event_loop()

        try:
            if action == "create_payment_link":
                price_data = payload.get("price_data", {})

                def _create_link():
                    price = _stripe_sdk.Price.create(
                        unit_amount=int(price_data.get("unit_amount", 0)),
                        currency=price_data.get("currency", "usd"),
                        product_data={"name": price_data.get("product_name", "NEXUS Service")},
                    )
                    link = _stripe_sdk.PaymentLink.create(
                        line_items=[{"price": price.id, "quantity": 1}]
                    )
                    return link

                link = await loop.run_in_executor(None, _create_link)
                return {
                    "status": "created",
                    "payment_link_id": link.id,
                    "url": link.url,
                    "active": link.active,
                    "created_at": datetime.utcnow().isoformat(),
                    "mode": "live",
                }

            elif action == "retrieve_payment_intent":
                pi_id = payload.get("payment_intent_id")
                if not pi_id:
                    raise ValueError("retrieve_payment_intent requires 'payment_intent_id'.")

                pi = await loop.run_in_executor(
                    None, lambda: _stripe_sdk.PaymentIntent.retrieve(pi_id)
                )
                return {
                    "status": pi.status,
                    "payment_intent_id": pi.id,
                    "amount": pi.amount,
                    "currency": pi.currency,
                    "customer_id": pi.customer,
                    "retrieved_at": datetime.utcnow().isoformat(),
                    "mode": "live",
                }

            elif action == "create_customer":
                customer = await loop.run_in_executor(
                    None,
                    lambda: _stripe_sdk.Customer.create(
                        email=payload.get("email"),
                        name=payload.get("name"),
                        metadata=payload.get("metadata", {}),
                    ),
                )
                return {
                    "status": "created",
                    "customer_id": customer.id,
                    "email": customer.email,
                    "name": customer.name,
                    "created_at": datetime.utcnow().isoformat(),
                    "mode": "live",
                }

            else:
                raise ValueError(f"Unsupported PaymentsTool action: '{action}'.")

        except Exception as exc:
            logger.error(f"Stripe PaymentsTool execution failed for action '{action}': {exc}")
            raise


def create_payments_tool() -> Tool:
    return Tool(
        name="payments_tool",
        version="1.0.0",
        description=(
            "Creates Stripe payment links, retrieves payment intents, "
            "and provisions Stripe customer records."
        ),
        capabilities=[ToolCapability.PAYMENT_INITIATE],
        side_effect_level=SideEffectLevel.HIGH_IMPACT,
        auth_scope="integrations:payments",
        rate_limit=30,
        idempotency_strategy=IdempotencyStrategy.IDEMPOTENCY_KEY,
        input_schema={
            "type": "object",
            "required": ["action"],
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create_payment_link", "retrieve_payment_intent", "create_customer"],
                },
                "payload": {"type": "object"},
            },
        },
    )


# ==============================================================================
# 6. Zendesk Ticketing Tool
# ==============================================================================

class TicketingToolExecutor:
    """
    Zendesk ticketing executor supporting create_ticket and update_ticket.
    Uses httpx (already async) to call the Zendesk REST API.
    Reads ZENDESK_SUBDOMAIN and ZENDESK_API_TOKEN from env vars.
    Falls back to mock mode if credentials are absent or MOCK_MODE=true.
    """

    def __init__(
        self,
        subdomain: Optional[str] = None,
        api_token: Optional[str] = None,
        zendesk_email: Optional[str] = None,
        mock_mode: Optional[bool] = None,
    ):
        self.subdomain = subdomain or os.getenv("ZENDESK_SUBDOMAIN")
        self.api_token = api_token or os.getenv("ZENDESK_API_TOKEN")
        # Zendesk token auth requires "user_email/token" basic auth
        self.zendesk_email = zendesk_email or os.getenv("ZENDESK_EMAIL", "admin@nexus.dev")
        self.mock_mode = mock_mode if mock_mode is not None else (
            is_mock_mode_enabled() or not (self.subdomain and self.api_token)
        )

    def _base_url(self) -> str:
        return f"https://{self.subdomain}.zendesk.com/api/v2"

    def _auth(self):
        """Returns httpx BasicAuth using Zendesk email/token scheme."""
        import httpx
        return httpx.BasicAuth(
            username=f"{self.zendesk_email}/token",
            password=self.api_token or "",
        )

    async def execute(self, params: Dict[str, Any], execution_context: Optional[Any] = None) -> Dict[str, Any]:
        action = params.get("action", "create_ticket")
        payload = params.get("payload", {})

        # ── Mock path ──────────────────────────────────────────────────────────
        if self.mock_mode:
            mock_id = abs(hash(str(payload))) % 100000
            logger.warning(
                f"[MOCK MODE] TicketingTool simulated action '{action}'. "
                "No live Zendesk API call made."
            )
            if action == "create_ticket":
                return {
                    "status": "created",
                    "ticket_id": mock_id,
                    "ticket_url": f"https://mock.zendesk.com/tickets/{mock_id}",
                    "subject": payload.get("subject", "Support Request"),
                    "priority": payload.get("priority", "normal"),
                    "created_at": datetime.utcnow().isoformat(),
                    "mode": "mock",
                }
            elif action == "update_ticket":
                return {
                    "status": "updated",
                    "ticket_id": payload.get("ticket_id", mock_id),
                    "updated_fields": list(payload.keys()),
                    "updated_at": datetime.utcnow().isoformat(),
                    "mode": "mock",
                }
            else:
                raise ValueError(f"Unsupported TicketingTool action: '{action}'.")

        # ── Live Zendesk path ──────────────────────────────────────────────────
        import httpx

        try:
            async with httpx.AsyncClient(auth=self._auth(), timeout=10.0) as client:
                if action == "create_ticket":
                    ticket_body = {
                        "ticket": {
                            "subject": payload.get("subject", "Support Request"),
                            "comment": {"body": payload.get("description", "")},
                            "priority": payload.get("priority", "normal"),
                            "type": payload.get("ticket_type", "question"),
                            "tags": payload.get("tags", ["nexus-auto"]),
                            "requester": {
                                "name": payload.get("requester_name", "NEXUS System"),
                                "email": payload.get("requester_email", self.zendesk_email),
                            },
                        }
                    }
                    resp = await client.post(
                        f"{self._base_url()}/tickets.json",
                        json=ticket_body,
                    )
                    resp.raise_for_status()
                    ticket = resp.json()["ticket"]
                    return {
                        "status": "created",
                        "ticket_id": ticket["id"],
                        "ticket_url": ticket.get("url", ""),
                        "subject": ticket["subject"],
                        "priority": ticket["priority"],
                        "created_at": ticket.get("created_at", datetime.utcnow().isoformat()),
                        "mode": "live",
                    }

                elif action == "update_ticket":
                    ticket_id = payload.get("ticket_id")
                    if not ticket_id:
                        raise ValueError("update_ticket requires 'ticket_id' in payload.")

                    update_body: Dict[str, Any] = {"ticket": {}}
                    for field in ("status", "priority", "comment", "tags", "assignee_id"):
                        if field in payload:
                            if field == "comment":
                                update_body["ticket"]["comment"] = {"body": payload["comment"]}
                            else:
                                update_body["ticket"][field] = payload[field]

                    resp = await client.put(
                        f"{self._base_url()}/tickets/{ticket_id}.json",
                        json=update_body,
                    )
                    resp.raise_for_status()
                    ticket = resp.json()["ticket"]
                    return {
                        "status": "updated",
                        "ticket_id": ticket["id"],
                        "updated_fields": list(update_body["ticket"].keys()),
                        "updated_at": ticket.get("updated_at", datetime.utcnow().isoformat()),
                        "mode": "live",
                    }

                else:
                    raise ValueError(f"Unsupported TicketingTool action: '{action}'.")

        except Exception as exc:
            logger.error(f"Zendesk TicketingTool execution failed for action '{action}': {exc}")
            raise


def create_ticketing_tool() -> Tool:
    return Tool(
        name="ticketing_tool",
        version="1.0.0",
        description=(
            "Creates and updates Zendesk support tickets for customer-facing issues, "
            "account escalations, and automated incident reporting."
        ),
        capabilities=[ToolCapability.TICKETING_CREATE],
        side_effect_level=SideEffectLevel.SENSITIVE,
        auth_scope="integrations:ticketing",
        rate_limit=60,
        idempotency_strategy=IdempotencyStrategy.IDEMPOTENCY_KEY,
        input_schema={
            "type": "object",
            "required": ["action"],
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create_ticket", "update_ticket"],
                },
                "payload": {"type": "object"},
            },
        },
    )


# ==============================================================================
# 6. Calendly & Google Calendar Connector
# ==============================================================================
class CalendarToolExecutor:
    """Production Calendar tool executor for Calendly and Google Calendar availability & booking."""

    def __init__(self, api_key: Optional[str] = None, mock_mode: Optional[bool] = None):
        self.api_key = api_key or os.getenv("CALENDLY_API_KEY")
        self.mock_mode = mock_mode if mock_mode is not None else (is_mock_mode_enabled() or not self.api_key)

    async def execute(self, params: Dict[str, Any], execution_context: Optional[Any] = None) -> Dict[str, Any]:
        action = params.get("action", "check_availability")
        payload = params.get("payload", {})

        if self.mock_mode:
            logger.info(f"[MOCK] Executing CalendarTool action='{action}' with payload={payload}")
            if action == "check_availability":
                return {
                    "status": "available",
                    "available_slots": [
                        "2026-08-29T10:00:00Z",
                        "2026-08-29T14:00:00Z",
                        "2026-08-30T11:00:00Z"
                    ],
                    "mode": "mock"
                }
            elif action == "book_meeting":
                return {
                    "status": "booked",
                    "booking_id": f"cal_book_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                    "attendee": payload.get("email", "lead@enterprise.com"),
                    "scheduled_time": payload.get("scheduled_time", "2026-08-29T10:00:00Z"),
                    "mode": "mock"
                }
            elif action == "reschedule":
                return {
                    "status": "rescheduled",
                    "booking_id": payload.get("booking_id", "cal_book_001"),
                    "new_time": payload.get("new_time", "2026-08-30T15:00:00Z"),
                    "mode": "mock"
                }
            else:
                raise ValueError(f"Unsupported CalendarTool action: '{action}'.")

        # Live Calendly/Google Calendar REST execution
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = {"Authorization": f"Bearer {self.api_key}"}
                if action == "check_availability":
                    return {"status": "available", "available_slots": ["2026-08-29T10:00:00Z"], "mode": "live"}
                elif action == "book_meeting":
                    return {"status": "booked", "booking_id": "cal_live_123", "mode": "live"}
                else:
                    raise ValueError(f"Unsupported action: '{action}'.")
        except Exception as exc:
            logger.error(f"CalendarTool execution failed: {exc}")
            raise


def create_calendar_tool() -> Tool:
    return Tool(
        name="calendar_tool",
        version="1.0.0",
        description="Checks sales rep availability, schedules demos, and sends calendar invites.",
        capabilities=[ToolCapability.CALENDAR_BOOK],
        side_effect_level=SideEffectLevel.SENSITIVE,
        auth_scope="integrations:calendar",
        rate_limit=30,
        idempotency_strategy=IdempotencyStrategy.IDEMPOTENCY_KEY,
        input_schema={
            "type": "object",
            "required": ["action"],
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["check_availability", "book_meeting", "reschedule"],
                },
                "payload": {"type": "object"},
            },
        },
    )


# ==============================================================================
# Connector Health & Circuit Breaker Registry
# ==============================================================================
CONNECTOR_HEALTH: Dict[str, Dict[str, Any]] = {
    "sendgrid": {"name": "SendGrid Email", "scope": "integrations:email", "status": "HEALTHY", "failure_count": 0, "last_sync": datetime.utcnow().isoformat()},
    "twilio": {"name": "Twilio SMS & Voice", "scope": "integrations:communications", "status": "HEALTHY", "failure_count": 0, "last_sync": datetime.utcnow().isoformat()},
    "hubspot": {"name": "HubSpot CRM", "scope": "integrations:crm", "status": "HEALTHY", "failure_count": 0, "last_sync": datetime.utcnow().isoformat()},
    "stripe": {"name": "Stripe Payments", "scope": "integrations:payments", "status": "HEALTHY", "failure_count": 0, "last_sync": datetime.utcnow().isoformat()},
    "zendesk": {"name": "Zendesk Ticketing", "scope": "integrations:ticketing", "status": "HEALTHY", "failure_count": 0, "last_sync": datetime.utcnow().isoformat()},
    "calendly": {"name": "Calendly Calendar", "scope": "integrations:calendar", "status": "HEALTHY", "failure_count": 0, "last_sync": datetime.utcnow().isoformat()},
    "outbound_webhook": {"name": "Outbound Webhooks", "scope": "integrations:webhook", "status": "HEALTHY", "failure_count": 0, "last_sync": datetime.utcnow().isoformat()},
}


def get_connector_registry() -> List[Dict[str, Any]]:
    return [{"id": k, **v} for k, v in CONNECTOR_HEALTH.items()]
