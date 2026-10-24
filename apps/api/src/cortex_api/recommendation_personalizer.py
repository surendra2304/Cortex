"""
Cortex/apps/api/src/cortex_api/recommendation_personalizer.py — Cortex Recommendation Personalizer.

Product recommendations, collaborative filtering, content-based filtering,
and real-time personalization.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter()


@dataclass
class UserProfile:
    """A user profile for personalization."""
    user_id: str
    preferences: dict[str, float] = field(default_factory=dict)
    viewed_items: list[str] = field(default_factory=list)
    purchased_items: list[str] = field(default_factory=list)
    similarity_to_others: dict[str, float] = field(default_factory=dict)


@dataclass
class Product:
    """A product for recommendation."""
    product_id: str
    name: str
    category: str
    tags: list[str] = field(default_factory=list)
    price: float = 0.0
    popularity: float = 0.0


@dataclass
class Recommendation:
    """A product recommendation."""
    recommendation_id: str
    user_id: str
    product_id: str
    product_name: str
    score: float = 0.0
    reason: str = ""
    method: str = "collaborative"  # collaborative, content-based, popular


class RecommendationPersonalizer:
    """Engine for personalized recommendations."""

    def __init__(self) -> None:
        self._users: dict[str, UserProfile] = {}
        self._products: dict[str, Product] = {}
        self._recommendations: list[Recommendation] = []

    def add_user(self, user_id: str, preferences: dict[str, float] | None = None) -> UserProfile:
        """Add a user profile."""
        user = UserProfile(user_id=user_id, preferences=preferences or {})
        self._users[user_id] = user
        return user

    def add_product(self, product_id: str, name: str, category: str,
                    tags: list[str] | None = None, price: float = 0.0) -> Product:
        """Add a product."""
        product = Product(product_id=product_id, name=name, category=category,
                         tags=tags or [], price=price, popularity=1.0)
        self._products[product_id] = product
        return product

    def record_view(self, user_id: str, product_id: str) -> None:
        """Record a product view."""
        user = self._users.get(user_id)
        if user and product_id not in user.viewed_items:
            user.viewed_items.append(product_id)

    def generate_recommendations(self, user_id: str, top_n: int = 5) -> list[Recommendation]:
        """Generate personalized recommendations."""
        user = self._users.get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        recs = []
        viewed = set(user.viewed_items)

        # Content-based filtering
        for product_id, product in self._products.items():
            if product_id in viewed:
                continue
            score = 0.5
            reason = "Recommended based on content similarity"
            method = "content-based"
            # Boost by matching preferences
            for tag in product.tags:
                if tag in user.preferences:
                    score += user.preferences[tag] * 0.2
                    reason = f"Matches your interest in {tag}"

            rec = Recommendation(
                recommendation_id=f"rec_{uuid.uuid4().hex[:8]}",
                user_id=user_id, product_id=product_id,
                product_name=product.name, score=min(1.0, score),
                reason=reason, method=method,
            )
            recs.append(rec)

        # Sort by score
        recs.sort(key=lambda r: r.score, reverse=True)
        top_recs = recs[:top_n]
        self._recommendations.extend(top_recs)
        return top_recs

    def get_user_profile(self, user_id: str) -> dict[str, Any]:
        """Get a user profile."""
        user = self._users.get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return {
            "user_id": user.user_id,
            "preferences": user.preferences,
            "viewed_items": user.viewed_items[:10],
            "purchased_items": user.purchased_items[:10],
        }

    def get_report(self) -> dict[str, Any]:
        """Get engine report."""
        return {
            "total_users": len(self._users),
            "total_products": len(self._products),
            "total_recommendations": len(self._recommendations),
            "engine_status": "operational",
        }


engine = RecommendationPersonalizer()


@router.post("/cortex/recommendations/users")
async def add_user(user_id: str, preferences: dict[str, float] | None = None):
    """Add a user profile."""
    user = engine.add_user(user_id, preferences)
    return {"user_id": user.user_id, "status": "added"}


@router.post("/cortex/recommendations/products")
async def add_product(product_id: str, name: str, category: str, tags: list[str] | None = None, price: float = 0.0):
    """Add a product."""
    product = engine.add_product(product_id, name, category, tags, price)
    return {"product_id": product.product_id, "status": "added"}


@router.post("/cortex/recommendations/views")
async def record_view(user_id: str, product_id: str):
    """Record a product view."""
    engine.record_view(user_id, product_id)
    return {"status": "recorded"}


@router.get("/cortex/recommendations/{user_id}")
async def generate_recommendations(user_id: str, top_n: int = 5):
    """Generate personalized recommendations."""
    recs = engine.generate_recommendations(user_id, top_n)
    return {
        "user_id": user_id,
        "recommendations": [
            {"product_id": r.product_id, "product_name": r.product_name, "score": r.score, "reason": r.reason}
            for r in recs
        ],
    }


@router.get("/cortex/recommendations/report")
async def recommendation_report():
    """Get recommendation report."""
    return engine.get_report()
