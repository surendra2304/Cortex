import logging
from typing import Dict, Any, List, Optional

from nexus_agents import SpecialistAgent, AgentInput, AgentOutput, ProposedAction
from nexus_integrations.intelx_client import IntelXClient, CompetitorProfile

logger = logging.getLogger("nexus-competitive-agent")


class CompetitiveIntelligenceAgent(SpecialistAgent):
    """
    Competitive Intelligence Specialist Agent:
    - Triggered when:
      1. Competitor mentioned in visitor session/search queries
      2. Competitor detected in referral traffic or UTM campaign params
      3. User or FRIDAY explicitly requests competitive analysis
    - Submits deep research query to IntelXClient
    - Feeds findings into:
      - GrowthAgent: Positioning recommendations targeting competitor feature gaps
      - SalesAgent: Evidence-backed battlecards for high-value enterprise leads
      - Personalization Engine: Competitor-aware messaging variants
    """

    def __init__(self, intelx_client: Optional[IntelXClient] = None):
        super().__init__(
            agent_id="agent_competitive",
            domain="competitive",
            capabilities=["account_update", "banner_injection"]
        )
        self.intelx_client = intelx_client or IntelXClient()

    async def process(self, input_data: AgentInput) -> AgentOutput:
        events = input_data.events or []
        context = input_data.context or {}

        # 1. Identify competitor from event telemetry or context
        competitor_name = None
        for evt in events:
            evt_type = str(evt.get("type", "")).lower()
            data_str = str(evt.get("data", {})).lower()
            for candidate in ["datadog", "dynatrace", "segment", "heap", "mixpanel", "splunk"]:
                if candidate in evt_type or candidate in data_str:
                    competitor_name = candidate
                    break
            if competitor_name:
                break

        if not competitor_name:
            competitor_name = context.get("requested_competitor") or context.get("competitor_name") or "Datadog"

        # 2. Fetch competitive intelligence profile via IntelX
        profile = await self.intelx_client.fetch_competitor_intelligence(competitor_name)

        # 3. Propose battlecard & positioning actions
        proposed_actions = [
            ProposedAction(
                action_type="account_update",
                target="sales_battlecard",
                params={
                    "competitor": profile.competitor_name,
                    "battlecard": profile.battlecard_summary,
                    "feature_gaps": profile.feature_gaps,
                    "citations": profile.evidence_citations
                },
                rationale=f"Identified interest comparing against {profile.competitor_name}. Synthesized positioning battlecard.",
                side_effect_level="SENSITIVE"
            ),
            ProposedAction(
                action_type="banner_injection",
                target="comparison_banner",
                params={
                    "variant": f"vs_{competitor_name.lower()}_callout",
                    "copy": f"Switch from {profile.competitor_name} to Nexus for zero-latency autonomous operations and 60% lower TCO."
                },
                rationale=f"Surface competitor-aware comparison banner targeting {profile.competitor_name} feature gaps.",
                side_effect_level="READ"
            )
        ]

        evidence_refs = [
            f"competitor_identified={profile.competitor_name}",
            f"market_share_tier={profile.market_share_tier}",
            f"gap_count={len(profile.feature_gaps)}",
            *profile.evidence_citations
        ]

        return AgentOutput(
            agent_id=self.agent_id,
            decision="SYNTHESIZE_COMPETITIVE_BATTLECARD",
            confidence=0.92,
            reasoning_summary=f"Analyzed competitive positioning vs {profile.competitor_name}. Found {len(profile.feature_gaps)} key feature gaps. Generated sales battlecard and personalized comparison banner.",
            proposed_actions=proposed_actions,
            evidence_refs=evidence_refs
        )
