"use client";

import React, { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { apiClient, fetcher } from "@/lib/api";

type Lead = { id: string; score?: number | null; status?: string | null; source?: string | null; created_at?: string | null };
type LeadDetail = Lead & { profile_id?: string | null; tenant_id?: string; metadata?: Record<string, unknown> | null };
type LeadPayload = { id: string; score?: number | null; status?: string | null; source?: string | null; created_at?: string | null };

function dateLabel(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

function apiError(error: any) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (error?.response?.status === 401) return "The API rejected the credentials. Add a valid operator token in the top bar.";
  if (error?.response?.status === 403) return "This operation requires an operator token with lead-write access.";
  return error?.message || "The API request failed. Check the service connection and try again.";
}

export default function LeadsPage() {
  const { data, error, isLoading, mutate } = useSWR("/v1/leads", fetcher, { refreshInterval: 30000, revalidateOnFocus: true });
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [captureOpen, setCaptureOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<LeadDetail | null>(null);
  const [detailError, setDetailError] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const leads: Lead[] = Array.isArray(data?.leads) ? data.leads : [];

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("capture") === "1") {
      setCaptureOpen(true);
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []);

  const filtered = useMemo(() => leads.filter((lead) => {
    const matchesQuery = `${lead.id} ${lead.source || ""} ${lead.status || ""}`.toLowerCase().includes(query.toLowerCase());
    const matchesStatus = statusFilter === "all" || (lead.status || "unspecified").toLowerCase() === statusFilter;
    return matchesQuery && matchesStatus;
  }), [leads, query, statusFilter]);

  const openDetail = async (leadId: string) => {
    setSelectedId(leadId);
    setDetail(null);
    setDetailError("");
    setDetailLoading(true);
    try {
      const response = await apiClient.get(`/v1/leads/${encodeURIComponent(leadId)}`);
      setDetail(response.data?.lead || null);
    } catch (requestError) {
      setDetailError(apiError(requestError));
    } finally {
      setDetailLoading(false);
    }
  };

  const createLead = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const email = String(form.get("email") || "").trim();
    const name = String(form.get("name") || "").trim();
    const company = String(form.get("company") || "").trim();
    const source = String(form.get("source") || "website").trim();
    const profileId = String(form.get("profileId") || "").trim();
    const notes = String(form.get("notes") || "").trim();
    setSaving(true);
    setFormError("");
    try {
      const response = await apiClient.post("/v1/leads", {
        ...(profileId ? { profile_id: profileId } : {}),
        status: "new",
        source,
        metadata: { ...(email ? { email } : {}), ...(name ? { name } : {}), ...(company ? { company } : {}), ...(notes ? { notes } : {}) },
      });
      const created: LeadPayload | undefined = response.data?.lead;
      setCaptureOpen(false);
      formElement.reset();
      await mutate();
      if (created?.id) await openDetail(created.id);
    } catch (requestError) {
      setFormError(apiError(requestError));
    } finally {
      setSaving(false);
    }
  };

  const statuses = Array.from(new Set(leads.map((lead) => (lead.status || "unspecified").toLowerCase()))).sort();

  return (
    <div className="page-stack">
      <section className="page-heading">
        <div><span className="eyebrow">GROWTH WORKSPACE / LEADS</span><h1>Lead records</h1><p>Capture contact context and review the records actually stored for this tenant. Nothing here is sample data.</p></div>
        <div className="heading-actions"><button className="button-quiet" type="button" onClick={() => void mutate()}>↻ Refresh</button><button className="button-primary" type="button" onClick={() => { setFormError(""); setCaptureOpen(true); }}>＋ Capture lead</button></div>
      </section>

      <div className="inline-notice"><strong>Available today:</strong> CORTEX exposes lead create, list, and detail endpoints. Contact metadata is stored with the lead; no email-send or voice-call endpoint is currently wired into this console.</div>

      <section className="card">
        <div className="section-head">
          <div><h2>Lead list <span className="small-label">{isLoading ? "· loading" : error ? "· unavailable" : `· ${data?.total ?? leads.length} records`}</span></h2><p>Tenant-scoped list from <code>GET /v1/leads</code>; selecting a row requests its detail record.</p></div>
          <div className="toolbar">
            <label className="search-field"><span aria-hidden="true">⌕</span><input aria-label="Search lead records" placeholder="Search id, source, or status" value={query} onChange={(e) => setQuery(e.target.value)} /></label>
            <select className="select-field" aria-label="Filter leads by status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}><option value="all">All statuses</option>{statuses.map((status) => <option key={status} value={status}>{status}</option>)}</select>
          </div>
        </div>

        {isLoading ? <div className="state-panel"><div className="state-icon">···</div><h3>Loading lead records</h3><p>Reading tenant-scoped leads from CORTEX.</p></div> : error ? <div className="state-panel state-error"><div className="state-icon">!</div><h3>Could not load leads</h3><p>{apiError(error)}</p><button className="button-quiet" style={{ marginTop: 12 }} onClick={() => void mutate()}>Try again</button></div> : leads.length === 0 ? <div className="state-panel"><div className="state-icon">＋</div><h3>This lead list is empty</h3><p>Capture a real lead to create the first record. The page will not fill in sample contacts.</p><button className="button-primary" style={{ marginTop: 12 }} onClick={() => setCaptureOpen(true)}>Capture a lead</button></div> : filtered.length === 0 ? <div className="state-panel"><div className="state-icon">⌕</div><h3>No matches</h3><p>Change the search text or status filter to see more records.</p></div> : (
          <div className="table-wrap"><table className="data-table"><thead><tr><th>LEAD ID</th><th>STATUS</th><th>SOURCE</th><th>STORED SCORE</th><th>CREATED</th><th></th></tr></thead><tbody>{filtered.map((lead) => <tr key={lead.id} onClick={() => void openDetail(lead.id)} style={{ cursor: "pointer" }}><td><strong className="lead-id">{lead.id}</strong></td><td><span className="source-pill">{lead.status || "Unspecified"}</span></td><td>{lead.source || "—"}</td><td className="score-pill">{lead.score ?? "—"}</td><td>{dateLabel(lead.created_at)}</td><td><button className="button-quiet" type="button" aria-label={`Open lead ${lead.id}`} onClick={(event) => { event.stopPropagation(); void openDetail(lead.id); }}>Details ↗</button></td></tr>)}</tbody></table></div>
        )}
      </section>

      {selectedId && <section className="card card-pad">
        <div className="card-header"><div><span className="eyebrow">LEAD DETAIL</span><h2>{selectedId}</h2><p>Loaded from <code>GET /v1/leads/{"{lead_id}"}</code>.</p></div><button className="button-quiet" type="button" onClick={() => { setSelectedId(null); setDetail(null); }}>Close</button></div>
        {detailLoading ? <div className="state-panel"><h3>Loading lead detail</h3><p>Requesting the record from CORTEX.</p></div> : detailError ? <div className="form-error" role="alert">{detailError}</div> : detail ? <div className="lead-detail" style={{ marginTop: 15 }}><div className="lead-detail-grid"><div><span className="small-label">Status</span><span className="detail-value">{detail.status || "—"}</span></div><div><span className="small-label">Source</span><span className="detail-value">{detail.source || "—"}</span></div><div><span className="small-label">Profile ID</span><span className="detail-value">{detail.profile_id || "—"}</span></div><div><span className="small-label">Created</span><span className="detail-value">{dateLabel(detail.created_at)}</span></div></div><div style={{ marginTop: 14 }}><span className="small-label">Contact metadata stored on this record</span><pre style={{ margin: "6px 0 0", overflowX: "auto", whiteSpace: "pre-wrap", overflowWrap: "anywhere", color: "#435248", fontSize: 10 }}>{JSON.stringify(detail.metadata || {}, null, 2)}</pre></div></div> : null}
      </section>}

      {captureOpen && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !saving) setCaptureOpen(false); }}><form className="lead-dialog" onSubmit={createLead} role="dialog" aria-modal="true" aria-labelledby="capture-title">
        <button className="dialog-close" type="button" aria-label="Close" disabled={saving} onClick={() => setCaptureOpen(false)}>×</button>
        <span className="eyebrow">NEW LEAD RECORD</span><h2 id="capture-title">Capture a lead</h2><p>This creates a tenant-scoped record via <code>POST /v1/leads</code>. CORTEX stores these details as record metadata; it does not send outreach.</p>
        <div className="form-grid">
          <div className="form-field"><label htmlFor="lead-name">Contact name</label><input id="lead-name" name="name" autoComplete="name" placeholder="Name (optional)" /></div>
          <div className="form-field"><label htmlFor="lead-email">Email</label><input id="lead-email" name="email" type="email" autoComplete="email" placeholder="name@company.com" /></div>
          <div className="form-field"><label htmlFor="lead-company">Company</label><input id="lead-company" name="company" autoComplete="organization" placeholder="Company (optional)" /></div>
          <div className="form-field"><label htmlFor="lead-source">Source</label><input id="lead-source" name="source" defaultValue="website" required /></div>
          <div className="form-field form-full"><label htmlFor="lead-profile">Existing profile ID <span className="small-label">optional</span></label><input id="lead-profile" name="profileId" placeholder="Link an existing CORTEX profile" /></div>
          <div className="form-field form-full"><label htmlFor="lead-notes">Context</label><textarea id="lead-notes" name="notes" placeholder="What prompted this capture?" /><span className="form-hint">The current lead API stores contact/context fields in metadata and returns them in lead detail.</span></div>
        </div>
        {formError && <div className="form-error" role="alert">{formError}</div>}
        <div className="dialog-actions"><button className="button-quiet" type="button" disabled={saving} onClick={() => setCaptureOpen(false)}>Cancel</button><button className="button-primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Create lead record"}</button></div>
      </form></div>}
    </div>
  );
}
