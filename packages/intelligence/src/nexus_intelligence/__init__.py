from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class ContextPackage(BaseModel):
    session_context: Dict[str, Any] = Field(default_factory=dict)
    visitor_context: Dict[str, Any] = Field(default_factory=dict)
    lead_context: Dict[str, Any] = Field(default_factory=dict)
    site_context: Dict[str, Any] = Field(default_factory=dict)
    intent_level: str = "LOW"  # HIGH_INTENT, MEDIUM, LOW
    intent_score: float = 0.0
    anomaly_flags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ContextBuilder:
    """
    Context Engine per NEXUS spec section 11:
    - Builds decision-ready typed ContextPackage for agents
    - Computes deterministic intent score and intent level
    - Detects session anomaly flags (rage clicks, error spikes, high velocity)
    """

    def build_context(
        self,
        event: Dict[str, Any],
        session_events: List[Dict[str, Any]],
        actor_events: List[Dict[str, Any]],
        visitor_attributes: Dict[str, Any],
        profile_traits: Dict[str, Any],
        lead_info: Optional[Dict[str, Any]] = None,
        site_metrics: Optional[Dict[str, Any]] = None
    ) -> ContextPackage:
        all_events = [event] + session_events

        # 1. Intent Detection (Deterministic with explicit weights)
        pricing_count = sum(1 for e in all_events if "pricing" in str(e.get("type", "")).lower())
        demo_count = sum(1 for e in all_events if "demo" in str(e.get("type", "")).lower())
        enterprise_count = sum(1 for e in all_events if any(k in str(e.get("type", "")).lower() for k in ["enterprise", "security"]))
        security_count = sum(1 for e in all_events if "security" in str(e.get("type", "")).lower())

        raw_intent = (pricing_count * 0.30) + (demo_count * 0.40) + (enterprise_count * 0.50) + (security_count * 0.20)
        intent_score = round(min(raw_intent, 1.0), 2)

        if intent_score >= 0.70:
            intent_level = "HIGH_INTENT"
        elif intent_score >= 0.40:
            intent_level = "MEDIUM"
        else:
            intent_level = "LOW"

        # 2. Anomaly flags
        anomalies = []
        error_count = sum(1 for e in all_events if "error" in str(e.get("type", "")).lower())
        if error_count >= 3:
            anomalies.append("high_session_error_count")
        
        rage_clicks = sum(1 for e in all_events if "rage" in str(e.get("type", "")).lower())
        if rage_clicks >= 2:
            anomalies.append("rage_clicks_detected")

        if len(session_events) > 30:
            anomalies.append("unusual_velocity_spike")

        # 3. Assemble sub-contexts
        session_ctx = {
            "events_count": len(all_events),
            "pages_viewed": len([e for e in all_events if "page_view" in str(e.get("type", "")).lower()]),
            "error_count": error_count,
            "pricing_views": pricing_count,
            "demo_views": demo_count,
            "exit_intent": any("exit" in str(e.get("type", "")).lower() for e in all_events)
        }

        visitor_ctx = {
            "first_seen": visitor_attributes.get("first_seen_at"),
            "attributes": visitor_attributes,
            "cross_session_events_count": len(actor_events),
            "profile_traits": profile_traits
        }

        lead_ctx = lead_info or {
            "lifecycle_stage": "lead" if profile_traits.get("email") else "visitor",
            "lead_score": intent_score
        }

        site_ctx = site_metrics or {
            "traffic_health": "normal",
            "active_incidents_count": 0
        }

        return ContextPackage(
            session_context=session_ctx,
            visitor_context=visitor_ctx,
            lead_context=lead_ctx,
            site_context=site_ctx,
            intent_level=intent_level,
            intent_score=intent_score,
            anomaly_flags=anomalies
        )
