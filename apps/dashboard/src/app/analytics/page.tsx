"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import axios from "axios";

export default function AnalyticsPage() {
  const [nlQuery, setNlQuery] = useState("What's the top traffic source by conversion rate?");
  const [nlResult, setNlResult] = useState<any>(null);
  const [isQuerying, setIsQuerying] = useState(false);

  const handleAsk = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!nlQuery.trim()) return;
    setIsQuerying(true);
    try {
      const res = await axios.post("http://localhost:8000/v1/analytics/query", { question: nlQuery });
      setNlResult(res.data);
    } catch {
      setNlResult({
        answer_summary: "Unable to reach the analytics query endpoint. Please ensure the CORTEX API is running on localhost:8000.",
        sql_translation: "SELECT * FROM events LIMIT 10;",
        data: []
      });
    } finally {
      setIsQuerying(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Advanced Analytics &amp; Natural Language Querying</h1>
          <p className="text-sm text-slate-400 mt-1">Cohort retention curves, multi-touch attribution, and conversational SQL engine.</p>
        </div>
        <span className="text-xs font-mono bg-sky-950 text-sky-400 px-3 py-1 rounded border border-sky-800">
          NL Query Engine Active
        </span>
      </div>

      {/* Natural Language Query Bar */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-4">
        <h2 className="text-sm font-semibold text-slate-200">Ask Operations Intelligence (Natural Language)</h2>
        <form onSubmit={handleAsk} className="flex gap-3">
          <input
            type="text"
            value={nlQuery}
            onChange={(e) => setNlQuery(e.target.value)}
            placeholder="e.g. How many visitors from Google Ads converted this week?"
            className="flex-1 bg-slate-950 border border-slate-800 rounded-lg px-4 py-2 text-sm text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
          />
          <button
            type="submit"
            disabled={isQuerying}
            className="px-5 py-2 bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold rounded-lg transition disabled:opacity-50"
          >
            {isQuerying ? "Analyzing..." : "Ask CORTEX"}
          </button>
        </form>

        {nlResult && (
          <div className="p-4 bg-slate-950 rounded-lg border border-slate-800/80 space-y-3">
            <div>
              <span className="text-slate-500 block text-[10px] uppercase font-semibold">Answer Summary:</span>
              <p className="mt-1 text-sm text-slate-100 font-medium">{nlResult.answer_summary}</p>
            </div>

            <div>
              <span className="text-slate-500 block text-[10px] uppercase font-semibold">Generated SQL Translation:</span>
              <pre className="mt-1 p-2 bg-slate-900 rounded text-xs font-mono text-sky-400 overflow-x-auto border border-slate-800">
                {nlResult.sql_translation}
              </pre>
            </div>

            {nlResult.data && nlResult.data.length > 0 && (
              <div>
                <span className="text-slate-500 block text-[10px] uppercase font-semibold mb-2">Structured Result Set:</span>
                <table className="w-full text-left text-xs text-slate-300">
                  <thead className="bg-slate-900/60 uppercase text-[10px] text-slate-400">
                    <tr>
                      <th className="p-2">Dimension / Source</th>
                      <th className="p-2">Visitors</th>
                      <th className="p-2">Conversion Rate</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {nlResult.data.map((row: any, idx: number) => (
                      <tr key={idx}>
                        <td className="p-2 font-mono text-sky-400">{row.source || row.dimension || "Organic"}</td>
                        <td className="p-2">{row.visitors || row.metric || 100}</td>
                        <td className="p-2 text-emerald-400 font-semibold">{row.conversion_rate_pct || 10.0}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Multi-Touch Attribution & Cohort Retention Overview */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-3">
          <h3 className="text-sm font-semibold text-slate-200 border-b border-slate-800 pb-2">
            Multi-Touch Revenue Attribution Models
          </h3>
          <div className="space-y-2 text-xs text-slate-300">
            <div className="flex justify-between p-2 bg-slate-950 rounded">
              <span>Google Ads (CPC)</span>
              <span className="font-bold text-emerald-400">$18,450 (Time-Decay 7d)</span>
            </div>
            <div className="flex justify-between p-2 bg-slate-950 rounded">
              <span>LinkedIn Social</span>
              <span className="font-bold text-emerald-400">$14,200 (Linear Share)</span>
            </div>
            <div className="flex justify-between p-2 bg-slate-950 rounded">
              <span>Direct Enterprise Traffic</span>
              <span className="font-bold text-emerald-400">$32,800 (First-Touch)</span>
            </div>
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-3">
          <h3 className="text-sm font-semibold text-slate-200 border-b border-slate-800 pb-2">
            Cohort Retention Curves (Week-over-Week)
          </h3>
          <div className="space-y-2 text-xs text-slate-300">
            <div className="flex justify-between p-2 bg-slate-950 rounded">
              <span>Cohort Week 2026-W34</span>
              <span className="text-sky-400 font-mono">100% W0 &rarr; 42.8% W1</span>
            </div>
            <div className="flex justify-between p-2 bg-slate-950 rounded">
              <span>Cohort Week 2026-W33</span>
              <span className="text-sky-400 font-mono">100% W0 &rarr; 38.5% W1 &rarr; 29.1% W2</span>
            </div>
          </div>
        </div>
      </div>

      {/* IntelX Competitive & Market Intelligence Section */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-4">
        <div className="flex justify-between items-center border-b border-slate-800 pb-2">
          <div>
            <h2 className="text-sm font-semibold text-slate-200">IntelX Competitive Intelligence &amp; Market Position</h2>
            <p className="text-xs text-slate-400">Real-time competitor battlecards, feature gap analysis, and market signal tracking.</p>
          </div>
          <span className="text-xs font-mono bg-purple-950 text-purple-400 px-3 py-1 rounded border border-purple-800 font-bold">
            IntelX Research Active
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          {/* Competitor Battlecards */}
          <div className="p-4 bg-slate-950 border border-slate-800 rounded-lg space-y-3">
            <span className="text-[10px] uppercase font-bold text-slate-400 block">Competitor Battlecard: Datadog / Dynatrace</span>
            <div className="space-y-2">
              <div className="p-3 bg-slate-900 border border-slate-800 rounded space-y-1">
                <span className="font-bold text-slate-200 block">Identified Feature Gaps:</span>
                <ul className="list-disc list-inside text-[11px] text-slate-400 space-y-0.5">
                  <li>No autonomous real-time website personalization</li>
                  <li>Lacks 10-phase closed-loop agentic deliberation</li>
                  <li>Steep per-host and per-seat overage pricing model</li>
                </ul>
              </div>
              <div className="p-3 bg-sky-950/30 border border-sky-800/60 rounded space-y-1">
                <span className="font-bold text-sky-400 block text-[11px]">Recommended Sales Battlecard:</span>
                <p className="text-slate-300 text-[11px]">
                  Position Cortex's sub-100ms real-time autonomous cognitive loops and zero per-seat tax as a 60% TCO savings over legacy APM.
                </p>
              </div>
            </div>
          </div>

          {/* Market Signals Timeline */}
          <div className="p-4 bg-slate-950 border border-slate-800 rounded-lg space-y-3">
            <span className="text-[10px] uppercase font-bold text-slate-400 block">Market Signals &amp; Regulatory Shifts</span>
            <div className="space-y-2">
              <div className="p-3 bg-slate-900 border border-slate-800 rounded space-y-1">
                <div className="flex justify-between items-center">
                  <span className="font-bold text-slate-200">Surge in Autonomous Agentic Operations</span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-950 text-purple-400 border border-purple-800">STRATEGIC</span>
                </div>
                <p className="text-slate-400 text-[11px]">Enterprises rapidly moving from passive APM dashboards to active closed-loop intervention.</p>
                <span className="text-[10px] text-sky-400 block font-mono mt-1">Trending: Agentic Workflows, Real-Time DevSecOps</span>
              </div>
              <div className="p-3 bg-slate-900 border border-slate-800 rounded space-y-1">
                <div className="flex justify-between items-center">
                  <span className="font-bold text-slate-200">Heightened Data Privacy &amp; Erasure Audits</span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-800">HIGH</span>
                </div>
                <p className="text-slate-400 text-[11px]">EU &amp; US compliance teams mandating verified client-side PII masking and automated GDPR Art. 17 erasure.</p>
                <span className="text-[10px] text-sky-400 block font-mono mt-1">Trending: Client PII Redaction, Tamper-Evident Audit</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Futuris Predictive Web Operations Section */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-4">
        <div className="flex justify-between items-center border-b border-slate-800 pb-2">
          <div>
            <h2 className="text-sm font-semibold text-slate-200">Futuris Predictive Web Operations &amp; Capacity Forecasting</h2>
            <p className="text-xs text-slate-400">24-hour traffic volume predictions, capacity breach alerts, and conversion bottleneck forecasting.</p>
          </div>
          <span className="text-xs font-mono bg-amber-950 text-amber-400 px-3 py-1 rounded border border-amber-800 font-bold">
            Predictive AI Active (95% CI)
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          {/* Traffic Forecast & Capacity */}
          <div className="p-4 bg-slate-950 border border-slate-800 rounded-lg space-y-2">
            <div className="flex justify-between items-center">
              <span className="text-[10px] uppercase font-bold text-slate-400">Traffic Horizon (24h)</span>
              <span className="text-rose-400 font-mono font-bold text-[10px]">PEAK: 504 RPS</span>
            </div>
            <div className="p-2.5 bg-slate-900 border border-slate-800 rounded space-y-1">
              <div className="flex justify-between">
                <span>Threshold:</span>
                <span className="font-mono text-slate-300">400 RPS</span>
              </div>
              <div className="flex justify-between">
                <span>Capacity Status:</span>
                <span className="font-mono text-rose-400 font-bold">EXCEEDS CAPACITY</span>
              </div>
              <span className="text-[10px] text-amber-400 block font-mono mt-1">Action: Auto-scale replicas 3 &rarr; 7</span>
            </div>
          </div>

          {/* Conversion Trend Forecast */}
          <div className="p-4 bg-slate-950 border border-slate-800 rounded-lg space-y-2">
            <div className="flex justify-between items-center">
              <span className="text-[10px] uppercase font-bold text-slate-400">Conversion Trajectory</span>
              <span className="text-amber-400 font-mono font-bold text-[10px]">78% DROP RISK</span>
            </div>
            <div className="p-2.5 bg-slate-900 border border-slate-800 rounded space-y-1">
              <div className="flex justify-between">
                <span>Current CVR:</span>
                <span className="font-mono text-slate-300">3.8%</span>
              </div>
              <div className="flex justify-between">
                <span>Predicted CVR:</span>
                <span className="font-mono text-rose-400">2.1% (Dropping)</span>
              </div>
              <span className="text-[10px] text-sky-400 block font-mono mt-1">Bottleneck: /checkout/payment</span>
            </div>
          </div>

          {/* Predictive Churn Risk */}
          <div className="p-4 bg-slate-950 border border-slate-800 rounded-lg space-y-2">
            <div className="flex justify-between items-center">
              <span className="text-[10px] uppercase font-bold text-slate-400">At-Risk Segment Forecast</span>
              <span className="text-rose-400 font-mono font-bold text-[10px]">18 ACCOUNTS</span>
            </div>
            <div className="p-2.5 bg-slate-900 border border-slate-800 rounded space-y-1">
              <div className="flex justify-between">
                <span>Segment:</span>
                <span className="text-slate-300 font-bold">Mid-Market Expiring</span>
              </div>
              <div className="flex justify-between">
                <span>Churn Rate:</span>
                <span className="font-mono text-rose-400">42.5%</span>
              </div>
              <span className="text-[10px] text-emerald-400 block font-mono mt-1">Preemptive: Retention Workflow</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
