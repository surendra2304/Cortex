# The Agent's Brain — multi-agent collaboration, self-healing, self-model

Date: 2026-10-06 · Branch: `arena/01a10cc3-cortex` · Base: `1c79655` + the phases 0–5 work

This document records what was built after the Phase 5 handoff, what was actually executed to
prove it, and what is still unproven. Nothing here is claimed from code reading alone.

---

## 1. What was added

### 1.1 Agents helping each other — `packages/agents/src/cortex_agents/collaboration.py` (new)

| Concept | Behaviour | Guardrail |
| :--- | :--- | :--- |
| `HandoffRequest` | Any specialist can ask a peer for judgement, with a reason and priority | A handoff carries **no** capability and **no** execution authority |
| Bounded session | Breadth-first, one visit per agent, `max_rounds` (1–5) and `max_agents` caps | Cycles refused (`already participated`), unknown targets refused, wall-clock timeout |
| Shared board | Every later participant receives `peer_findings` (decision, confidence, reasoning, evidence) | Evidence, not vibes: the board carries what peers actually produced |
| Consensus | Confidence-weighted `Consensus` with `agreement`, `agreeing`, `dissenting`, `unresolved_disagreements` | Dissent is recorded, never averaged into a fake unanimity |
| Failure tolerance | One exploding agent becomes an `AGENT_ERROR` step | The session and the lead agent's decision still stand |

Integrated into the real loop as phase **`4a.Collaborate`** (`packages/core/src/cortex_core/orchestrator.py`):
after the lead agent produces its decision, only the handoffs it actually requested are
executed; peer evidence is appended to the lead agent's evidence trail; participants,
consensus and dissent are written into the trace. The session is seeded with the lead's
already-computed output so the lead agent is not run twice.

Gated by the runtime knob `max_collaboration_rounds` — the same knob the self-model can change.
A peer failure is logged and never takes down the cognitive loop.

### 1.2 Self-healing — `packages/core/src/cortex_core/resilience.py` (new)

* `SubsystemCircuit`: `CLOSED → OPEN → HALF_OPEN → CLOSED`, opening on **3 consecutive
  failures** or a **failure ratio ≥ 0.6 over ≥ 5 samples**, 15 s recovery window,
  `outage_for`, transition log, observation count.
* `HealthRegistry`: probe + circuit per subsystem, snapshot with `samples` per subsystem.
* `SelfHealingSupervisor`: probes **every** subsystem on **every** cycle (including healthy
  ones — a breaker only opens if there are observations), runs at most one repair per
  subsystem per 30 s cooldown, gives up after 3 attempts and **escalates** with the reason.
  A repair is only reported as repaired when a follow-up probe verifies it.
* `SelfHealingLoop`: runs cycles on a cadence, re-reading `self_healing_enabled` and
  `self_healing_interval_seconds` **every tick** (so a self-modification takes effect within
  one tick), survives exceptions, exposes `cycles`, `errors`, `skipped_while_disabled`,
  `last_checked_at`, `last_unhealthy`, `last_repairs`.

Wired subsystems (`apps/api/src/cortex_api/self_healing.py`): `database` (pool dispose),
`schema` (idempotent create), `redis` (pool reset), `agents` (re-register the 7 expected ids),
`ai_universe` (deterministic fallback — intentionally stays unhealthy without a provider),
plus circuits fed by **real traffic** for `ingestion` (event commits) and `tools` (tool bus
executions). No synthetic health claims: subsystems without observations are `unverified`.

### 1.3 Self-model / "self brain" — `packages/core/src/cortex_core/self_model.py` (new)

* `SelfModel.build()`: capabilities from registration + **observed** health + real DB counts.
  A capability with no observations reports `unverified` and contributes an explicit gap —
  the model refuses to claim capability it has not seen.
* `SelfModel.diagnose()`: `healthy` / `attention_required` with per-finding severity.
* `SelfModificationEngine`: allow-list of `self_healing_enabled`,
  `self_healing_interval_seconds` (1–3600), `max_collaboration_rounds` (1–5). Refuses
  everything else with a reason (not on allow-list / expected int / out of range / already at
  value), applies through the process-wide `RuntimeKnobs` singleton, detects re-applying an
  already-applied change-set with **409**, and supports **rollback** back through the history.
  It never touches environment variables or files, so a change cannot outlive the process
  unnoticed.

