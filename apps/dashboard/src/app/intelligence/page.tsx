"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

export default function IntelligencePage() {
  const [expandedRequestId, setExpandedRequestId] = useState<string | null>("req_intel_01");
  const { data: health } = useSWR("/v1/friday/health_summary", fetcher);

  const mockRequests = [
    {
      id: "req_intel_01",
      timestamp: "2026-08-28T08:14:00Z",
      task_type: "conversion_drop_diagnosis",
      mode: "DEBATE",
      latency_ms: 18420,
      confidence: 0.94,
      fallback_applied: false,
      decision: "ESCALATE_CHECKOUT_LATENCY_INCIDENT",
      reasoning_chain: [
        "GrowthAgent identified 34.5% conversion drop on /checkout between 07:00 and 08:00 UTC.",
        "ReliabilityAgent corroborated P99 API latency increased from 140ms to 920ms on payment gateway route.",
        "SalesAgent confirmed 8 qualified enterprise buyers abandoned checkout during latency spike.",
        "Adversarial Debate round 3 synthesized consensus: Checkout drop is strictly infrastructure-driven, not pricing fatigue."
      ],
      dissent_log: ["Dissent from AnalyticsAgent resolved: No traffic segment anomaly detected."]
    },
    {
      id: "req_intel_02",
      timestamp: "2026-08-28T08:22:00Z",
      task_type: "lead_qualification_review",
      mode: "REVIEW",
      latency_ms: 7600,
      confidence: 0.89,
      fallback_applied: false,
      decision: "QUALIFIED_ENTERPRISE_LEAD",
      reasoning_chain: [
        "Primary Specialist Agent scored lead at 0.74 based on repeat pricing views and corporate domain.",
        "Critic Agent performed firmographic domain verification confirming 2,000+ employee organization.",
        "Final recommendation: Route immediately to dedicated Enterprise Account Executive."
      ],
      dissent_log: []
    },
    {
      id: "req_intel_03",
      timestamp: "2026-08-28T08:35:00Z",
      task_type: "email_copy_optimization",
      mode: "FAST",
      latency_ms: 2450,
      confidence: 0.96,
      fallback_applied: false,
      decision: "GENERATE_PERSONALIZED_SUBJECT_LINE",
      reasoning_chain: [
        "Single specialist agent drafted ROI calculator callout personalized to CTO role.",
        "Predicted open rate increase: +28%."
      ],
      dissent_log: []
    }
  ];

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">AI Universe Intelligence &amp; Request Audit Log</h1>
          <p className="text-sm text-slate-400 mt-1">Multi-mode deliberation logs (FAST, REVIEW, DEBATE) with expandable reasoning chains.</p>
        </div>
        <span className="text-xs font-mono bg-sky-950 text-sky-400 px-3 py-1 rounded border border-sky-800">
          AI Status: {health?.status || "HEALTHY"}
        </span>
      </div>

      {/* Deliberation Modes Architecture */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl space-y-2">
          <div className="flex justify-between">
            <span className="font-mono text-xs font-bold text-sky-400">FAST MODE</span>
            <span className="text-[10px] text-slate-500">Budget: ~3s</span>
          </div>
          <p className="text-xs text-slate-300">Single specialist quick pass for email copy optimization and routine interventions.</p>
        </div>

        <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl space-y-2">
          <div className="flex justify-between">
            <span className="font-mono text-xs font-bold text-emerald-400">REVIEW MODE</span>
            <span className="text-[10px] text-slate-500">Budget: ~8s</span>
          </div>
          <p className="text-xs text-slate-300">Primary specialist + Critic pass for ambiguous lead scoring and edge cases.</p>
        </div>

        <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl space-y-2">
          <div className="flex justify-between">
            <span className="font-mono text-xs font-bold text-purple-400">DEBATE MODE</span>
            <span className="text-[10px] text-slate-500">Budget: ~20s</span>
          </div>
          <p className="text-xs text-slate-300">Multi-round adversarial deliberation across 3+ agents for strategic diagnosis.</p>
        </div>
      </div>

      {/* AI Universe Consultation Request Logs Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow space-y-4">
        <div className="p-4 border-b border-slate-800 flex justify-between items-center">
          <h2 className="text-sm font-semibold text-slate-200">Recent AI Universe Deliberation Requests</h2>
          <span className="text-xs text-slate-400">Click row to expand reasoning chain</span>
        </div>

        <div className="divide-y divide-slate-800 text-xs">
          {mockRequests.map((req) => (
            <div key={req.id} className="p-4 space-y-3">
              <div
                onClick={() => setExpandedRequestId(expandedRequestId === req.id ? null : req.id)}
                className="flex items-center justify-between cursor-pointer hover:text-sky-300 transition"
              >
                <div className="flex items-center gap-3">
                  <span className="font-mono font-bold text-sky-400">{req.id}</span>
                  <span className="font-semibold text-slate-200">{req.task_type}</span>
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${
                      req.mode === "DEBATE"
                        ? "bg-purple-950 text-purple-400 border-purple-800"
                        : req.mode === "REVIEW"
                        ? "bg-emerald-950 text-emerald-400 border-emerald-800"
                        : "bg-sky-950 text-sky-400 border-sky-800"
                    }`}
                  >
                    {req.mode}
                  </span>
                </div>
                <div className="flex items-center gap-4 text-slate-400">
                  <span>Latency: <strong className="text-slate-200">{req.latency_ms}ms</strong></span>
                  <span>Confidence: <strong className="text-emerald-400">{(req.confidence * 100).toFixed(0)}%</strong></span>
                  <span>{expandedRequestId === req.id ? "▲" : "▼"}</span>
                </div>
              </div>

              {expandedRequestId === req.id && (
                <div className="p-4 bg-slate-950 border border-slate-800 rounded-lg space-y-3 font-mono text-xs">
                  <div>
                    <span className="text-[10px] uppercase text-slate-500 font-bold block mb-1">Synthesized Decision:</span>
                    <span className="text-sky-400 font-bold">{req.decision}</span>
                  </div>

                  <div>
                    <span className="text-[10px] uppercase text-slate-500 font-bold block mb-1">Multi-Agent Reasoning Chain:</span>
                    <ul className="space-y-1 text-slate-300 list-disc list-inside">
                      {req.reasoning_chain.map((step, idx) => (
                        <li key={idx}>{step}</li>
                      ))}
                    </ul>
                  </div>

                  {req.dissent_log.length > 0 && (
                    <div>
                      <span className="text-[10px] uppercase text-amber-500 font-bold block mb-1">Resolved Dissent &amp; Critique:</span>
                      <ul className="space-y-1 text-amber-400/80 list-disc list-inside">
                        {req.dissent_log.map((d, idx) => (
                          <li key={idx}>{d}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
