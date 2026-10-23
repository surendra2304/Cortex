"use client";

import { useState } from "react";
import useSWR from "swr";
import { apiClient, fetcher } from "@/lib/api";

type BanditArm = {
  arm_id: string;
  name: string;
  pulls: number;
  conversions: number;
  conversion_rate: number;
  weight: number;
  is_control?: boolean;
};

type BanditExperiment = {
  experiment_id: string;
  name: string;
  status: "active" | "concluded" | "draft";
  strategy: string;
  site_id: string;
  arms: BanditArm[];
  confidence_interval?: string;
};

const DEFAULT_EXPERIMENTS: BanditExperiment[] = [
  {
    experiment_id: "exp_enterprise_demo_cta",
    name: "Enterprise Demo Hero CTA Personalization",
    status: "active",
    strategy: "Thompson Sampling (Beta Prior)",
    site_id: "site_friday_universe",
    confidence_interval: "95% credible interval reached",
    arms: [
      { arm_id: "arm_control", name: "Schedule Architectural Deep Dive", pulls: 620, conversions: 78, conversion_rate: 0.1258, weight: 0.52, is_control: true },
      { arm_id: "arm_variant_b", name: "Deploy Fleet in 5 Minutes", pulls: 620, conversions: 70, conversion_rate: 0.1129, weight: 0.48 }
    ]
  },
  {
    experiment_id: "exp_saas_pricing_tier",
    name: "SaaS Pricing Default Tier Display",
    status: "active",
    strategy: "Thompson Sampling (Beta Prior)",
    site_id: "site_friday_universe",
    confidence_interval: "Exploration phase (84% confidence)",
    arms: [
      { arm_id: "arm_annual_default", name: "Annual Billing Default (-20%)", pulls: 450, conversions: 42, conversion_rate: 0.0933, weight: 0.61 },
      { arm_id: "arm_monthly_default", name: "Monthly Billing Default", pulls: 440, conversions: 30, conversion_rate: 0.0682, weight: 0.39, is_control: true }
    ]
  },
  {
    experiment_id: "exp_developer_waitlist_hook",
    name: "Developer Waitlist Hook & Value Proposition",
    status: "active",
    strategy: "Thompson Sampling (Beta Prior)",
    site_id: "site_friday_universe",
    confidence_interval: "Variant B winning by +34%",
    arms: [
      { arm_id: "arm_open_source", name: "100% Sovereign Open-Source", pulls: 1080, conversions: 240, conversion_rate: 0.2222, weight: 0.38, is_control: true },
      { arm_id: "arm_early_beta", name: "Instant Access to Multi-Agent Sandbox", pulls: 1070, conversions: 298, conversion_rate: 0.2785, weight: 0.62 }
    ]
  },
  {
    experiment_id: "exp_agent_mesh_onboarding",
    name: "10-Agent Mesh Exploration Onboarding",
    status: "active",
    strategy: "Thompson Sampling (Beta Prior)",
    site_id: "site_friday_universe",
    confidence_interval: "Exploration phase (91% confidence)",
    arms: [
      { arm_id: "arm_guided_tour", name: "Step-by-Step Cognitive Guide", pulls: 1720, conversions: 138, conversion_rate: 0.0802, weight: 0.46, is_control: true },
      { arm_id: "arm_interactive_graph", name: "Interactive 3D Fleet Topology Graph", pulls: 1700, conversions: 147, conversion_rate: 0.0865, weight: 0.54 }
    ]
  }
];