### 1.4 API surface (all `X-Friday-Api-Key` protected, all audited)

| Endpoint | Purpose |
| :--- | :--- |
| `POST /v1/friday/collaborate` | Run a bounded session on demand |
| `GET /v1/friday/self_healing` | Circuits, outages, escalations, **background loop state** |
| `POST /v1/friday/self_healing/run` | Force one healing cycle |
| `GET /v1/friday/self_model` | Honest capability report + gaps + usage |
| `GET /v1/friday/self_model/diagnose` | Findings with severity |
| `POST /v1/friday/self_model/modify` | Propose/apply/rollback allow-listed knobs |

Request models use `extra="forbid"`: a misspelled field (`agent_id` instead of
`root_agent_id`) is a loud 422, never a silent run against a different agent.

---

## 2. What was executed to prove it

### 2.1 Test suite and linters

```
$ .venv/bin/python -m pytest tests -q
307 passed, 1 warning in 23.03s
$ black --line-length 120 / ruff check  → clean on every touched file
```

New tests: `tests/unit/test_multi_agent_collaboration.py` (7), 
`tests/unit/test_self_healing_and_self_model.py` (17), 
`tests/unit/test_orchestrator_collaboration.py` (4), plus agent-level regressions in
`tests/unit/test_intelligent_agents.py`.

### 2.2 Real outage drill — `scripts/self_healing_live_test.py`

```
── 1. baseline: Redis up, probe observes a healthy sample ──   redis CLOSED, samples 9
── 2. induce a REAL outage: stop the Redis process ──           redis OPEN, samples 13
── 3. self-healing cycle during the outage ──
   unhealthy: ['redis', 'ai_universe']
   redis: 'repair throttled by cooldown'      (bounded, no fake fix)
   ai_universe: '3 repair attempts did not restore health' → escalated
── 4. self-model while degraded ──  realtime_streaming: degraded ['circuit OPEN for redis']
── 5. restore Redis ──              repaired=['redis'], samples 15 (evidence kept)
── 6. self-model after recovery ──  realtime_streaming: operational
API liveness during/after the outage: healthy
```

### 2.3 Full integrity sweep — `scripts/self_integrity_live_test.py` (52/52, re-runnable)

Highlights, verbatim from the last run:

```
[PASS] ingestion circuit gained real samples — samples 2 -> 3        (traffic, not synthetic probes)
[PASS] malformed event is 4xx, not 500 — status=422
[PASS] more than one agent participated — ['agent_growth', 'agent_sales']
[PASS] a handoff happened and none was refused — executed=1 refused=[]
[PASS] consensus names an agreement score in [0,1] — agreement=0.5937
[PASS] dissent is recorded rather than averaged away — dissent=['agent_sales']
[PASS] misspelled agent field is 422 (no silent default agent)
[PASS] unknown root agent is 404
[PASS] no capability claims operational without observations — []
[PASS] re-introducing an already-applied change-set is 409
[PASS] rollback-only request works (no proposals needed) — status=200
[PASS] second rollback walks back to the default 30 — value=30
[PASS] the loop asked peers for help when the lead agent requested it — ['agent_growth','agent_sales']
[PASS] peer evidence is recorded in the loop trace — ['peer:agent_sales:NURTURE_LEAD']
[PASS] interval change accepted — 200
[PASS] loop healed at the new cadence without a restart — cycles 3 -> 5 at interval=5s
[PASS] disabled loop stops healing — skipped_while_disabled=1
52/52 checks passed
```

### 2.4 End-to-end: a FRIDAY command drives the loop until peers join

Staged session history (4× `pricing_page_view`, 3× `demo_request`, 2× `enterprise_plan_view`)
→ `POST /v1/friday/command` → real trace:

```
2.Contextualize  intent_level=HIGH_INTENT intent_score=1.0
                 session_summary={events_count:10, pricing_views:5, demo_views:3}
3.Understand     selected_agent=agent_growth
4a.Collaborate   participants=['agent_growth','agent_sales'] consensus=OPTIMIZE_FUNNEL
                 agreement=0.6552 dissent=['agent_sales'] peer_evidence=['peer:agent_sales:NURTURE_LEAD']
4.Plan           decision=OPTIMIZE_FUNNEL confidence=0.95
5.Authorize      tool=banner_injection approved=false requires_human=true
6.Execute        status=no_auto_approved_actions_executed count=0
7.Verify … 10.Continue  cycle_complete
```

