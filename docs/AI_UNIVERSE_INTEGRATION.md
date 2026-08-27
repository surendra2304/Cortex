# NEXUS AI Universe Integration & Deliberation Engine

## 1. Overview
NEXUS consumes **AI Universe** as its foundational intelligence and multi-agent deliberation layer. However, per specification section 17, **not every event is routed to AI Universe**. NEXUS follows a **deterministic-first** philosophy, calling AI deliberation only when the expected value is high.

---

## 2. Intelligence Request Routing Table

| Classification | Event Examples | AI Deliberation | Mode Used | Latency Budget |
| :--- | :--- | :--- | :--- | :--- |
| **`TRIVIAL`** | `page_view`, `session.start`, `click`, `heartbeat` | **None** (Deterministic only) | None | < 10ms |
| **`ROUTINE`** | `email.opened`, `lead.score_refresh`, `digest` | Optional AI copy optimization | `FAST` | ~3,000ms |
| **`AMBIGUOUS`**| `lead.qualify`, `error.spike`, `pricing.viewed` | AI Universe Recommended | `REVIEW` | ~8,000ms |
| **`STRATEGIC`**| `high_intent.detected`, `conversion.drop`, `incident.p0` | AI Universe Required | `DEBATE` | ~20,000ms |

---

## 3. Deliberation Modes
- **`FAST`**: Single specialist agent with direct prompt evaluation for high-velocity routine tasks.
- **`REVIEW`**: Specialist Agent + Critic pass. The critic evaluates agent reasoning, checks policy boundaries, and suggests refinements.
- **`DEBATE`**: Multi-round adversarial deliberation. Competing agents form hypotheses, present evidence bundles, and debate root causes until consensus or documented dissent is achieved.

---

## 4. Resilience & Deterministic Fallbacks
If the AI Universe layer experiences network timeouts, HTTP 5xx responses, or rate limits:
1. Exponential backoff retry is attempted (1s, 2s, 4s).
2. If all retries fail, `AIUniverseClient` activates its **Deterministic Fallback Engine**.
3. Fallback responses mark `fallback_applied=True` and route high-impact actions to the **Human-in-the-Loop Approval Queue**.
4. The system logs the fallback event to Prometheus (`ai_universe_fallback_total`).
