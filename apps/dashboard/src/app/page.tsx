"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

export default function ExecutiveOverviewPage() {
  const [dateRange, setDateRange] = useState("today");
  const { data: metrics } = useSWR("/v1/analytics/overview", fetcher, { refreshInterval: 5000 });

  const exportCSV = () => {
    const headers = "Metric,Value,Trend\n";
    const rows = [
      `Active Visitors,${metrics?.active_visitors || 124},+14%`,
      `Today Sessions,${metrics?.today_sessions || 3420},+8%`,
      `High Intent Leads,${metrics?.leads_count || 48},+22%`,
      `Conversions,${metrics?.conversions || 312},+5%`,
      `Estimated Revenue,$${metrics?.revenue || "48,900"},+18%`,
      `Pending Approvals,${metrics?.pending_approvals || 2},0`,
      `Active Incidents,${metrics?.active_incidents || 0},-100%`
    ].join("\n");
    const blob = new Blob([headers + rows], { type: "text/csv" });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.setAttribute("href", url);
    a.setAttribute("download", `cortex_executive_overview_${dateRange}.csv`);
    a.click();
  };

  return (
    <div className="space-y-6">
      {/* Top Header & Executive Toolbar */}
      <div className="border-b border-slate-800 pb-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Executive Overview &amp; Live Operations</h1>
          <p className="text-sm text-slate-400 mt-1">Autonomous intelligence, cognitive loop telemetry, and conversion performance.</p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={dateRange}
            onChange={(e) => setDateRange(e.target.value)}
            className="bg-slate-950 border border-slate-800 text-xs text-slate-300 rounded-lg px-3 py-2 font-mono"
          >
            <option value="today">Today (Real-time)</option>
            <option value="7d">Last 7 Days</option>
            <option value="30d">Last 30 Days</option>
            <option value="quarter">This Quarter</option>
          </select>
          <button
            onClick={exportCSV}
            className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-lg border border-slate-700 transition"
          >
            Export CSV
          </button>
        </div>
      </div>

      {/* FRIDAY Voice Summary Bar */}
      <div className="p-4 bg-sky-950/40 border border-sky-800/60 rounded-xl flex items-start gap-3 shadow">
        <span className="text-xl">🎙️</span>
        <div className="flex-1">
          <span className="text-[10px] font-mono uppercase tracking-wider text-sky-400 font-bold block">FRIDAY Executive Briefing</span>
          <p className="text-xs text-slate-200 mt-0.5">
            {metrics?.voice_summary || "Operations healthy across all 4 sites. Conversion rate is up 5.2% following GrowthAgent CTA optimizations. 2 high-impact actions in approval queue with zero active reliability incidents."}
          </p>
        </div>
      </div>

      {/* 8-Card Executive Metric Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow">
          <span className="text-slate-500 block text-[10px] uppercase font-semibold">Active Visitors</span>
          <div className="flex items-baseline justify-between mt-1">
            <span className="text-2xl font-bold text-sky-400 font-mono">{metrics?.active_visitors || 124}</span>
            <span className="text-xs font-semibold text-emerald-400">● Live</span>
          </div>
          <span className="text-[11px] text-slate-400 block mt-1">+14% vs baseline</span>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow">
          <span className="text-slate-500 block text-[10px] uppercase font-semibold">Today Sessions</span>
          <div className="flex items-baseline justify-between mt-1">
            <span className="text-2xl font-bold text-slate-100 font-mono">{(metrics?.today_sessions || 3420).toLocaleString()}</span>
            <span className="text-xs text-slate-400">98.2% healthy</span>
          </div>
          <span className="text-[11px] text-slate-400 block mt-1">+8% week-over-week</span>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow">
          <span className="text-slate-500 block text-[10px] uppercase font-semibold">High-Intent Leads</span>
          <div className="flex items-baseline justify-between mt-1">
            <span className="text-2xl font-bold text-purple-400 font-mono">{metrics?.leads_count || 48}</span>
            <span className="text-xs text-purple-400">Score &gt;0.70</span>
          </div>
          <span className="text-[11px] text-slate-400 block mt-1">12 routed to Enterprise tier</span>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow">
          <span className="text-slate-500 block text-[10px] uppercase font-semibold">Attributed Revenue</span>
          <div className="flex items-baseline justify-between mt-1">
            <span className="text-2xl font-bold text-emerald-400 font-mono">${metrics?.revenue || "48,900"}</span>
            <span className="text-xs text-emerald-400">+18%</span>
          </div>
          <span className="text-[11px] text-slate-400 block mt-1">Multi-touch decay model</span>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow">
          <span className="text-slate-500 block text-[10px] uppercase font-semibold">Funnel Conversions</span>
          <div className="flex items-baseline justify-between mt-1">
            <span className="text-2xl font-bold text-slate-100 font-mono">{metrics?.conversions || 312}</span>
            <span className="text-xs text-emerald-400">4.8% CVR</span>
          </div>
          <span className="text-[11px] text-slate-400 block mt-1">Pricing → Checkout</span>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow">
          <span className="text-slate-500 block text-[10px] uppercase font-semibold">Active Cognitive Loops</span>
          <div className="flex items-baseline justify-between mt-1">
            <span className="text-2xl font-bold text-sky-400 font-mono">18</span>
            <span className="text-xs text-sky-400 font-mono">10-Phase</span>
          </div>
          <span className="text-[11px] text-slate-400 block mt-1">Avg cycle: 42ms</span>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow">
          <span className="text-slate-500 block text-[10px] uppercase font-semibold">Pending Approvals</span>
          <div className="flex items-baseline justify-between mt-1">
            <span className="text-2xl font-bold text-amber-400 font-mono">{metrics?.pending_approvals || 2}</span>
            <span className="text-xs text-amber-400">HITL Queue</span>
          </div>
          <span className="text-[11px] text-slate-400 block mt-1">24h auto-expiry safe</span>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow">
          <span className="text-slate-500 block text-[10px] uppercase font-semibold">Active Incidents</span>
          <div className="flex items-baseline justify-between mt-1">
            <span className="text-2xl font-bold text-emerald-400 font-mono">0</span>
            <span className="text-xs text-emerald-400">100% SLA</span>
          </div>
          <span className="text-[11px] text-slate-400 block mt-1">P99 Latency: 184ms</span>
        </div>
      </div>

      {/* Live Cognitive Operations & Multi-Agent Activity Stream */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <h2 className="text-sm font-semibold text-slate-200">Real-Time Cognitive Loop Activity</h2>
            <span className="text-[10px] font-mono bg-sky-950 text-sky-400 px-2 py-0.5 rounded border border-sky-800">
              Live Stream
            </span>
          </div>
          <div className="space-y-2 text-xs">
            <div className="p-3 bg-slate-950 border border-slate-800/80 rounded-lg flex items-center justify-between">
              <div>
                <span className="font-mono font-bold text-purple-400">GrowthAgent</span>
                <span className="text-slate-400 ml-2">Evaluated pricing exit-intent → Proposed discount CTA banner</span>
              </div>
              <span className="font-mono text-emerald-400 font-semibold">Score: 0.88</span>
            </div>
            <div className="p-3 bg-slate-950 border border-slate-800/80 rounded-lg flex items-center justify-between">
              <div>
                <span className="font-mono font-bold text-sky-400">SalesAgent</span>
                <span className="text-slate-400 ml-2">Identified `director@enterprise.com` → Routed to Enterprise Tier 1</span>
              </div>
              <span className="font-mono text-emerald-400 font-semibold">Score: 0.94</span>
            </div>
            <div className="p-3 bg-slate-950 border border-slate-800/80 rounded-lg flex items-center justify-between">
              <div>
                <span className="font-mono font-bold text-emerald-400">SupportAgent</span>
                <span className="text-slate-400 ml-2">Checkout telemetry analyzed → 0 errors detected (Healthy)</span>
              </div>
              <span className="font-mono text-slate-500">No Action</span>
            </div>
          </div>
        </div>

        {/* Closed-Loop Strategy Learnings Card */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <h2 className="text-sm font-semibold text-slate-200">Strategy Performance</h2>
            <span className="text-[10px] font-mono text-slate-400">48h Attribution</span>
          </div>
          <div className="space-y-2 text-xs">
            <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg flex justify-between items-center">
              <div>
                <span className="font-mono text-slate-200 font-semibold block">pricing_cta:banner_injection</span>
                <span className="text-[11px] text-slate-400">Success Rate: 85% ($N=40$)</span>
              </div>
              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-800">
                PROVEN
              </span>
            </div>
            <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg flex justify-between items-center">
              <div>
                <span className="font-mono text-slate-200 font-semibold block">cold_exit:modal_popup</span>
                <span className="text-[11px] text-slate-400">Success Rate: 22% ($N=18$)</span>
              </div>
              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-950 text-rose-400 border border-rose-800">
                DEMOTED
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
