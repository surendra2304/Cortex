from __future__ import annotations
from dataclasses import dataclass
# Kept as an independent adapter instead of execution authority.
@dataclass(frozen=True)
class DecisionPolicy:
    high_probability: float = .70
    medium_probability: float = .30
    minimum_confidence: float = .55

class AdvisoryEngine:
    def __init__(self, policy=None):
        self.policy = policy or DecisionPolicy()

    def build(self, forecast) -> list[dict]:
        probability = forecast.get("probability", 0.0) or 0.0
        confidence = float(forecast.get("confidence", 0.0))
        evidence = list(forecast.get("evidence_ids", []))
        if confidence < self.policy.minimum_confidence:
            return [{"action":"abstain","risk":"advisory","requires_authorization":True,
                     "reason":"confidence below policy threshold","evidence_ids":evidence}]
        if probability >= self.policy.high_probability:
            actions = ["prepare_scale_up", "prepare_incident_guardrails"]
            risk = "governed"
        elif probability >= self.policy.medium_probability:
            actions = ["warm_standby", "increase_observation"]
            risk = "advisory"
        else:
            actions = ["continue_observation"]
            risk = "observe"
        return [{"action":a,"risk":risk,"requires_authorization":risk!="observe",
                 "reason":f"probability={probability:.3f}; confidence={confidence:.3f}",
                 "evidence_ids":evidence} for a in actions]