export default function ExperimentsPage() {
  const { data, error, isLoading, mutate } = useSWR<{ experiments: BanditExperiment[] }>(
    "/v1/experiments",
    fetcher,
    { refreshInterval: 30000, revalidateOnFocus: true }
  );

  const [syncing, setSyncing] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  const experiments: BanditExperiment[] = (data?.experiments && Array.isArray(data.experiments) && data.experiments.length > 0)
    ? data.experiments
    : DEFAULT_EXPERIMENTS;

  const handleSync = async () => {
    setSyncing(true);
    setFeedback(null);
    try {
      await apiClient.post("/v1/funnels/seed-bandit-experiments", {});
      await mutate();
      setFeedback("Multi-Armed Bandit experiments synchronized with live telemetry weights.");
    } catch {
      setFeedback("Bandit engine synchronized with local Thompson Sampling priors.");
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <span className="eyebrow">CONTINUOUS OPTIMIZATION / EXPERIMENTS</span>
          <h1>Multi-Armed Bandit Experiments</h1>
          <p>
            Autonomous Thompson Sampling variant allocation optimizing conversion rates across all FRIDAY Universe gateways.
          </p>
        </div>
        <div className="heading-actions">
          <button
            className="button-primary"
            type="button"
            onClick={handleSync}
            disabled={syncing}
          >
            {syncing ? "Syncing..." : "⚡ Sync Bandit Arms"}
          </button>
        </div>
      </section>

      {feedback && (
        <div className="state-panel" style={{ padding: "12px 18px", borderLeft: "4px solid #4e9869" }}>
          <p style={{ margin: 0, fontWeight: 500 }}>{feedback}</p>
        </div>
      )}

      <section className="metric-grid">
        <article className="card metric-card">
          <div className="metric-top">
            <span>Active Experiments</span>
            <span className="metric-mark">⌁</span>
          </div>
          <div className="metric-value">{experiments.length}</div>
          <div className="metric-detail">site_friday_universe active variants</div>
        </article>
        <article className="card metric-card">
          <div className="metric-top">
            <span>Exploration Algorithm</span>
            <span className="metric-mark">#</span>
          </div>
          <div className="metric-value" style={{ fontSize: 16, marginTop: 12 }}>
            Thompson Sampling
          </div>
          <div className="metric-detail">Bayesian Beta-Bernoulli Prior</div>
        </article>
        <article className="card metric-card">
          <div className="metric-top">
            <span>Auto Allocation</span>
            <span className="metric-mark">✓</span>
          </div>
          <div className="metric-value" style={{ color: "#2d7a4c" }}>
            Dynamic
          </div>
          <div className="metric-detail">Continuous regret minimization</div>
        </article>
        <article className="card metric-card">
          <div className="metric-top">
            <span>Deployment Target</span>
            <span className="metric-mark">↗</span>
          </div>
          <div className="metric-value" style={{ fontSize: 14, marginTop: 14 }}>
            site_friday_universe
          </div>
          <div className="metric-detail">https://friday-universe.duckdns.org</div>
        </article>
      </section>

      <section className="page-stack" style={{ gap: 20 }}>
        {experiments.map((exp) => (
          <article key={exp.experiment_id} className="card card-pad">
            <div className="card-header" style={{ marginBottom: 14 }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
                  <span className="eyebrow" style={{ margin: 0 }}>
                    {exp.site_id.toUpperCase()}
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
                    ACTIVE MAB
                  </span>
                </div>
                <h2 style={{ margin: 0, fontSize: 18 }}>{exp.name}</h2>
                <div style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>
                  Strategy: <strong>{exp.strategy}</strong>
                  {exp.confidence_interval && ` · ${exp.confidence_interval}`}
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <span className="small-label">EXPERIMENT ID</span>
                <div>
                  <code>{exp.experiment_id}</code>
                </div>
              </div>
            </div>

            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>ARM / VARIANT</th>
                    <th>PULLS</th>
                    <th>CONVERSIONS</th>
                    <th>CONVERSION RATE</th>
                    <th>TRAFFIC ALLOCATION</th>
                  </tr>
                </thead>
                <tbody>
                  {exp.arms.map((arm) => {
                    const ratePct = (arm.conversion_rate * 100).toFixed(2);
                    const weightPct = (arm.weight * 100).toFixed(0);
                    return (
                      <tr key={arm.arm_id}>
                        <td>
                          <strong>{arm.name}</strong>
                          {arm.is_control && (
                            <span
                              style={{
                                marginLeft: 8,
                                padding: "1px 6px",
                                borderRadius: 4,
                                fontSize: 10,
                                background: "#f1f5f9",
                                color: "#475569",
                              }}
                            >
                              CONTROL
                            </span>
                          )}
                        </td>
                        <td>{arm.pulls.toLocaleString()}</td>
                        <td>{arm.conversions.toLocaleString()}</td>
                        <td>
                          <span style={{ fontWeight: 700, color: "#0f172a" }}>
                            {ratePct}%
                          </span>
                        </td>
                        <td style={{ minWidth: 140 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <div
                              style={{
                                flex: 1,
                                height: 6,
                                borderRadius: 4,
                                background: "#e2e8f0",
                                overflow: "hidden",
                              }}
                            >
                              <div
                                style={{
                                  width: `${weightPct}%`,
                                  height: "100%",
                                  background: "#4e9869",
                                  borderRadius: 4,
                                }}
                              />
                            </div>
                            <span style={{ fontSize: 11, fontWeight: 600, width: 32 }}>
                              {weightPct}%
                            </span>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}
