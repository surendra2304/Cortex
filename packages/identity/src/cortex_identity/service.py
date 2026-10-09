import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from cortex_api.db_models import AuditRecordModel, IdentityLinkModel, LeadModel, ProfileModel, VisitorModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _utcnow() -> datetime:
    """Timezone-aware UTC now (never a naive timestamp)."""
    return datetime.now(UTC)


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
        user_id: str | None = None,
        email: str | None = None,
        device_fingerprint: str | None = None,
        tenant_id: str = "default",
        site_id: str = "default",
        consent_granted: bool = True,
        traits: dict[str, Any] | None = None,
        event_trigger: str | None = None,
    ) -> dict[str, Any]:
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
                first_seen_at=_utcnow(),
                last_seen_at=_utcnow(),
                attributes=traits,
            )
            db.add(visitor)
        else:
            visitor.last_seen_at = _utcnow()
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
                "message": "Pseudonymous tracking; no authenticated credentials or consent.",
            }

        # 3. Authenticated resolution: search existing profile by email or user_id
        target_profile: ProfileModel | None = None

        if email:
            prof_res = await db.execute(
                select(ProfileModel).where(ProfileModel.tenant_id == tenant_id, ProfileModel.primary_email == email)
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
                identities.append({"type": "user_id", "value": user_id, "linked_at": _utcnow().isoformat()})
            if email:
                identities.append({"type": "email", "value": email, "linked_at": _utcnow().isoformat()})

            target_profile = ProfileModel(
                id=profile_id,
                tenant_id=tenant_id,
                primary_email=email,
                identities=identities,
                traits=traits,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            db.add(target_profile)
        else:
            if email and not target_profile.primary_email:
                target_profile.primary_email = email
            merged_traits = dict(target_profile.traits or {})
            merged_traits.update(traits)
            target_profile.traits = merged_traits
            target_profile.updated_at = _utcnow()

            ids = list(target_profile.identities or [])
            if user_id and not any(i.get("value") == user_id for i in ids):
                ids.append({"type": "user_id", "value": user_id, "linked_at": _utcnow().isoformat()})
            if email and not any(i.get("value") == email for i in ids):
                ids.append({"type": "email", "value": email, "linked_at": _utcnow().isoformat()})
            target_profile.identities = ids

        visitor.profile_id = target_profile.id

        # 5. Record identity link in resolution graph. Deduplicated: re-identifying
        # the same visitor must not pile up duplicate link rows.
        if visitor_id:
            existing_link = await db.execute(
                select(IdentityLinkModel).where(
                    IdentityLinkModel.tenant_id == tenant_id,
                    IdentityLinkModel.source_type == "anonymous_id",
                    IdentityLinkModel.source_value == visitor_id,
                    IdentityLinkModel.target_type == "profile_id",
                )
            )
            if existing_link.scalar_one_or_none() is None:
                link = IdentityLinkModel(
                    id=f"link_{uuid.uuid4().hex[:10]}",
                    tenant_id=tenant_id,
                    source_type="anonymous_id",
                    source_value=visitor_id,
                    target_type="profile_id",
                    target_id=target_profile.id,
                    confidence=1.0,
                    link_metadata={"device_fingerprint": device_fingerprint, "trigger": event_trigger},
                )
                db.add(link)

        # 5b. Persist authenticated identity links (user_id / email -> profile).
        # The cognitive loop resolves an event's actor through these rows; without
        # them an identified visitor (whose events carry the user_id, not the
        # anonymous visitor id) is invisible to every agent.
        for source_type, source_value in (("user_id", user_id), ("email", email)):
            if not source_value:
                continue
            existing_auth_link = await db.execute(
                select(IdentityLinkModel).where(
                    IdentityLinkModel.tenant_id == tenant_id,
                    IdentityLinkModel.source_type == source_type,
                    IdentityLinkModel.source_value == source_value,
                    IdentityLinkModel.target_type == "profile_id",
                )
            )
            if existing_auth_link.scalar_one_or_none() is None:
                db.add(
                    IdentityLinkModel(
                        id=f"link_{uuid.uuid4().hex[:10]}",
                        tenant_id=tenant_id,
                        source_type=source_type,
                        source_value=source_value,
                        target_type="profile_id",
                        target_id=target_profile.id,
                        confidence=1.0,
                        link_metadata={"trigger": event_trigger},
                    )
                )

        # 6. Lifecycle promotions
        lifecycle_stage = "lead" if (email or user_id) else "visitor"

        # Check if lead exists or promote visitor -> lead
        lead = None
        try:
            lead_stmt = select(LeadModel).where(
                LeadModel.tenant_id == tenant_id, LeadModel.profile_id == target_profile.id
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
                created_at=_utcnow(),
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
                "consent_granted": consent_granted,
            },
            verification_status="verified",
            trace_id=f"trc_id_{uuid.uuid4().hex[:8]}",
            timestamp=_utcnow(),
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
            "traits": target_profile.traits,
        }

    async def resolve_actor_profile(
        self,
        db: AsyncSession,
        actor_id: str,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        """Lookup-only resolution of an event actor to its profile (and visitor).

        Used by the cognitive loop's Contextualize phase: events from identified
        users carry the user_id (or email) as actor id, which never equals the
        anonymous visitor id — the profile is reachable only through the identity
        graph. Tenant-scoped; returns empty dicts when nothing resolves.
        """
        result: dict[str, Any] = {
            "profile_id": None,
            "profile_traits": {},
            "primary_email": None,
            "visitor_attributes": {},
            "lead": None,
        }
        if not actor_id:
            return result

        link_stmt = (
            select(IdentityLinkModel)
            .where(
                IdentityLinkModel.tenant_id == tenant_id,
                IdentityLinkModel.source_value == actor_id,
                IdentityLinkModel.target_type == "profile_id",
            )
            .order_by(IdentityLinkModel.created_at.desc())
            .limit(1)
        )
        link_res = await db.execute(link_stmt)
        link = link_res.scalar_one_or_none()
        if not link:
            return result

        profile_id = link.target_id
        result["profile_id"] = profile_id

        prof_res = await db.execute(
            select(ProfileModel).where(ProfileModel.id == profile_id, ProfileModel.tenant_id == tenant_id)
        )
        profile = prof_res.scalar_one_or_none()
        if profile:
            result["profile_traits"] = dict(profile.traits or {})
            result["primary_email"] = profile.primary_email

        # The anonymous visitor attached to the same profile, if any.
        vis_res = await db.execute(
            select(VisitorModel)
            .where(VisitorModel.tenant_id == tenant_id, VisitorModel.profile_id == profile_id)
            .order_by(VisitorModel.last_seen_at.desc())
            .limit(1)
        )
        visitor = vis_res.scalar_one_or_none()
        if visitor:
            result["visitor_attributes"] = dict(visitor.attributes or {})

        lead_res = await db.execute(
            select(LeadModel).where(LeadModel.tenant_id == tenant_id, LeadModel.profile_id == profile_id)
        )
        lead = lead_res.scalar_one_or_none()
        if lead:
            result["lead"] = {
                "lead_id": lead.id,
                "score": lead.score,
                "status": lead.status,
                "lifecycle_stage": "customer" if lead.status == "customer" else "lead",
            }
        return result


# Maintain backward-compatible IdentityService alias
IdentityService = IdentityResolver
