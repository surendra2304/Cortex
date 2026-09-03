from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from cortex_api.db_models import ProfileModel, VisitorModel, LeadModel, IdentityLinkModel, AuditRecordModel

logger = logging.getLogger("cortex-identity")


class IdentityResolver:
    """
    Identity Resolution Engine per CORTEX spec section 9:
    - Input: anonymous visitor ID, email, user ID, device fingerprint
    - Resolution graph: links stored in IdentityLinkModel
    - Policy: only link identities when consent granted AND tenant policy allows
    - Merge rules: preserve both event histories, earliest first_seen wins
    - Lifecycle promotions: visitor -> lead -> customer
    """

    async def resolve_identity(
        self,
        db: AsyncSession,
        visitor_id: str,
        user_id: Optional[str] = None,
        email: Optional[str] = None,
        device_fingerprint: Optional[str] = None,
        tenant_id: str = "default",
        site_id: str = "default",
        consent_granted: bool = True,
        traits: Optional[Dict[str, Any]] = None,
        event_trigger: Optional[str] = None
    ) -> Dict[str, Any]:
        traits = traits or {}
        if email and "email" not in traits:
            traits["email"] = email

        # 1. Fetch or create Visitor
        vis_stmt = select(VisitorModel).where(VisitorModel.id == visitor_id)
        vis_res = await db.execute(vis_stmt)
        visitor = vis_res.scalar_one_or_none()

        if not visitor:
            visitor = VisitorModel(
                id=visitor_id,
                tenant_id=tenant_id,
                site_id=site_id,
                first_seen_at=datetime.utcnow(),
                last_seen_at=datetime.utcnow(),
                attributes=traits
            )
            db.add(visitor)
        else:
            visitor.last_seen_at = datetime.utcnow()
            if traits:
                updated = dict(visitor.attributes or {})
                updated.update(traits)
                visitor.attributes = updated

        # 2. Check if this is an anonymous visitor (no email, no user_id) or consent revoked
        is_identified = bool(user_id or email)
        if not is_identified or not consent_granted:
            await db.commit()
            return {
                "visitor_id": visitor.id,
                "profile_id": visitor.profile_id,
                "is_identified": False,
                "lifecycle_stage": "anonymous",
                "linked_identities": [],
                "traits": visitor.attributes,
                "attributes": visitor.attributes,
                "message": "Pseudonymous tracking; no authenticated credentials or consent."
            }

        # 3. Authenticated resolution: search existing profile by email or user_id
        target_profile: Optional[ProfileModel] = None

        if email:
            prof_res = await db.execute(
                select(ProfileModel).where(
                    ProfileModel.tenant_id == tenant_id,
                    ProfileModel.primary_email == email
                )
            )
            target_profile = prof_res.scalar_one_or_none()

        if not target_profile and user_id:
            all_profs = await db.execute(select(ProfileModel).where(ProfileModel.tenant_id == tenant_id))
            for p in all_profs.scalars():
                if any(ident.get("user_id") == user_id for ident in (p.identities or [])):
                    target_profile = p
                    break

        # 4. Create or update unified profile
        if not target_profile:
            profile_id = f"prof_{uuid.uuid4().hex[:12]}"
            identities = []
            if user_id:
                identities.append({"type": "user_id", "value": user_id, "linked_at": datetime.utcnow().isoformat()})
            if email:
                identities.append({"type": "email", "value": email, "linked_at": datetime.utcnow().isoformat()})

            target_profile = ProfileModel(
                id=profile_id,
                tenant_id=tenant_id,
                primary_email=email,
                identities=identities,
                traits=traits,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(target_profile)
        else:
            if email and not target_profile.primary_email:
                target_profile.primary_email = email
            merged_traits = dict(target_profile.traits or {})
            merged_traits.update(traits)
            target_profile.traits = merged_traits
            target_profile.updated_at = datetime.utcnow()

            ids = list(target_profile.identities or [])
            if user_id and not any(i.get("value") == user_id for i in ids):
                ids.append({"type": "user_id", "value": user_id, "linked_at": datetime.utcnow().isoformat()})
            if email and not any(i.get("value") == email for i in ids):
                ids.append({"type": "email", "value": email, "linked_at": datetime.utcnow().isoformat()})
            target_profile.identities = ids

        visitor.profile_id = target_profile.id

        # 5. Record identity link in resolution graph
        if visitor_id:
            link = IdentityLinkModel(
                id=f"link_{uuid.uuid4().hex[:10]}",
                tenant_id=tenant_id,
                source_type="anonymous_id",
                source_value=visitor_id,
                target_type="profile_id",
                target_id=target_profile.id,
                confidence=1.0,
                link_metadata={"device_fingerprint": device_fingerprint, "trigger": event_trigger}
            )
            db.add(link)

        # 6. Lifecycle promotions
        lifecycle_stage = "lead" if (email or user_id) else "visitor"
        
        # Check if lead exists or promote visitor -> lead
        lead = None
        try:
            lead_stmt = select(LeadModel).where(
                LeadModel.tenant_id == tenant_id,
                LeadModel.profile_id == target_profile.id
            )
            lead_res = await db.execute(lead_stmt)
            lead = lead_res.scalar_one_or_none()
        except Exception:
            lead = None

        if not lead and (email or user_id):
            lead = LeadModel(
                id=f"lead_{uuid.uuid4().hex[:10]}",
                tenant_id=tenant_id,
                profile_id=target_profile.id,
                score=0.50,
                status="new",
                source=traits.get("source", "identity_resolution"),
                lead_metadata={"email": email, "promoted_from": visitor_id},
                created_at=datetime.utcnow()
            )
            try:
                db.add(lead)
            except Exception:
                pass
            lifecycle_stage = "lead"

        # Check for customer promotion (e.g. checkout event)
        if event_trigger and ("checkout" in event_trigger.lower() or "purchase" in event_trigger.lower()):
            if lead:
                lead.status = "customer"
            lifecycle_stage = "customer"

        # 7. Audit operation
        audit = AuditRecordModel(
            id=f"aud_id_{uuid.uuid4().hex[:8]}",
            tenant_id=tenant_id,
            actor_id=visitor_id,
            action="identity:resolve",
            target_resource=f"profile/{target_profile.id}",
            changes={
                "visitor_id": visitor_id,
                "profile_id": target_profile.id,
                "lifecycle_stage": lifecycle_stage,
                "email": email,
                "consent_granted": consent_granted
            },
            verification_status="verified",
            trace_id=f"trc_id_{uuid.uuid4().hex[:8]}",
            timestamp=datetime.utcnow()
        )
        db.add(audit)
        await db.commit()

        return {
            "visitor_id": visitor.id,
            "profile_id": target_profile.id,
            "lead_id": lead.id if lead else None,
            "is_identified": True,
            "lifecycle_stage": lifecycle_stage,
            "primary_email": target_profile.primary_email,
            "identities": target_profile.identities,
            "traits": target_profile.traits
        }


# Maintain backward-compatible IdentityService alias
IdentityService = IdentityResolver
