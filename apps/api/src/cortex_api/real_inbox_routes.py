from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:
    from cortex_api.real_agentic_inbox import (
        EmailMessage,
        EmailThread,
        AIEmailAgent,
        InboxState,
        AsyncEmailWorker,
        AgentCoordinator,
    )
except ImportError:
    from Cortex.apps.api.src.cortex_api.real_agentic_inbox import (
        EmailMessage,
        EmailThread,
        AIEmailAgent,
        InboxState,
        AsyncEmailWorker,
        AgentCoordinator,
    )

logger = logging.getLogger("cortex.real_inbox_routes")
router = APIRouter(prefix="/inbox", tags=["Agentic Inbox"])

# In-memory inbox state for persistent session triage
_inbox = InboxState()
_agent = AIEmailAgent()


class EmailPayload(BaseModel):
    sender: str = "partner@enterprise.com"
    recipient: str = "friday@universe.ai"
    subject: str = "Strategic Integration Meeting & Q4 Roadmap"
    body: str = "Let's schedule a meeting tomorrow to review the architecture. Please send the financial report by Friday."


class ActionExtractPayload(BaseModel):
    text: str = "Please review the deployment pipeline. You must submit the security audit by end of day."


class BatchEmailsPayload(BaseModel):
    messages: List[EmailPayload]


@router.post("/classify")
def classify_email(payload: EmailPayload):
    """Classify incoming email message, detect priority, sentiment, spam, and auto-labels."""
    msg = EmailMessage.create_message(
        sender=payload.sender,
        recipient=payload.recipient,
        subject=payload.subject,
        body=payload.body,
    )
    _inbox.add_message(msg)

    intent = AIEmailAgent.classify_email(msg)
    sentiment = AIEmailAgent.detect_sentiment(payload.body)
    is_spam = AIEmailAgent.detect_spam(msg)
    labels = AIEmailAgent.auto_label(msg)
    summary = AIEmailAgent.summarize_email(msg)

    return {
        "status": "success",
        "engine": "AgenticInbox",
        "message_id": msg.message_id,
        "classification": intent,
        "priority_score": msg.priority_score,
        "sentiment": sentiment,
        "is_spam": is_spam,
        "labels": labels,
        "summary": summary,
        "total_inbox_messages": len(_inbox.messages),
    }


@router.post("/actions")
def extract_actions(payload: ActionExtractPayload):
    """Extract actionable tasks, deadlines, and urgency items from message text."""
    items = AIEmailAgent.extract_action_items(payload.text)
    return {
        "status": "success",
        "engine": "AgenticInbox",
        "action_items": items,
        "item_count": len(items),
    }


@router.post("/summarize")
def summarize_email_message(payload: EmailPayload):
    """Generate concise executive summary of email content."""
    msg = EmailMessage.create_message(
        sender=payload.sender,
        recipient=payload.recipient,
        subject=payload.subject,
        body=payload.body,
    )
    summary = AIEmailAgent.summarize_email(msg)
    return {
        "status": "success",
        "engine": "AgenticInbox",
        "summary": summary,
    }


@router.post("/triage")
def triage_inbox(payload: BatchEmailsPayload):
    """Triage a batch of emails into functional categories and priorities."""
    temp_inbox = InboxState()
    for item in payload.messages:
        msg = EmailMessage.create_message(
            sender=item.sender,
            recipient=item.recipient,
            subject=item.subject,
            body=item.body,
        )
        temp_inbox.add_message(msg)

    triage_result = AsyncEmailWorker.triage_messages(temp_inbox)
    processed = AsyncEmailWorker.process_inbox(temp_inbox, _agent)

    return {
        "status": "success",
        "engine": "AgenticInbox",
        "triage": triage_result,
        "processed_metrics": processed,
    }


@router.get("/digest")
def generate_inbox_digest():
    """Generate daily inbox digest with unread counts and top senders."""
    digest = AsyncEmailWorker.generate_digest(_inbox)
    return {
        "status": "success",
        "engine": "AgenticInbox",
        "digest": digest,
    }


@router.post("/coordinate")
def coordinate_email_routing(payload: BatchEmailsPayload):
    """Coordinate multi-agent routing and generate execution plan."""
    msgs = [
        EmailMessage.create_message(
            sender=m.sender,
            recipient=m.recipient,
            subject=m.subject,
            body=m.body,
        )
        for m in payload.messages
    ]

    routed = [{ "subject": m.subject, "agent": AgentCoordinator.route_message(m) } for m in msgs]
    plan = AgentCoordinator.coordination_plan(msgs)

    return {
        "status": "success",
        "engine": "AgenticInbox",
        "routing": routed,
        "coordination_plan": plan,
    }
