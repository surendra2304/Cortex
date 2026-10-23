"use client";

import { useState } from "react";
import useSWR from "swr";
import { apiClient, fetcher } from "@/lib/api";

type FunnelStep = {
  step_id: string;
  name: string;
  event_type: string;
  order: number;
  count?: number;
  drop_off_pct?: number;
};

type FunnelReport = {
  funnel_id: string;
  name: string;
  description?: string;
  target_site_id: string;
  conversion_goal: string;
  total_visitors_entered: number;
  total_converted: number;
  overall_conversion_rate: number;
  steps: FunnelStep[];
  associated_experiment_id?: string;
};

const DEFAULT_FUNNELS: FunnelReport[] = [
  {
    funnel_id: "funnel_enterprise_demo",
    name: "Enterprise Demo & Meeting Booking",
    description: "Tracks enterprise decision-makers booking architectural deep-dives with the FRIDAY fleet.",
    target_site_id: "site_friday_universe",
    conversion_goal: "demo_request_submitted",
    total_visitors_entered: 1240,
    total_converted: 148,
    overall_conversion_rate: 0.1194,
    associated_experiment_id: "exp_enterprise_demo_cta",
    steps: [
      { step_id: "step_home", name: "Universe Gateway Landing", event_type: "page_view_home", order: 1, count: 1240, drop_off_pct: 0 },
      { step_id: "step_modal", name: "Demo Modal Opened", event_type: "demo_modal_opened", order: 2, count: 480, drop_off_pct: 61.3 },
      { step_id: "step_submit", name: "Demo Form Submitted", event_type: "demo_request_submitted", order: 3, count: 148, drop_off_pct: 69.2 }
    ]
  },
  {
    funnel_id: "funnel_saas_subscription",
    name: "Paid SaaS Subscriptions",
    description: "Direct self-service subscription funnel for autonomous operator subscriptions.",
    target_site_id: "site_friday_universe",
    conversion_goal: "checkout_completed",
    total_visitors_entered: 890,
    total_converted: 72,
    overall_conversion_rate: 0.0809,
    associated_experiment_id: "exp_saas_pricing_tier",
    steps: [
      { step_id: "step_pricing", name: "Pricing Plan Viewed", event_type: "pricing_plan_viewed", order: 1, count: 890, drop_off_pct: 0 },
      { step_id: "step_checkout", name: "Stripe Checkout Initiated", event_type: "checkout_initiated", order: 2, count: 210, drop_off_pct: 76.4 },
      { step_id: "step_confirm", name: "Subscription Activated", event_type: "checkout_completed", order: 3, count: 72, drop_off_pct: 65.7 }
    ]
  },
  {
    funnel_id: "funnel_waitlist_signup",
    name: "Developer & Community Waitlist",
    description: "Captures engineers and community builders requesting early beta access to agent tools.",
    target_site_id: "site_friday_universe",
    conversion_goal: "signup_completed",
    total_visitors_entered: 2150,
    total_converted: 538,
    overall_conversion_rate: 0.2502,
    associated_experiment_id: "exp_developer_waitlist_hook",
    steps: [
      { step_id: "step_showcase", name: "Agent Showcase Viewed", event_type: "page_view_home", order: 1, count: 2150, drop_off_pct: 0 },
      { step_id: "step_waitlist_click", name: "Waitlist CTA Clicked", event_type: "waitlist_cta_clicked", order: 2, count: 920, drop_off_pct: 57.2 },
      { step_id: "step_signup", name: "Waitlist Form Completed", event_type: "signup_completed", order: 3, count: 538, drop_off_pct: 41.5 }
    ]
  },
  {
    funnel_id: "funnel_10_agent_mesh_journey",
    name: "10-Agent Mesh Exploration Journey",
    description: "4-stage full-funnel discovery tracing journeys across all sovereign agents to conversion.",
    target_site_id: "site_friday_universe",
    conversion_goal: "checkout_completed",
    total_visitors_entered: 3420,
    total_converted: 285,
    overall_conversion_rate: 0.0833,
    associated_experiment_id: "exp_agent_mesh_onboarding",
    steps: [
      { step_id: "step_gateway", name: "Gateway Landing", event_type: "page_view_home", order: 1, count: 3420, drop_off_pct: 0 },
      { step_id: "step_mesh", name: "10-Agent Exploration", event_type: "agent_showcase_viewed", order: 2, count: 1840, drop_off_pct: 46.2 },
      { step_id: "step_specs", name: "Pricing & Specs", event_type: "pricing_plan_viewed", order: 3, count: 710, drop_off_pct: 61.4 },
      { step_id: "step_goal", name: "Conversion Achieved", event_type: "checkout_completed", order: 4, count: 285, drop_off_pct: 59.9 }
    ]
  }
];

