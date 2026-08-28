import logging
import uuid
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from nexus_integrations.intelx_client import IntelXClient, MarketSignal

logger = logging.getLogger("nexus-market-signals")


class MarketSignalDetector:
    """
    Market Signal & Regulatory Trend Detector:
    - Ingests real-time market signals from IntelX
    - Detects industry shifts and generates strategic adaptation events
    - Recommends personalized trending topic injection for high-intent visitors
    """

    def __init__(self, intelx_client: Optional[IntelXClient] = None):
        self.intelx_client = intelx_client or IntelXClient()
        self.active_signals: List[MarketSignal] = []

    async def detect_market_signals(self, industry: str = "saas_devops") -> List[MarketSignal]:
        signals = await self.intelx_client.fetch_market_signals(industry)
        self.active_signals = signals
        return signals

    def get_trending_content_recommendations(self, visitor_interests: List[str]) -> List[str]:
        """Matches visitor interests to trending market topics from IntelX research."""
        recommendations = []
        for signal in self.active_signals:
            for topic in signal.trending_topics:
                if any(interest.lower() in topic.lower() for interest in visitor_interests):
                    recommendations.append(topic)

        if not recommendations and self.active_signals:
            # Fallback to top market trend
            recommendations.extend(self.active_signals[0].trending_topics[:2])

        return list(set(recommendations))

    def evaluate_positioning_shift(self, signal_id: str) -> Optional[Dict[str, Any]]:
        signal = next((s for s in self.active_signals if s.signal_id == signal_id), None)
        if not signal:
            return None

        return {
            "signal_id": signal.signal_id,
            "trend_title": signal.trend_title,
            "impact_level": signal.impact_level,
            "recommended_positioning": signal.recommended_positioning,
            "trending_topics": signal.trending_topics,
            "citations": signal.citations
        }
