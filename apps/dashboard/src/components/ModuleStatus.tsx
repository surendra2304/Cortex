import Link from "next/link";

export default function ModuleStatus({ title }: { title: string }) {
  return <div className="page-stack">
    <section className="page-heading"><div><span className="eyebrow">CORTEX WORKSPACE / MODULE</span><h1>{title}</h1><p>This module is not part of the live lead console yet.</p></div><Link className="button-quiet" href="/">← Back to overview</Link></section>
    <section className="card state-panel"><div className="state-icon">⌁</div><h3>No verified live view is connected</h3><p>The current frontend does not have a verified API contract and working workflow for this module. No sample metrics, records, or “live” status are shown here.</p><div style={{ display: "flex", justifyContent: "center", gap: 9, marginTop: 14 }}><Link className="button-primary" href="/leads">Open lead workspace</Link><Link className="button-quiet" href="/activity">Review activity</Link></div></section>
  </div>;
}
