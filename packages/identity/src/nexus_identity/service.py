from typing import Optional, Dict, Any
from datetime import datetime
import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from nexus_core.models import Profile, Visitor
from nexus_api.db_models import ProfileModel, VisitorModel

logger = logging.getLogger("nexus-identity")


class IdentityService:
    """Identity Resolution Engine for stitching anonymous visitors to unified profiles."""

    async def resolve_identity(
        self,
        db: AsyncSession,
        visitor_id: str,
        user_id: Optional[str] = None,
        tenant_id: str = "default",
        site_id: str = "default",
        traits: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        traits = traits or {}
        email = traits.get("email")

        # 1. Fetch or create VisitorModel
        vis_stmt = select(VisitorModel).where(VisitorModel.id == visitor_id)
        vis_result = await db.execute(vis_stmt)
        visitor_record = vis_result.scalar_one_or_none()

        if not visitor_record:
            visitor_record = VisitorModel(
                id=visitor_id,
                tenant_id=tenant_id,
                site_id=site_id,
                first_seen_at=datetime.utcnow(),
                last_seen_at=datetime.utcnow(),
                attributes=traits
            )
            db.add(visitor_record)
        else:
            visitor_record.last_seen_at = datetime.utcnow()
            if traits:
                updated_attrs = dict(visitor_record.attributes or {})
                updated_attrs.update(traits)
                visitor_record.attributes = updated_attrs

        # 2. If no authenticated user_id or email provided, return pseudonymous visitor record
        if not user_id and not email:
            await db.commit()
            return {
                "visitor_id": visitor_record.id,
                "profile_id": visitor_record.profile_id,
                "is_identified": False,
                "attributes": visitor_record.attributes
            }

        # 3. Authenticated resolution: Find existing profile by email or user identity
        target_profile: Optional[ProfileModel] = None

        if email:
            prof_stmt = select(ProfileModel).where(
                ProfileModel.tenant_id == tenant_id,
                ProfileModel.primary_email == email
            )
            prof_res = await db.execute(prof_stmt)
            target_profile = prof_res.scalar_one_or_none()

        if not target_profile and user_id:
            # Search by user_id in identities list
            prof_all = await db.execute(select(ProfileModel).where(ProfileModel.tenant_id == tenant_id))
            for p in prof_all.scalars():
                for ident in p.identities or []:
                    if ident.get("user_id") == user_id:
                        target_profile = p
                        break
                if target_profile:
                    break

        # 4. Create new ProfileModel if none matched
        if not target_profile:
            profile_id = f"prof_{uuid.uuid4().hex[:12]}"
            identities = [{"user_id": user_id, "linked_at": datetime.utcnow().isoformat()}] if user_id else []
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
            logger.info(f"Created new Profile '{profile_id}' for visitor '{visitor_id}'.")
        else:
            # Merge traits and identities
            existing_traits = dict(target_profile.traits or {})
            existing_traits.update(traits)
            target_profile.traits = existing_traits
            target_profile.updated_at = datetime.utcnow()

            if user_id:
                existing_ids = list(target_profile.identities or [])
                if not any(i.get("user_id") == user_id for i in existing_ids):
                    existing_ids.append({"user_id": user_id, "linked_at": datetime.utcnow().isoformat()})
                    target_profile.identities = existing_ids

        # 5. Link visitor to the resolved profile
        visitor_record.profile_id = target_profile.id
        await db.commit()

        return {
            "visitor_id": visitor_record.id,
            "profile_id": target_profile.id,
            "is_identified": True,
            "primary_email": target_profile.primary_email,
            "identities": target_profile.identities,
            "traits": target_profile.traits
        }