Two things matter here: the peer's judgement is in the evidence trail, and collaboration
**did not** grant itself execution authority — the high-impact action still needed an operator.

### 2.5 Pressure regression — `scripts/pressure_test.py` (9/9, exit 0)

```
concurrency=200 events=5000 soak=60s
baseline-latency PASS · idempotency-race PASS (accepted=1, duplicate=199)
tenant-isolation PASS (403×200) · unauthenticated-flood PASS (401×300)
rate-limit PASS (429=120, 5xx=0) · hostile-input PASS (18 adversarial, 0 5xx)
throughput PASS 5000 events @101 req/s p50=1298ms p95=5518ms p99=6774ms, 5xx=0, dropped=0
sustained-soak PASS · consistency PASS accepted=2000 readable=2000 missing=0
scenarios: 9  failed: 0  skipped: 0
```

---

## 3. Defects found by this live work (and fixed)

| # | Defect | Found by | Fix |
| :-- | :--- | :--- | :--- |
| 1 | `SelfHealingSupervisor.run_cycle` only probed OPEN circuits → breakers could never open | live outage drill | probe every subsystem every cycle |
| 2 | `SelfModel` read a default-CLOSED breaker as healthy → "operational" with zero observations | live `/self_model` call | require `samples > 0`, else `unverified` + gap |
| 3 | `SubsystemCircuit.reset()` wiped the observation history → a *recovered* subsystem reported `unverified` | live drill step 5/6 | keep evidence; a verified repair records a success sample |
| 4 | Rollback-only `/self_model/modify` requests were 422 (`proposals` required) | live integrity sweep | `proposals` optional |
| 5 | Misspelled request fields silently fell back to the default agent | live sweep (`agent_id`) | `extra="forbid"` → 422 |
| 6 | A second consecutive rollback raised `KeyError` (history scan used `entry["applied"]`) | live sweep | `entry.get("applied")` + regression test |
| 7 | Growth/Sales agents looked for `*_view_count` while `ContextBuilder` publishes `pricing_views`/`demo_views` → pre-aggregated intent was silently discarded | tracing the e2e command | accept both names + regression test |

---

## 4. REAL vs CONFIGURED-BUT-UNVERIFIED (this layer)

**REAL (executed here, evidence above):** circuit breaker transitions, real-outage detection,
bounded repair + escalation, repair verification, background loop cadence and on/off,
multi-agent handoff with peer findings and consensus/dissent, orchestrator phase `4a`,
allow-list refusals, 409 conflict, rollback chains, self-model honesty (`unverified` +
gaps), traffic-fed `ingestion` observations, human approval still required for high-impact
actions, 5000-event pressure run.

**CONFIGURED-BUT-UNVERIFIED (needs the real world):**
* `ai_universe` deliberation as a *healthy* subsystem — no provider credentials here, so it is
  correctly reported `degraded`/escalated rather than healed.
* `postgres` persistence, a production Redis, real connectors (SendGrid/Twilio/HubSpot/…),
  multi-worker deployment (the background loop would run per worker — a leader election /
  distributed lock is not implemented).
* Long-horizon learning: strategy promotion/demotion after 48 h of real outcomes.
* `tools` circuit under real tool failures (only exercised through deterministic fallbacks).

---

## 5. Next five

1. **Leader election for the healing loop** so multi-worker deployments run it once, and a
   distributed view of circuits (Redis-backed) instead of per-process state.
2. **Peer-to-peer verification of agent claims**: a peer that can *challenge* another's
   evidence (not just add its own), with a quorum rule for high-impact actions.
3. **Self-model trend memory**: persist capability snapshots so "are we getting better?" is
   answered from history, not from the current process's memory.
4. **Escalation delivery**: escalations currently live in the API snapshot; push them to
   FRIDAY/operator channels (webhook, Slack) with deduplication.
5. **Failure injection in CI**: run the outage drill and the integrity sweep against a
   throwaway compose stack on every merge, so these guarantees cannot silently rot.
