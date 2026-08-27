"use client";

import React from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

export default function IntelligencePage() {
  const { data: health } = useSWR("/v1/friday/health_summary", fetcher);
  const { data: strategies } = useSWR("/v1/strategies/performance", fetcher);

  const stratList = strategies || [];

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Intelligence & AI Universe Deliberation</h1>
          <p className="text-sm text-slate-400 mt-1">Multi-mode intelligence orchestration (FAST, REVIEW, DEBATE) and strategy promotion.</p>
        </div>
        <span className="text-xs font-mono bg-sky-950 text-sky-400 px-3 py-1 rounded border border-sky-800">
          Status: {health?.status || "HEALTHY"}
        </span>
      </div>

      {/* Deliberation Modes Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl space-y-2">
          <div className="flex justify-between">
            <span className="font-mono text-xs font-bold text-sky-400">FAST MODE</span>
            <span className="text-[10px] text-slate-500">Latency: ~3000ms</span>
          </div>
          <p className="text-xs text-slate-300">Single specialist quick path for routine copy &amp; minor ambiguity.</p>
        </div>

        <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl space-y-2">
          <div className="flex justify-between">
            <span className="font-mono text-xs font-bold text-emerald-400">REVIEW MODE</span>
            <span className="text-[10px] text-slate-500">Latency: ~8000ms</span>
          </div>
          <p className="text-xs text-slate-300">Specialist + Critic double-pass for ambiguous lead qualification.</p>
        </div>

        <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl space-y-2">
          <div className="flex justify-between">
            <span className="font-mono text-xs font-bold text-purple-400">DEBATE MODE</span>
            <span className="text-[10px] text-slate-500">Latency: ~20000ms</span>
          </div>
          <p className="text-xs text-slate-300">Multi-round adversarial deliberation for strategic conversion drop diagnosis.</p>
        </div>
      </div>

      {/* Strategy Performance & Promoted/Demoted Badges */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-4">
        <h2 className="text-sm font-semibold text-slate-200">Closed-Loop Strategy Performance Ratings</h2>
        <table className="w-full text-left text-xs text-slate-300">
          <thead className="bg-slate-950 text-slate-400 border-b border-slate-800">
            <tr>
              <th className="p-3">Strategy Key</th>
              <th className="p-3">Status</th>
              <th className="p-3">Executions</th>
              <th className="p-3">Success Rate</th>
              <th className="p-3">Confidence</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {stratList.length > 0 ? (
              stratList.map((s: any) => (
                <tr key={s.strategy_key}>
                  <td className="p-3 font-mono text-sky-400">{s.strategy_key}</td>
                  <td className="p-3">
                    <span className={`px-2 py-0.5 rounded text-[10px] border ${
                      s.status === "PROVEN"
                        ? "bg-emerald-950 text-emerald-400 border-emerald-800"
                        : s.status === "DEMOTED"
                        ? "bg-rose-950 text-rose-400 border-rose-800"
                        : "bg-slate-800 text-slate-400 border-slate-700"
                    }`}>
                      {s.status}
                    </span>
                  </td>
                  <td className="p-3">{s.total_executions}</td>
                  <td className="p-3 text-emerald-400 font-bold">{s.success_rate_pct}%</td>
                  <td className="p-3">{s.confidence}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={5} className="p-4 text-center text-slate-500 italic">No strategy executions recorded yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
