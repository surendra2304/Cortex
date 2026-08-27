# NEXUS Agent Architecture & Registry

## 1. Overview
The defining principle of NEXUS specialist agents is the **closed operational loop**:
`Observe -> Understand -> Decide -> Act -> Measure -> Learn`.

Agents are **input-driven cognitive engines** that reason over real telemetry events, visitor profile traits, historical lead scores, and system metrics. They never return hardcoded canned responses.

---

## 2. Agent Input & Output Contracts

### `AgentInput` Model
```python
class AgentInput(BaseModel):
    goal: str                     # Primary objective (e.g. "Optimize conversion")
    context: Dict[str, Any]       # Visitor traits, session summary, metrics
    events: List[Dict[str, Any]]  # Recent telemetry event stream
    identity_scope: Dict[str, Any]# Visitor/User identifiers
    allowed_capabilities: List[str]
    policy_constraints: List[str] # Hard safety boundaries
    budget: Dict[str, Any]        # Execution step and token limits
```

### `AgentOutput` Model
```python
class AgentOutput(BaseModel):
    agent_id: str
    decision: str                 # Deterministic decision verdict
    reasoning_summary: str        # Mathematical explanation citing exact metrics
    confidence: float             # Calculated score between 0.0 and 1.0
    evidence_refs: List[str]      # Verified input parameters (e.g. "pricing_views=3")
    proposed_actions: List[ProposedAction] # Actions proposed for ToolBus
    required_approvals: List[str] # Policy gates requiring human review
```

---

## 3. Specialist Agent Families

| Agent Class | Domain | Decision Capabilities & Input-Driven Logic |
| :--- | :--- | :--- |
| **`GrowthAgent`** | Growth & Funnels | Computes weighted intent score based on pricing views (35%), demo requests (40%), and enterprise views (10%). Proposes banner injections. |
| **`SalesAgent`** | Sales & Pipeline | Evaluates firmographic domains (30%), behavior (40%), recency (20%), and source (10%) to route enterprise vs mid-market leads. |
| **`SupportAgent`** | Support & Triage | Scans event stream for error spikes, checkout failures, and rage clicks. Proposes session inspection and priority email outreach. |
| **`ReliabilityAgent`** | Site Reliability | Monitors P99 latency and error rates against configured operational thresholds, escalating P0/P1 incidents. |
| **`QualificationAgent`** | Lead Qualification | Calculates 4-factor explainable qualification score, deciding `QUALIFIED_LEAD` vs `UNQUALIFIED_LEAD`. |
| **`ChurnRiskAgent`** | Customer Retention | Analyzes 30-day session decline velocity, recent support ticket volume, and negative cancellation signals to classify risk (`HIGH`, `MEDIUM`, `LOW`). |

---

## 4. Agent Registry & Event Routing
The [`AgentRegistry`](file:///d:/Nexus/packages/agents/src/nexus_agents/__init__.py) inspects incoming event types and dispatches them to the appropriate specialist agent:
- `pricing`, `banner`, `funnel` -> `GrowthAgent`
- `checkout`, `lead`, `sale` -> `SalesAgent`
- `error`, `support`, `ticket` -> `SupportAgent`
- `latency`, `metric`, `heartbeat` -> `ReliabilityAgent`
- `qualify`, `score` -> `QualificationAgent`
- `churn`, `engage` -> `ChurnRiskAgent`
