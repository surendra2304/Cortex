"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

type EventRecord = { event_id: string; type?: string; actor_id?: string; actor_type?: string; site_id?: string; session_id?: string; occurred_at?: string | null; source?: string; data?: Record<string, unknown> | null };

function describeError(error: any) {
  if (error?.response?.status === 401) return "The API rejected the credentials. Add a valid operator token in the top bar.";
  if (error?.response?.status === 403) return "This request needs a CORTEX viewer token.";
  return error?.response?.data?.detail || error?.message || "The activity endpoint could not be reached.";
}

export default function ActivityPage() {
  const { data, error, isLoading, mutate } = useSWR<EventRecord[]>("/v1/events?limit=100", fetcher, { refreshInterval: 15000, revalidateOnFocus: true });
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<EventRecord | null>(null);
  const events = Array.isArray(data) ? data : [];
  const filtered = useMemo(() => events.filter((event) => `${event.type || ""} ${event.actor_id || ""} ${event.actor_type || ""} ${event.source || ""} ${event.site_id || ""}`.toLowerCase().includes(search.toLowerCase())), [events, search]);
  const eventKinds = useMemo(() => {
    const tally = new Map<string, number>();
    for (const event of events) tally.set(event.type || "unknown", (tally.get(event.type || "unknown") || 0) + 1);
    return Array.from(tally.entries()).sort((a, b) => b[1] - a[1]).slice(0, 5);
  }, [events]);
  const maxKind = Math.max(1, ...eventKinds.map((entry) => entry[1]));

  return <div className="page-stack">
    <section className="page-heading"><div><span className="eyebrow">GROWTH WORKSPACE / ACTIVITY</span><h1>Product activity</h1><p>Inspect event rows stored for the current tenant. The list refreshes every 15 seconds while this page is open.</p></div><div className="heading-actions"><span className="live-label">15s refresh</span><button className="button-quiet" type="button" onClick={() => void mutate()}>↻ Refresh now</button></div></section>

    <section className="metric-grid">
      <article className="card metric-card"><div className="metric-top"><span>Rows returned</span><span className="metric-mark">⌁</span></div><div className="metric-value">{isLoading ? "···" : error ? "—" : events.length}</div><div className="metric-detail">Latest records · API limit 100</div></article>
      <article className="card metric-card"><div className="metric-top"><span>Event types</span><span className="metric-mark">#</span></div><div className="metric-value">{isLoading ? "···" : error ? "—" : new Set(events.map((event) => event.type).filter(Boolean)).size}</div><div className="metric-detail">Distinct types in returned rows</div></article>
      <article className="card metric-card"><div className="metric-top"><span>Actors</span><span className="metric-mark">◎</span></div><div className="metric-value">{isLoading ? "···" : error ? "—" : new Set(events.map((event) => event.actor_id).filter(Boolean)).size}</div><div className="metric-detail">Distinct actor IDs in returned rows</div></article>
      <article className="card metric-card"><div className="metric-top"><span>Data source</span><span className="metric-mark">↗</span></div><div className="metric-value" style={{ fontSize: 15, marginTop: 14 }}>CORTEX API</div><div className="metric-detail"><code>GET /v1/events?limit=100</code></div></article>
    </section>

    <section className="content-grid">
      <div className="card">
        <div className="section-head"><div><h2>Event stream</h2><p>Stored events, newest first. Select a row to inspect its payload.</p></div><label className="search-field"><span aria-hidden="true">⌕</span><input aria-label="Filter activity events" placeholder="Filter type, actor, or source" value={search} onChange={(event) => setSearch(event.target.value)} /></label></div>
        {isLoading ? <div className="state-panel"><div className="state-icon">···</div><h3>Loading activity</h3><p>Requesting the latest event rows from CORTEX.</p></div> : error ? <div className="state-panel state-error"><div className="state-icon">!</div><h3>Activity unavailable</h3><p>{describeError(error)}</p><button className="button-quiet" style={{ marginTop: 12 }} onClick={() => void mutate()}>Try again</button></div> : events.length === 0 ? <div className="state-panel"><div className="state-icon">⌁</div><h3>No events in this workspace</h3><p>The API returned an empty event list. New records will appear after event ingestion is configured.</p></div> : filtered.length === 0 ? <div className="state-panel"><div className="state-icon">⌕</div><h3>No matching events</h3><p>Try a different actor, type, or source search.</p></div> : <div className="table-wrap"><table className="data-table"><thead><tr><th>TIME</th><th>EVENT</th><th>ACTOR</th><th>SOURCE</th><th>SITE</th></tr></thead><tbody>{filtered.map((event) => <tr key={event.event_id} onClick={() => setSelected(event)} style={{ cursor: "pointer" }}><td>{event.occurred_at ? new Date(event.occurred_at).toLocaleString() : "—"}</td><td><strong>{event.type || "Unknown"}</strong></td><td><span className="lead-id">{event.actor_id || "—"}</span><small>{event.actor_type || "actor type not provided"}</small></td><td>{event.source || "—"}</td><td>{event.site_id || "—"}</td></tr>)}</tbody></table></div>}
      </div>
      <div className="card">
        <div className="section-head"><div><h2>Event mix</h2><p>Counts calculated from these returned rows.</p></div></div>
        {isLoading ? <div className="state-panel"><p>Loading event counts…</p></div> : error ? <div className="state-panel"><p>Counts unavailable until the event request succeeds.</p></div> : eventKinds.length === 0 ? <div className="state-panel"><p>No event types to summarize yet.</p></div> : <div className="card-pad" style={{ display: "grid", gap: 15 }}>{eventKinds.map(([kind, count]) => <div key={kind}><div className="metric-top" style={{ marginBottom: 7 }}><span>{kind}</span><strong style={{ color: "#506057", fontSize: 9 }}>{count}</strong></div><div style={{ height: 5, borderRadius: 9, background: "#edf1ec", overflow: "hidden" }}><div style={{ width: `${(count / maxKind) * 100}%`, height: "100%", borderRadius: 9, background: "#4e9869" }} /></div></div>)}</div>}
      </div>
    </section>

    {selected && <section className="card card-pad"><div className="card-header"><div><span className="eyebrow">EVENT DETAIL</span><h2>{selected.type || "Event"}</h2><p>{selected.event_id}</p></div><button className="button-quiet" type="button" onClick={() => setSelected(null)}>Close</button></div><div className="lead-detail-grid" style={{ marginTop: 15 }}><div><span className="small-label">Actor</span><span className="detail-value">{selected.actor_id || "—"}</span></div><div><span className="small-label">Session</span><span className="detail-value">{selected.session_id || "—"}</span></div><div><span className="small-label">Site</span><span className="detail-value">{selected.site_id || "—"}</span></div><div><span className="small-label">Source</span><span className="detail-value">{selected.source || "—"}</span></div></div><pre style={{ marginTop: 14, padding: 12, overflowX: "auto", whiteSpace: "pre-wrap", overflowWrap: "anywhere", border: "1px solid #e7ece6", borderRadius: 8, background: "#fbfcfa", color: "#435248", fontSize: 9 }}>{JSON.stringify(selected.data || {}, null, 2)}</pre></section>}
  </div>;
}
