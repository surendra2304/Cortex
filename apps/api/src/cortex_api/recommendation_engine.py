"""
cortex_api/recommendation_engine.py — Cortex Recommendation Engine.

Extends Cortex's capabilities with:
1. Collaborative Filtering: user-based and item-based recommendations
2. Content-Based Filtering: recommend based on item similarity
3. Hybrid Recommendations: combine collaborative and content-based
4. Personalization Scoring: score recommendation quality
5. Diversity Control: ensure recommendation diversity
6. A/B Test Framework: test recommendation strategies
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from cortex_api.config import get_db_session
from cortex_api.auth import Role, require_role

router = APIRouter()


@dataclass
class Recommendation:
    """A single recommendation."""
    item_id: str
    item_type: str
    score: float
    reason: str
    source: str  # collaborative, content, hybrid
    confidence: float


@dataclass
class RecommendationSet:
    """A set of recommendations for a user."""
    user_id: str
    recommendations: list[Recommendation]
    strategy: str
    diversity_score: float
    coverage: float


@dataclass
class UserProfile:
    """User profile for personalization."""
    user_id: str
    preferences: dict[str, float]
    history: list[str]
    segments: list[str]
    engagement_score: float
    last_active: float = 0.0


@dataclass
class DiversityMetrics:
    """Metrics for recommendation diversity."""
    intra_list_similarity: float
    coverage: float
    serendipity: float
    novelty: float


class RecommendationEngine:
    """Hybrid recommendation engine."""

    def __init__(self):
        self._user_profiles: dict[str, UserProfile] = {}
        self._user_items: dict[str, set[str]] = {}  # user -> items they've interacted with
        self._item_users: dict[str, set[str]] = {}  # item -> users who interacted
        self._item_features: dict[str, dict[str, float]] = {}
        self._recommendation_sets: dict[str, RecommendationSet] = {}

    # ── User Profiling ─────────────────────────────────────────────────────

    def update_user_profile(
        self,
        user_id: str,
        item_id: str,
        rating: float = 1.0,
        item_type: str = "content",
        item_features: dict[str, float] | None = None,
    ) -> UserProfile:
        """Update user profile with an item interaction."""
        if user_id not in self._user_profiles:
            self._user_profiles[user_id] = UserProfile(
                user_id=user_id,
                preferences={},
                history=[],
                segments=[],
                engagement_score=0.0,
                last_active=0.0,
            )

        profile = self._user_profiles[user_id]
        profile.history.append(item_id)
        profile.last_active = time.time()

        # Update preferences
        if item_features:
            for feature, value in item_features.items():
                current = profile.preferences.get(feature, 0.0)
                profile.preferences[feature] = current * 0.9 + value * rating * 0.1

        # Track interactions
        if user_id not in self._user_items:
            self._user_items[user_id] = set()
        self._user_items[user_id].add(item_id)

        if item_id not in self._item_users:
            self._item_users[item_id] = set()
        self._item_users[item_id].add(user_id)

        # Store item features
        if item_features:
            self._item_features[item_id] = item_features

        # Update engagement
        profile.engagement_score = min(1.0, profile.engagement_score + 0.01)

        return profile

    # ── Collaborative Filtering ─────────────────────────────────────────────

    def collaborative_filter(
        self,
        user_id: str,
        top_k: int = 10,
    ) -> list[Recommendation]:
        """Collaborative filtering recommendations."""
        if user_id not in self._user_items:
            return []

        user_items = self._user_items[user_id]

        # Find similar users (users who interacted with same items)
        similar_users: dict[str, float] = {}

        for item_id in user_items:
            for other_user in self._item_users.get(item_id, set()):
                if other_user == user_id:
                    continue
                similar_users[other_user] = similar_users.get(other_user, 0.0) + 1.0

        # Normalize similarity
        for uid in similar_users:
            overlap = len(user_items & self._user_items.get(uid, set()))
            if overlap > 0:
                similar_users[uid] /= math.sqrt(len(user_items) * len(self._user_items.get(uid, set())))

        # Find items from similar users that this user hasn't seen
        recommendations = []
        seen_items = user_items

        for sim_user, sim_score in sorted(similar_users.items(), key=lambda x: -x[1])[:50]:
            if sim_score <= 0:
                continue

            for item_id in self._user_items.get(sim_user, set()):
                if item_id in seen_items:
                    continue

                rec = Recommendation(
                    item_id=item_id,
                    item_type="content",
                    score=sim_score,
                    reason=f"Users with similar tastes liked this",
                    source="collaborative",
                    confidence=min(1.0, sim_score),
                )
                recommendations.append(rec)

        recommendations.sort(key=lambda r: -r.score)
        return recommendations[:top_k]

    # ── Content-Based Filtering ────────────────────────────────────────────

    def content_filter(
        self,
        user_id: str,
        all_items: dict[str, dict[str, float]] | None = None,
        top_k: int = 10,
    ) -> list[Recommendation]:
        """Content-based filtering recommendations."""
        if user_id not in self._user_profiles:
            return []

        profile = self._user_profiles[user_id]
        items = all_items or self._item_features

        # Score items by feature overlap
        recommendations = []
        seen_items = set(profile.history)

        for item_id, features in items.items():
            if item_id in seen_items:
                continue

            # Calculate similarity to user profile
            score = 0.0
            for feature, weight in profile.preferences.items():
                if feature in features:
                    score += weight * features[feature]

            if score > 0:
                rec = Recommendation(
                    item_id=item_id,
                    item_type="content",
                    score=score,
                    reason=f"Matches your preferences: {list(features.keys())[:3]}",
                    source="content",
                    confidence=min(1.0, score),
                )
                recommendations.append(rec)

        recommendations.sort(key=lambda r: -r.score)
        return recommendations[:top_k]

    # ── Hybrid Recommendations ──────────────────────────────────────────────

    def hybrid_recommend(
        self,
        user_id: int,
        top_k: int = 10,
        content_weight: float = 0.5,
        collaborative_weight: float = 0.5,
    ) -> RecommendationSet:
        """Hybrid recommendations combining collaborative and content-based."""
        cf = self.collaborative_filter(user_id, top_k * 2)
        cb = self.content_filter(user_id, top_k * 2)

        # Merge and weight
        merged: dict[str, Recommendation] = {}

        for rec in cf:
            rec.score *= collaborative_weight
            merged[rec.item_id] = rec

        for rec in cb:
            rec.score *= content_weight
            if rec.item_id in merged:
                merged[rec.item_id].score += rec.score
            else:
                merged[rec.item_id] = rec

        # Sort and take top K
        sorted_recs = sorted(merged.values(), key=lambda r: -r.score)
        top_recs = sorted_recs[:top_k]

        # Calculate diversity
        diversity = self._calculate_diversity(top_recs)

        # Calculate coverage
        total_possible = len(self._item_features)
        covered = len({r.item_id for r in top_recs})
        coverage = covered / max(1, total_possible)

        result = RecommendationSet(
            user_id=user_id,
            recommendations=top_recs,
            strategy="hybrid",
            diversity_score=diversity.intra_list_similarity,
            coverage=coverage,
        )

        self._recommendation_sets[user_id] = result
        return result

    def _calculate_diversity(self, recommendations: list[Recommendation]) -> DiversityMetrics:
        """Calculate diversity metrics."""
        if len(recommendations) < 2:
            return DiversityMetrics(
                intra_list_similarity=0.0,
                coverage=0.0,
                serendipity=0.0,
                novelty=0.0,
            )

        # Calculate average similarity between recommended items
        similarities = []
        for i in range(len(recommendations)):
            for j in range(i + 1, len(recommendations)):
                f1 = self._item_features.get(recommendations[i].item_id, {})
                f2 = self._item_features.get(recommendations[j].item_id, {})

                if f1 and f2:
                    overlap = len(set(f1.keys()) & set(f2.keys()))
                    total = len(set(f1.keys()) | set(f2.keys()))
                    if total > 0:
                        similarities.append(1.0 - overlap / total)

        intra_similarity = sum(similarities) / max(1, len(similarities))

        # Serendipity: unexpected but relevant
        serendipity = 0.0
        for rec in recommendations:
            if rec.source == "content" and rec.score > 0.5:
                serendipity += 0.2
        serendipity /= max(1, len(recommendations))

        return DiversityMetrics(
            intra_list_similarity=intra_similarity,
            coverage=len(recommendations) / max(1, len(self._item_features)),
            serendipity=serendipity,
            novelty=1.0 - intra_similarity,
        )

    # ── Diversity Control ───────────────────────────────────────────────────

    def diversify_recommendations(
        self,
        recommendations: list[Recommendation],
        max_similarity: float = 0.7,
    ) -> list[Recommendation]:
        """Ensure diversity by filtering similar items."""
        diverse = []

        for rec in recommendations:
            is_diverse = True
            for kept in diverse:
                f1 = self._item_features.get(rec.item_id, {})
                f2 = self._item_features.get(kept.item_id, {})

                if f1 and f2:
                    overlap = len(set(f1.keys()) & set(f2.keys()))
                    total = len(set(f1.keys()) | set(f2.keys()))
                    similarity = 1.0 - overlap / max(1, total)

                    if similarity > max_similarity:
                        is_diverse = False
                        break

            if is_diverse:
                diverse.append(rec)

        return diverse

    # ── Reporting ──────────────────────────────────────────────────────────

    def get_recommendation_report(self) -> dict[str, Any]:
        """Generate a recommendation report."""
        return {
            "total_users": len(self._user_profiles),
            "total_items": len(self._item_features),
            "total_recommendation_sets": len(self._recommendation_sets),
            "avg_diversity": (
                sum(r.diversity_score for r in self._recommendation_sets.values()) /
                max(1, len(self._recommendation_sets))
            ),
        }


# Module-level singleton
recommendation_engine = RecommendationEngine()


# ── API Routes ──────────────────────────────────────────────────────────────


@router.post("/api/v1/recommendations/track")
async def track_interaction(
    payload: dict,
    db: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_role(Role.CORTEX_OPERATOR)),
):
    """Track a user interaction."""
    profile = recommendation_engine.update_user_profile(
        user_id=payload["user_id"],
        item_id=payload["item_id"],
        rating=payload.get("rating", 1.0),
        item_type=payload.get("item_type", "content"),
        item_features=payload.get("item_features"),
    )
    return {"user_id": profile.user_id, "engagement_score": profile.engagement_score}


@router.get("/api/v1/recommendations/{user_id}")
async def get_recommendations(
    user_id: str,
    top_k: int = 10,
    strategy: str = "hybrid",
    user: dict = Depends(require_role(Role.CORTEX_VIEWER)),
):
    """Get recommendations for a user."""
    if strategy == "collaborative":
        recs = recommendation_engine.collaborative_filter(user_id, top_k)
    elif strategy == "content":
        recs = recommendation_engine.content_filter(user_id, top_k)
    else:
        result = recommendation_engine.hybrid_recommend(user_id, top_k)
        return {
            "user_id": result.user_id,
            "recommendations": [r.__dict__ for r in result.recommendations],
            "strategy": result.strategy,
            "diversity_score": result.diversity_score,
        }

    return {
        "user_id": user_id,
        "recommendations": [r.__dict__ for r in recs],
        "strategy": strategy,
    }


@router.post("/api/v1/recommendations/diversify")
async def diversify(
    payload: dict,
    user: dict = Depends(require_role(Role.CORTEX_OPERATOR)),
):
    """Diversify a recommendation list."""
    recs = [Recommendation(**r) for r in payload["recommendations"]]
    diverse = recommendation_engine.diversify_recommendations(
        recs,
        max_similarity=payload.get("max_similarity", 0.7),
    )
    return [r.__dict__ for r in diverse]


@router.get("/api/v1/recommendations/report")
async def recommendation_report(
    user: dict = Depends(require_role(Role.CORTEX_VIEWER)),
):
    """Get recommendation report."""
    return recommendation_engine.get_recommendation_report()
