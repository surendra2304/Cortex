# Phase 7 — Frontend (apps/dashboard + packages/sdk)

Date: 2026-10-07

## Dashboard [FACT]

- **Next.js 14.2.35** (lockfile), React 18.3.1, app router, TypeScript, Tailwind; `next.config.js`: `output: 'export'`, `trailingSlash: true`, `images.unoptimized: true`.
- **17 pages** under `src/app/`: overview (`/`), leads, activity (the only 3 linked in `Sidebar.tsx`), + 13 more — agents, analytics, automation, connectors, conversations, customers, experiments, funnels, governance, incidents, integrations, intelligence, memory, settings, visitors — **13 of 17 are 5-line `ModuleStatus` stubs** ("module not wired" placeholders). Real pages: Overview, Leads (3.77 kB), Activity, Visitors (179 B).
- `src/lib/api.ts`: relative baseURL in browser; Bearer token from `localStorage["cortex_operator_token"]`; `CredentialControl.tsx` = token input UI. First Load JS ~87-116 kB/page.
- **Committed static export** `apps/dashboard/out/` (17 prerendered pages, tracked in git; `!.gitignore` negation). Regenerating it changes **81 tracked files** (chunk hashes differ per build) [FACT, this session: built, diffed, restored via `git checkout`]. The API serves this export at `/` (`main.py:278-345`).
- **Build**: `npm run build` succeeds (26 s, 17 static pages) [FACT, this session]. `npm ci` works at root and per-workspace [FACT] — the prior audit's lockfile/platform-optional-deps failure claim is **stale** (lockfile now v3 with 17 platform optional deps, next pinned 14.2.35).
- **Broken container path [FACT, executed]**: `apps/dashboard/Dockerfile` ends with `CMD ["npm", "start"]` → `next start` aborts: `Error: "next start" does not work with "output: export" configuration. Use "npx serve@latest out" instead.` The docker-compose `dashboard` service would crash-loop. The compose file also passes `NEXT_PUBLIC_NEXUS_API_URL` (stale `nexus_*` name; the app reads `NEXT_PUBLIC_CORTEX_API_URL`).
- **npm audit**: 9 vulnerabilities (1 critical, 6 high, 2 moderate) — mostly Next.js version-range advisories not reachable in a static export (no server features); build-time deps only. See Phase 1.
- `landing_page.py` (API side): 797-line `FALLBACK_WEBSITE_HTML` — a marketing/ops page with an interactive 10-phase cognitive-loop simulator in vanilla JS + Tailwind CDN; served when no dashboard export exists.

## Browser SDK (`packages/sdk`) [FACT]

- 341-line `src/index.ts`; tsup build → CJS + ESM + IIFE + d.ts [FACT, built clean]; `npm test` = `tsc --noEmit` clean [FACT].
- Consent defaults **false** (prior audit H9 fix); queues events, batches, retry with backoff, falls back to single POST; sends `X-Cortex-Public-Key`; 30-minute session window; UTM capture + automatic `page_view`.
- Used by customer sites to ingest telemetry into `/v1/events`.

## Assessment [INFERENCE]

The dashboard is a thin, partially stubbed operator console (3 of 17 pages real) over a rich API; the committed `out/` export is the actual production artifact served by the API. The Dockerfile for it is broken, so the compose dashboard service never worked as written; the intended serving path is the API's static mount.
