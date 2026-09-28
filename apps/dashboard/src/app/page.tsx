"use client";

import Link from "next/link";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

type Lead = { id: string; score?: number | null; status?: string | null; source?: string | null; created_at?: string | null };
type EventRecord = { event_id: string; type?: string; actor_id?: string; source?: string; occurred_at?: string | null };

function State({ title, body, error = false }: { title: string; body: string; error?: boolean }) {
  return <div className={`state-panel${error ? " state-error" : ""}`}><div className="state-icon" aria-hidden="true">{error ? "!" : "···"}</div><h3>{title}</h3><p>{body}</p></div>;
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function downloadCsv(rows: Lead[]) {
  const quote = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  const csv = [["Lead ID", "Status", "Source", "Score", "Created at"], ...rows.map((lead) => [lead.id, lead.status, lead.source, lead.score, lead.created_at])]
    .map((row) => row.map(quote).join(",")).join("\r\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "cortex-leads.csv";
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function ExecutiveOverviewPage() {
  const { data: health, error: healthError, isLoading: healthLoading, mutate: refreshHealth } = useSWR("/health", fetcher, { refreshInterval: 30000, revalidateOnFocus: true });
  const { data: leadData, error: leadsError, isLoading: leadsLoading, mutate: refreshLeads } = useSWR("/v1/leads", fetcher, { refreshInterval: 30000, revalidateOnFocus: true });
  const { data: events, error: eventsError, isLoading: eventsLoading, mutate: refreshEvents } = useSWR<EventRecord[]>("/v1/events?limit=8", fetcher, { refreshInterval: 20000, revalidateOnFocus: true });
  const leads: Lead[] = Array.isArray(leadData?.leads) ? leadData.leads : [];
  const recentEvents: EventRecord[] = Array.isArray(events) ? events : [];
  const serverHealthy = health?.status === "healthy" || health?.status === "UP";
  const uniqueSources = new Set(leads.map((lead) => lead.source).filter(Boolean)).size;

  return (
    <div className="page-stack">
      <section className="page-heading">
        <div><span className="eyebrow">GROWTH WORKSPACE / OVERVIEW</span><h1>Turn real signals into better leads.</h1><p>Your live CORTEX view for captured leads and recent product activity. Metrics only appear when the API returns them.</p></div>
        <div className="heading-actions">
          <button className="button-quiet" type="button" onClick={() => { void refreshHealth(); void refreshLeads(); void refreshEvents(); }}>↻ <span>Refresh</span></button>
          <button className="button-outline" type="button" onClick={() => downloadCsv(leads)} disabled={leads.length === 0}>↓ Export leads</button>
        </div>
      </section>

      <section className="overview-grid" aria-label="Workspace status and lead capture">
        <div className="hero-card">
          <span className="eyebrow">LEAD WORKBENCH</span>
          <h2>Make every inbound signal count.</h2>
          <p>Capture a lead, keep its source and context together, then follow its record through the CORTEX API.</p>
          <div className="hero-actions"><Link href="/leads?capture=1" className="button-primary">＋ Capture a lead</Link><Link href="/leads" className="button-quiet">Open lead workspace <span aria-hidden="true">↗</span></Link></div>
        </div>
        <div className="card api-card">
          <div>
            <div className="api-card-top"><span className="api-icon" aria-hidden="true">⌁</span><span className={`status-tag ${healthLoading ? "neutral" : serverHealthy ? "good" : healthError ? "bad" : "warn"}`}>{healthLoading ? "Checking API" : serverHealthy ? "API responding" : healthError ? "API unavailable" : "Unexpected response"}</span></div>
            <h3>Connected workspace</h3><p>Live liveness response from <code>/health</code>. This confirms the API process responds, not that every integration is ready.</p>
          </div>
          <div className="api-card-foot"><span>Service</span><strong>{health?.service || "CORTEX API"}</strong></div>
        </div>
      </section>

      <section className="metric-grid" aria-label="Live workspace totals">
        <article className="card metric-card"><div className="metric-top"><span>Saved leads</span><span className="metric-mark">◎</span></div><div className="metric-value">{leadsLoading ? "···" : leadsError ? "—" : leadData?.total ?? leads.length}</div><div className="metric-detail">Records returned by <code>/v1/leads</code></div></article>
        <article className="card metric-card"><div className="metric-top"><span>Recent events</span><span className="metric-mark">⌁</span></div><div className="metric-value">{eventsLoading ? "···" : eventsError ? "—" : recentEvents.length}</div><div className="metric-detail">Latest {recentEvents.length ? "rows" : "query returned no rows"} · limit 8</div></article>
        <article className="card metric-card"><div className="metric-top"><span>Lead sources</span><span className="metric-mark">↗</span></div><div className="metric-value">{leadsLoading ? "···" : leadsError ? "—" : uniqueSources}</div><div className="metric-detail">Distinct non-empty sources in returned leads</div></article>
        <article className="card metric-card"><div className="metric-top"><span>Last API check</span><span className="metric-mark">◷</span></div><div className="metric-value" style={{ fontSize: 16, marginTop: 14 }}>{health?.timestamp ? formatDate(health.timestamp) : healthLoading ? "Checking" : "—"}</div><div className="metric-detail">Timestamp supplied by the API</div></article>
      </section>

      <section className="content-grid">
        <div className="card">
          <div className="section-head"><div><h2>Recently captured leads</h2><p>Latest records returned by your tenant-scoped lead endpoint.</p></div><Link href="/leads" className="section-link">View all leads ↗</Link></div>
          {leadsLoading ? <State title="Loading lead records" body="CORTEX is reading the lead list from your API." /> : leadsError ? <State error title="Could not load leads" body="Check the API connection and operator token, then retry from the lead workspace." /> : leads.length === 0 ? <State title="No lead records yet" body="When you capture a lead in this workspace, it will appear here. No example records are inserted." /> : (
            <div className="table-wrap"><table className="data-table"><thead><tr><th>LEAD</th><th>STATUS</th><th>SOURCE</th><th>SCORE</th><th>CREATED</th></tr></thead><tbody>
              {leads.slice(0, 6).map((lead) => <tr key={lead.id}><td><Link href={`/leads?id=${encodeURIComponent(lead.id)}`}><strong className="lead-id">{lead.id}</strong></Link></td><td><span className="source-pill">{lead.status || "Unspecified"}</span></td><td>{lead.source || "—"}</td><td className="score-pill">{lead.score ?? "—"}</td><td>{formatDate(lead.created_at)}</td></tr>)}
            </tbody></table></div>
          )}
        </div>
        <div className="card">
          <div className="section-head"><div><h2>Recent activity</h2><p>Event records from the CORTEX event store.</p></div><Link href="/activity" className="section-link">Activity log ↗</Link></div>
          {eventsLoading ? <State title="Loading activity" body="Reading the latest event records." /> : eventsError ? <State error title="Activity unavailable" body="The event endpoint did not return data. Verify the API token and event store." /> : recentEvents.length === 0 ? <State title="Waiting for the first event" body="No event rows were returned for this workspace. Incoming events will be listed here." /> : <div className="activity-list">{recentEvents.slice(0, 6).map((event, index) => <div className="activity-item" key={event.event_id || `${event.type}-${index}`}><span className="activity-bullet" aria-hidden="true">↗</span><div className="activity-copy"><strong>{event.type || "Event"}</strong><span>{event.actor_id || "Unknown actor"} · {event.source || "source not provided"}</span></div><span className="activity-time">{formatDate(event.occurred_at)}</span></div>)}</div>}
        </div>
      </section>

      <div className="inline-notice"><strong>Outreach status:</strong> this console can create and read lead records. The current API does not expose a verified email-send or calling action, so those controls are not represented as active.</div>
    </div>
  );
}
