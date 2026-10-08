# CORTEX Agent Upgrade — Progress Checklist (2026-10-07)

Mission: make the agent work in real life; drive it like the owner; push to dead ends
and extreme pressure; find and fix every error; keep real-life tests; don't stop
until done. Branch: `arena/998f44c2-cortex` (commit + push authorized).

Detailed running log: `notes/UPGRADE_PLAN.md`. Analysis baseline: `REPO_ANALYSIS.md`.

## Checklist
- [x] B1 — Worker/Redis fix: agent processes events end-to-end (redis pin, protocol=2,
      ack-on-success + PEL recovery + NOGROUP self-heal, dev_redis XPENDING/XCLAIM)
- [x] B2 — Autonomous loop closed: identity resolution in the loop, full-history intent
      scoring, gated actions create approval requests, approve executes via tool bus,
      route-shadowing stub + fabricated workflows removed, landing page honest
- [x] B3 — Cross-tenant IDOR killed: visitors/leads tenant-scoped, orchestrator
      Contextualize tenant-scoped, friday endpoints gain explicit tenant_id scope,
      live-verified + regression tests (test_tenant_isolation_reads.py)
- [x] B4 — Operator gauntlet: 4 repo live scripts green (self_integrity 55/55,
      self_healing outage→recovery, e2e 35/35 LIVE, escalation 14/14) +
      scripts/operator_gauntlet_live_test.py driving tasks/approvals/workflows/
      GDPR/dead-ends like the owner — 46/51, 5 remaining (script contract fixes
      + API restart for the Art. 15 unredacted-export fix)
- [ ] B5 — Extreme pressure: 5000@200/60s + 20k capacity + worker throughput +
      concurrent operator load; fix every bug found
- [ ] B6 — Remaining security fixes: S5 api-keys cross-tenant minting,
      S6 dev-auth-open-by-default, S7 webhook missing-secret, S10 hardcoded
      connector health — each with tests
- [ ] B7 — Full regression (pytest + all live scripts + pressure), upgrade report
      (AGENT_UPGRADE_2026-10-07.md), commit + push

## Current step
B5: extreme pressure — 5000@200/60s + 20k capacity + worker throughput +
concurrent operator load; fix every bug found.

## Verification state
- pytest: 357 passed, 3 skipped
- gauntlet: 51/51 (tasks, approvals, workflows, GDPR, dead ends)
- pushed: arena/998f44c2-cortex (B1-B4 commit)
- live scripts: self_integrity 55/55, self_healing PASS, e2e 35/35, escalation 14/14
- stack running: dev-redis :6379, cortex-api :8000 (dev), cortex-worker