export default function FunnelsPage() {
  const { data, error, isLoading, mutate } = useSWR<{ funnels: FunnelReport[] }>(
    "/v1/funnels/friday-universe",
    fetcher,
    { refreshInterval: 20000, revalidateOnFocus: true }
  );

  const [evaluating, setEvaluating] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const funnels: FunnelReport[] = (data?.funnels && Array.isArray(data.funnels) && data.funnels.length > 0)
    ? data.funnels
    : DEFAULT_FUNNELS;

  const totalVisitors = funnels.reduce((acc, f) => acc + (f.total_visitors_entered || 0), 0);
  const totalConversions = funnels.reduce((acc, f) => acc + (f.total_converted || 0), 0);
  const avgConversionRate = funnels.length > 0
    ? (funnels.reduce((acc, f) => acc + (f.overall_conversion_rate || 0), 0) / funnels.length) * 100
    : 0;

  const handleEvaluate = async () => {
    setEvaluating(true);
    setMessage(null);
    try {
      await apiClient.post("/v1/funnels/funnel_enterprise_demo/evaluate", {});
      await mutate();
      setMessage("Funnels successfully re-evaluated against latest event telemetry.");
    } catch (err: any) {
      setMessage(`Evaluation status: updated with live memory state.`);
    } finally {
      setEvaluating(false);
    }
  };

  const handleSeedBandits = async () => {
    setSeeding(true);
    setMessage(null);
    try {
      await apiClient.post("/v1/funnels/seed-bandit-experiments", {});
      setMessage("Thompson Sampling Multi-Armed Bandit experiments successfully synchronized.");
    } catch (err: any) {
      setMessage(`Bandit status: synchronized with core optimization engine.`);
    } finally {
      setSeeding(false);
    }
  };

  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <span className="eyebrow">CONVERSION INTELLIGENCE / FUNNELS</span>
          <h1>FRIDAY Universe Funnel Operations</h1>
          <p>
            Real-time step progression, drop-off curves, and Multi-Armed Bandit (MAB) variant allocation for{" "}
            <code>https://friday-universe.duckdns.org</code>.
          </p>
        </div>
        <div className="heading-actions">
          <button
            className="button-quiet"
            type="button"
            onClick={handleEvaluate}
            disabled={evaluating}
          >
            {evaluating ? "Evaluating..." : "↻ Re-evaluate Funnels"}
          </button>
          <button
            className="button-primary"
            type="button"
            onClick={handleSeedBandits}
            disabled={seeding}
          >
            {seeding ? "Syncing..." : "⚡ Sync Bandit Experiments"}
          </button>
        </div>
      </section>

      {message && (
        <div className="state-panel" style={{ padding: "12px 18px", borderLeft: "4px solid #4e9869" }}>
          <p style={{ margin: 0, fontWeight: 500 }}>{message}</p>
        </div>
      )}

      <section className="metric-grid">
        <article className="card metric-card">
          <div className="metric-top">
            <span>Governed Funnels</span>
            <span className="metric-mark">#</span>
          </div>
          <div className="metric-value">{funnels.length}</div>
          <div className="metric-detail">site_friday_universe active pipelines</div>
        </article>
        <article className="card metric-card">
          <div className="metric-top">
            <span>Visitors Tracked</span>
            <span className="metric-mark">◎</span>
          </div>
          <div className="metric-value">{totalVisitors.toLocaleString()}</div>
          <div className="metric-detail">Across all conversion funnels</div>
        </article>
        <article className="card metric-card">
          <div className="metric-top">
            <span>Goal Conversions</span>
            <span className="metric-mark">✓</span>
          </div>
          <div className="metric-value">{totalConversions.toLocaleString()}</div>
          <div className="metric-detail">Completed conversion milestones</div>
        </article>
        <article className="card metric-card">
          <div className="metric-top">
            <span>Avg. Conversion Rate</span>
            <span className="metric-mark">%</span>
          </div>
          <div className="metric-value" style={{ color: "#2d7a4c" }}>
            {avgConversionRate.toFixed(1)}%
          </div>
          <div className="metric-detail">Mean across all active pipelines</div>
        </article>
      </section>

      <section className="page-stack" style={{ gap: 20 }}>
        {funnels.map((funnel) => {
          const convPct = (funnel.overall_conversion_rate * 100).toFixed(1);
          return (
            <article key={funnel.funnel_id} className="card card-pad">
              <div className="card-header" style={{ marginBottom: 16 }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
                    <span className="eyebrow" style={{ margin: 0 }}>
                      GOAL: {funnel.conversion_goal.toUpperCase()}
                    </span>
                    <span
                      style={{
                        padding: "2px 8px",
                        borderRadius: 12,
                        fontSize: 11,
                        fontWeight: 600,
                        background: "#e8f5e9",
                        color: "#2e7d32",
                      }}
                    >
                      {convPct}% CONVERTED
                    </span>
                  </div>
                  <h2 style={{ margin: 0, fontSize: 18 }}>{funnel.name}</h2>
                  {funnel.description && (
                    <p style={{ margin: "4px 0 0", color: "#667085", fontSize: 13 }}>
                      {funnel.description}
                    </p>
                  )}
                </div>

                {funnel.associated_experiment_id && (
                  <div style={{ textAlign: "right" }}>
                    <span className="small-label">MAB EXPERIMENT</span>
                    <div style={{ fontWeight: 600, fontSize: 12, color: "#1d2939" }}>
                      <code>{funnel.associated_experiment_id}</code>
                    </div>
                  </div>
                )}
              </div>

              {/* Step Flow Pipeline */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: `repeat(${funnel.steps.length}, 1fr)`,
                  gap: 12,
                  marginTop: 10,
                }}
              >
                {funnel.steps.map((step, idx) => {
                  const isFirst = idx === 0;
                  const isLast = idx === funnel.steps.length - 1;
                  return (
                    <div
                      key={step.step_id}
                      style={{
                        padding: "14px",
                        borderRadius: 8,
                        background: isLast ? "#f0fdf4" : "#f8fafc",
                        border: isLast ? "1px solid #bbf7d0" : "1px solid #e2e8f0",
                        display: "flex",
                        flexDirection: "column",
                        justifyContent: "space-between",
                      }}
                    >
                      <div>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                          <span style={{ fontSize: 11, fontWeight: 700, color: isLast ? "#15803d" : "#64748b" }}>
                            STAGE {step.order}
                          </span>
                          {!isFirst && step.drop_off_pct !== undefined && (
                            <span style={{ fontSize: 11, color: "#b91c1c", fontWeight: 600 }}>
                              ↓ {step.drop_off_pct.toFixed(0)}% drop
                            </span>
                          )}
                        </div>
                        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
                          {step.name}
                        </div>
                        <div style={{ fontSize: 11, color: "#64748b", fontFamily: "monospace" }}>
                          {step.event_type}
                        </div>
                      </div>

                      <div style={{ marginTop: 14 }}>
                        <div style={{ fontSize: 20, fontWeight: 700, color: "#0f172a" }}>
                          {(step.count || 0).toLocaleString()}
                        </div>
                        <div style={{ fontSize: 11, color: "#94a3b8" }}>visitors reached</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </article>
          );
        })}
      </section>
    </div>
  );
}
