# Phase 12 — Git Archaeology

Date: 2026-10-07

## What git gives us [FACT]

- Clone is **shallow**: `git rev-parse --is-shallow-repository` → `true`. Exactly **1 commit** visible: `83e6f9a7260743166c8477ea6a602929447149c1` — "Merge pull request #1 from surendra2304/arena/01a10cc3-cortex", author Surendra <surendrabtech12321@gmail.com>, 2026-10-07 00:46:04 +0530. 482 objects, 1 pack.
- Remote: `https://github.com/surendra2304/Cortex.git` (fetch+push configured).
- Session branch: `arena/998f44c2-cortex` (branched from that merge commit). Prior agent's branch `arena/01a10cc3-cortex` was merged as PR #1 — i.e. **the entire prior audit+fix session is squashed into this single merge**; no intermediate history is available locally.
- Working tree is clean (`git status --porcelain` → empty after I restored the accidentally regenerated `apps/dashboard/out/`).

## What the repo itself says about history [FACT, from diary/ + docs]

- `CORTEX_DIARY.md` + `diary/2026-08-27 … 2026-10-06` (10 dated files): a day-by-day engineering diary — Day 1 scaffold (2026-08-27) → Day 2 spec realignment + 8-system ecosystem (128 tests) → Day 3 Render/SQLite/zero-config → Day 4 rename + CI green + SYSTEM_MANIFEST → … → 2026-09-12 governed-operations day (22-test Prompt 9 suite, 42 tests green) → later days to 2026-10-06.
- `docs/DEPLOYMENT.md` still says **128 tests** (stale vs 339 now) [FACT].
- README claims **307 tests** (stale) [FACT, from prior audit; not re-verified line-by-line this session].
- `patches/peer_fixes/` (2 files): futuris caller-telemetry + intelx naive-datetime patches — evidence of cross-repo (FRIDAY Universe) integration friction.
- Prior-agent root artifacts (`PHASE0-2_AUDIT_2026-10-05.md` @ commit 1c79655, `PHASE5_HANDOFF_2026-10-05.md`, `AGENT_BRAIN_2026-10-06.md`, `AUDIT_REPORT.md`, `SYSTEM_MANIFEST.md`) document the audit→fix arc; their defect lists describe the pre-fix state and are now historical.

## Inferences [INFERENCE]

- The project is ~6 weeks old (2026-08-27 → 2026-10-07) with an unusually dense fix/audit loop; the single merge suggests the public history was collapsed (or the repo was re-initialized) — the diary is the only faithful history.
- Renames left residue: `nexus_*` in docker-compose/k8s/terraform (project renamed Nexus→Cortex per diary Day 4); `DATABASE_URL` in docs vs `POSTGRES_DSN` in code; `NEXT_PUBLIC_NEXUS_API_URL` in compose.
- `AUDIT_REPORT.md` claims "128→164 tests, 0 warnings on win32" — platform mismatch (repo developed on Windows per diary; CI runs ubuntu) and stale counts.
