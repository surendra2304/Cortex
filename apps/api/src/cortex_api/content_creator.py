"""
Cortex/apps/api/src/cortex_api/content_creator.py — Cortex AI Content Creator.

Extends Cortex's capabilities with:
1. AI-Powered Content Generation: generate marketing content
2. Multi-Format Content Creation: create content for different platforms
3. Content Performance Prediction: predict content engagement
4. Brand Voice Adaptation: adapt content to brand voice
5. Content Variation Generation: generate A/B test variations
6. SEO Content Optimization: optimize content for search engines
7. Content Repurposing: repurpose content across platforms
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter()


@dataclass
class ContentPiece:
    """A content piece."""
    content_id: str
    title: str
    body: str
    format: str  # blog, tweet, video, image, podcast, email
    platform: str  # twitter, instagram, youtube, blog, email
    tags: list[str] = field(default_factory=list)
    word_count: int = 0
    seo_score: float = 0.0
    predicted_engagement: float = 0.0
    predicted_shares: int = 0
    predicted_conversions: int = 0
    brand_voice_score: float = 0.5
    created_at: float = 0.0
    variations: list[str] = field(default_factory=list)


@dataclass
class BrandVoice:
    """Brand voice profile."""
    tone: str = "professional"  # professional, casual, witty, authoritative
    style: str = "informative"  # informative, persuasive, entertaining
    formality: float = 0.5  # 0 = casual, 1 = formal
    enthusiasm: float = 0.5  # 0 = subdued, 1 = enthusiastic
    keywords: list[str] = field(default_factory=list)
    banned_words: list[str] = field(default_factory=list)
    avg_sentence_length: float = 20.0
    personality_traits: list[str] = field(default_factory=list)


@dataclass
class SEOAnalysis:
    """SEO analysis result."""
    content_id: str
    score: float
    issues: list[str]
    recommendations: list[str]
    keywords: list[str]
    density: dict[str, float]
    readability_score: float
    suggested_meta_title: str
    suggested_meta_description: str


@dataclass
class Variation:
    """Content variation."""
    variation_id: str
    content_id: str
    headline: str
    body: str
    change_type: str  # headline, body, tone, length, call_to_action
    predicted_improvement: float = 0.0
    is_recommended: bool = False


@dataclass
class RepurposeResult:
    """Content repurposing result."""
    original_content_id: str
    repurposed: list[str]
    new_contents: list[dict]
    total_reach_potential: int
    estimated_effort: float


@dataclass
class EngagementPrediction:
    """Engagement prediction for content."""
    content_id: str
    views: int
    shares: int
    likes: int
    comments: int
    conversions: int
    engagement_rate: float
    viral_potential: float
    best_post_time: str


class ContentCreator:
    """AI content creation engine."""

    def __init__(self):
        self._content: dict[str, ContentPiece] = {}
        self._brand_voice = BrandVoice()
        self._variations: dict[str, list[Variation]] = {}
        self._seo_analyses: dict[str, SEOAnalysis] = {}
        self._predictions: dict[str, EngagementPrediction] = {}

    def set_brand_voice(self, voice: dict) -> BrandVoice:
        """Set brand voice profile."""
        for key, value in voice.items():
            if hasattr(self._brand_voice, key):
                setattr(self._brand_voice, key, value)
        return self._brand_voice

    def get_brand_voice(self) -> BrandVoice:
        return self._brand_voice

    # ── Content Generation ──────────────────────────────────────────────────

    def generate_content(
        self,
        topic: str,
        format: str,
        platform: str,
        audience: str = "",
        goal: str = "engagement",
    ) -> ContentPiece:
        """Generate content."""
        # Generate title based on topic and platform
        title = self._generate_title(topic, platform)

        # Generate body content
        body = self._generate_body(topic, platform, audience, goal)

        # Calculate metrics
        word_count = len(body.split())
        seo_score = self._calculate_seo_score(body, topic)
        engagement = self._predict_engagement(body, platform, goal)
        brand_score = self._evaluate_brand_voice(body)

        content_id = hashlib.md5(
            f"content:{topic}:{format}:{time.time()}".encode()
        ).hexdigest()[:12]

        piece = ContentPiece(
            content_id=content_id,
            title=title,
            body=body,
            format=format,
            platform=platform,
            tags=self._extract_tags(body),
            word_count=word_count,
            seo_score=seo_score,
            predicted_engagement=engagement["engagement_rate"],
            predicted_shares=engagement["shares"],
            predicted_conversions=engagement["conversions"],
            brand_voice_score=brand_score,
            created_at=time.time(),
        )

        self._content[content_id] = piece
        return piece

    def _generate_title(self, topic: str, platform: str) -> str:
        """Generate title."""
        title_formats = {
            "twitter": f"🎯 {topic}: What You Need to Know",
            "instagram": f"✨ {topic}: A Visual Guide",
            "youtube": f"{topic}: The Ultimate Guide (2024)",
            "blog": f"The Complete Guide to {topic}",
            "email": f"Exploring {topic}: Key Insights",
            "linkedin": f"Deep Dive: {topic}",
        }
        return title_formats.get(platform, f"{topic}: A Comprehensive Guide")

    def _generate_body(self, topic: str, platform: str, audience: str, goal: str) -> str:
        """Generate body content."""
        intro = f"{topic} is a topic that deserves attention. "

        if audience:
            intro = f"For {audience}, {topic} is particularly important. "

        body_templates = {
            "twitter": (
                intro +
                "Here are the key points:\n" +
                f"1. {topic} offers unique benefits\n" +
                f"2. Implementation requires careful planning\n" +
                f"3. Results can be significant\n" +
                "What are your thoughts? #" + topic.replace(" ", "")
            ),
            "instagram": (
                intro +
                f"Key points about {topic}:\n\n" +
                f"📌 Point 1: {topic} fundamentals\n" +
                f"📌 Point 2: Best practices\n" +
                f"📌 Point 3: Common mistakes\n\n" +
                "Save this for later! ✨ #" + topic.replace(" ", "")
            ),
            "youtube": (
                intro +
                f"In this video, we explore {topic} in depth.\n\n" +
                f"Chapter 1: Introduction to {topic}\n" +
                f"Chapter 2: Why {topic} matters\n" +
                f"Chapter 3: How to implement {topic}\n" +
                f"Chapter 4: Tips and best practices\n\n" +
                "Don't forget to subscribe!"
            ),
            "blog": (
                intro +
                f"## Introduction\n" +
                f"{topic} has become increasingly important in today's landscape.\n\n" +
                f"## Key Concepts\n" +
                f"Understanding {topic} requires grasping several core concepts:\n" +
                f"- Fundamental principles of {topic}\n" +
                f"- Practical applications\n" +
                f"- Benefits and challenges\n\n" +
                f"## Implementation\n" +
                f"Successfully implementing {topic} involves:\n" +
                f"1. Clear goal setting\n" +
                f"2. Resource allocation\n" +
                f"3. Continuous optimization\n\n" +
                f"## Conclusion\n" +
                f"{topic} offers significant opportunities for those who approach it strategically."
            ),
            "email": (
                intro +
                f"Hello,\n\n" +
                f"I wanted to share some insights about {topic}.\n\n" +
                f"Key takeaways:\n" +
                f"- {topic} can drive meaningful results\n" +
                f"- Implementation is straightforward\n" +
                f"- ROI can be substantial\n\n" +
                f"Best regards,\nYour Team"
            ),
            "linkedin": (
                intro +
                f"In today's professional landscape, {topic} is more relevant than ever.\n\n" +
                f"After extensive research, here's what I've found:\n" +
                f"🔍 {topic} is reshaping how we approach challenges\n" +
                f"🔍 Organizations implementing {topic} see 40%+ improvements\n" +
                f"🔍 The key is starting with a clear strategy\n\n" +
                "What's your experience with this? Let's discuss."
            ),
        }

        return body_templates.get(platform, intro + f"Explore {topic} in detail.")

    # ── Content Performance Prediction ─────────────────────────────────────

    def _predict_engagement(
        self,
        body: str,
        platform: str,
        goal: str,
    ) -> dict[str, Any]:
        """Predict content engagement."""
        word_count = len(body.split())
        has_call_to_action = any(
            w in body.lower() for w in
            ["subscribe", "follow", "share", "like", "comment", "learn more"]
        )
        has_emoji = any(char in body for char in "🔥✨💯📌✅")

        # Base engagement by platform
        base_engagement = {
            "twitter": 0.03,
            "instagram": 0.05,
            "youtube": 0.08,
            "blog": 0.10,
            "email": 0.15,
            "linkedin": 0.06,
        }

        engagement = base_engagement.get(platform, 0.05)

        # Adjustments
        if has_call_to_action:
            engagement += 0.02
        if has_emoji:
            engagement += 0.01
        if word_count > 200:
            engagement += 0.01

        # Calculate metrics
        base_views = {
            "twitter": 1000,
            "instagram": 5000,
            "youtube": 500,
            "blog": 200,
            "email": 500,
            "linkedin": 1500,
        }

        views = base_views.get(platform, 1000)
        shares = int(views * engagement * 0.1)
        likes = int(views * engagement * 2)
        comments = int(views * engagement * 0.05)
        conversions = int(views * engagement * 0.02)

        return {
            "views": views,
            "shares": shares,
            "likes": likes,
            "comments": comments,
            "conversions": conversions,
            "engagement_rate": engagement,
        }

    # ── Brand Voice Adaptation ─────────────────────────────────────────────

    def _evaluate_brand_voice(self, text: str) -> float:
        """Evaluate how well text matches brand voice."""
        score = 0.5

        # Check formality
        avg_sentence_length = len(text.split()) / max(1, text.count(".") + 1)
        if abs(avg_sentence_length - self._brand_voice.avg_sentence_length) < 5:
            score += 0.2

        # Check keywords
        text_lower = text.lower()
        keyword_matches = sum(
            1 for kw in self._brand_voice.keywords if kw.lower() in text_lower
        )
        if keyword_matches > 0:
            score += 0.15

        # Check banned words
        banned_matches = sum(
            1 for word in self._brand_voice.banned_words if word.lower() in text_lower
        )
        if banned_matches == 0:
            score += 0.15

        return min(1.0, score)

    # ── Content Variation Generation ───────────────────────────────────────

    def generate_variations(
        self,
        content_id: str,
        count: int = 3,
    ) -> list[Variation]:
        """Generate A/B test variations."""
        piece = self._content.get(content_id)
        if not piece:
            raise HTTPException(404, f"Content {content_id} not found")

        variations = []

        change_types = ["headline", "tone", "length", "call_to_action"]

        for i in range(min(count, 4)):
            change_type = change_types[i % len(change_types)]

            if change_type == "headline":
                new_headline = f"🔥 {piece.title} (Updated!)"
            elif change_type == "tone":
                new_headline = f"Let's talk about {piece.title}"
            elif change_type == "length":
                new_headline = f"{piece.title} - Short & Sweet"
            else:
                new_headline = f"{piece.title} - Don't Miss Out!"

            # Predict improvement
            improvement = self._predict_variation_improvement(change_type)

            variation = Variation(
                variation_id=hashlib.md5(
                    f"variation:{content_id}:{i}:{time.time()}".encode()
                ).hexdigest()[:12],
                content_id=content_id,
                headline=new_headline,
                body=piece.body,
                change_type=change_type,
                predicted_improvement=improvement,
                is_recommended=i == 0,
            )

            variations.append(variation)

        self._variations[content_id] = variations
        return variations

    def _predict_variation_improvement(self, change_type: str) -> float:
        """Predict improvement from variation change."""
        improvements = {
            "headline": 0.05,
            "tone": 0.08,
            "length": 0.03,
            "call_to_action": 0.10,
        }
        return improvements.get(change_type, 0.05)

    # ── SEO Content Optimization ───────────────────────────────────────────

    def analyze_seo(
        self,
        content_id: str,
        target_keywords: list[str] | None = None,
    ) -> SEOAnalysis:
        """Analyze and optimize SEO."""
        piece = self._content.get(content_id)
        if not piece:
            raise HTTPException(404, f"Content {content_id} not found")

        issues = []
        recommendations = []
        keywords = target_keywords or self._extract_tags(piece.body)
        density = {}

        # Calculate keyword density
        word_count = piece.word_count
        body_lower = piece.body.lower()

        for kw in keywords:
            count = body_lower.count(kw.lower())
            density[kw] = count / max(1, word_count)

            if density[kw] < 0.01:
                issues.append(f"Keyword '{kw}' density too low")
                recommendations.append(f"Add '{kw}' more naturally")
            elif density[kw] > 0.05:
                issues.append(f"Keyword '{kw}' overused")
                recommendations.append(f"Reduce '{kw}' usage")

        # Readability
        sentences = piece.body.split(".")
        avg_sentence_length = len(piece.body.split()) / max(1, len(sentences))
        readability = max(0, 100 - avg_sentence_length * 2)

        # SEO score
        seo_score = 50.0
        if density and all(d > 0.01 for d in density.values()):
            seo_score += 20.0
        if len(piece.title) > 30 and len(piece.title) < 60:
            seo_score += 15.0
        if readability > 60:
            seo_score += 15.0

        analysis = SEOAnalysis(
            content_id=content_id,
            score=min(100.0, seo_score),
            issues=issues,
            recommendations=recommendations,
            keywords=keywords,
            density=density,
            readability_score=readability,
            suggested_meta_title=piece.title[:60],
            suggested_meta_description=piece.body[:150],
        )

        self._seo_analyses[content_id] = analysis
        return analysis

    # ── Content Repurposing ────────────────────────────────────────────────

    def repurpose_content(
        self,
        content_id: str,
        target_platforms: list[str] | None = None,
    ) -> RepurposeResult:
        """Repurpose content across platforms."""
        piece = self._content.get(content_id)
        if not piece:
            raise HTTPException(404, f"Content {content_id} not found")

        platforms = target_platforms or ["twitter", "instagram", "youtube"]
        new_contents = []
        total_reach = 0

        for platform in platforms:
            # Skip if same as original
            if platform == piece.platform:
                continue

            # Generate adapted content
            adapted = self.generate_content(
                topic=piece.title,
                format=platform,
                platform=platform,
            )

            new_contents.append({
                "platform": platform,
                "content_id": adapted.content_id,
                "title": adapted.title,
                "predicted_engagement": adapted.predicted_engagement,
            })

            total_reach += adapted.predicted_shares + adapted.predicted_engagement * 1000

        return RepurposeResult(
            original_content_id=content_id,
            repurposed=platforms,
            new_contents=new_contents,
            total_reach_potential=total_reach,
            estimated_effort=len(platforms) * 0.5,
        )


# ── API Routes ──────────────────────────────────────────────────────────────


@router.post("/api/v1/content/generate")
async def generate_content(payload: dict):
    """Generate content."""
    piece = creator.generate_content(
        topic=payload["topic"],
        format=payload["format"],
        platform=payload["platform"],
        audience=payload.get("audience", ""),
        goal=payload.get("goal", "engagement"),
    )
    return piece.__dict__


@router.post("/api/v1/content/brand_voice")
async def set_brand_voice(payload: dict):
    """Set brand voice."""
    voice = creator.set_brand_voice(payload)
    return {k: v for k, v in voice.__dict__.items()}


@router.get("/api/v1/content/{content_id}/variations")
async def get_variations(content_id: str, count: int = 3):
    """Generate variations."""
    variations = creator.generate_variations(content_id, count)
    return [v.__dict__ for v in variations]


@router.get("/api/v1/content/{content_id}/seo")
async def analyze_seo(content_id: str, keywords: list[str] | None = None):
    """Analyze SEO."""
    analysis = creator.analyze_seo(content_id, keywords)
    return analysis.__dict__


@router.post("/api/v1/content/{content_id}/repurpose")
async def repurpose_content(content_id: str, payload: dict):
    """Repurpose content."""
    result = creator.repurpose_content(
        content_id,
        payload.get("target_platforms"),
    )
    return result.__dict__


@router.get("/api/v1/content/all")
async def list_content():
    """List all content."""
    return [c.__dict__ for c in creator._content.values()]


# Module-level singleton
creator = ContentCreator()
