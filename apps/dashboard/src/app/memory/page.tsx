"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

export default function MemoryPage() {
  const [filterScope, setFilterScope] = useState("all");
  const { data: stratPerformance } = useSWR("/v1/strategies/performance", fetcher);

  const mockStrategies = [
    {
      strategy_name: "agent_growth:pricing_cta_banner",
      action_type: "banner_injection",
      total_executions: 40,
      successes: 34,
      success_rate: 0.85,
      status: "PROVEN",
      avg_conversion_lift: "+18.4%",
      learning_curve: [0.65, 0.70, 0.76, 0.82, 0.85]
    },
    {
      strategy_name: "agent_sales:enterprise_routing",
      action_type: "crm_tool",
      total_executions: 28,
      successes: 22,
      success_rate: 0.78,
      status: "PROVEN",
      avg_conversion_lift: "+14.2%",
      learning_curve: [0.60, 0.68, 0.72, 0.75, 0.78]
    },
    {
      strategy_name: "agent_support:automated_checkout_ticket",
      action_type: "ticketing_tool",
      total_executions: 15,
      successes: 10,
      success_rate: 0.66,
      status: "PROVEN",
      avg_conversion_lift: "+9.5%",
      learning_curve: [0.50, 0.58, 0.62, 0.64, 0.66]
    },
    {
      strategy_name: "agent_growth:cold_exit_modal",
      action_type: "modal_popup",
      total_executions: 18,
      successes: 4,
      success_rate: 0.22,
      status: "DEMOTED",
      avg_conversion_lift: "-4.2%",
      learning_curve: [0.40, 0.32, 0.28, 0.25, 0.22]
    }
  ];

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Closed-Loop Strategy Learning &amp; Performance</h1>
          <p className="text-sm text-slate-400 mt-1">
            48h outcome measurement, automated strategy promotion (&gt;60%), and auto-demotion (&lt;30%).
          </p>
        </div>
        <span className="text-xs font-mono bg-purple-950 text-purple-400 px-3 py-1 rounded border border-purple-800">
          Reinforcement Learning Active
        </span>
      </div>

      {/* Strategy Performance Summary Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow">
        <div className="p-4 border-b border-slate-800 flex justify-between items-center">
          <h2 className="text-sm font-semibold text-slate-200">Autonomous Strategy Performance Matrix</h2>
          <span className="text-xs text-slate-400">Sorted by Success Rate</span>
        </div>

        <table className="w-full text-left text-xs text-slate-300">
          <thead className="bg-slate-950 text-slate-400 border-b border-slate-800">
            <tr>
              <th className="p-4">Strategy Key</th>
              <th className="p-4">Action Tool</th>
              <th className="p-4">Executions ($N$)</th>
              <th className="p-4">Success Rate</th>
              <th className="p-4">Avg Impact</th>
              <th className="p-4">Learning Trend</th>
              <th className="p-4">Promotion Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {mockStrategies.map((strat) => (
              <tr key={strat.strategy_name} className="hover:bg-slate-800/50 transition font-mono">
                <td className="p-4 font-bold text-sky-400">{strat.strategy_name}</td>
                <td className="p-4 text-slate-300">{strat.action_type}</td>
                <td className="p-4">{strat.total_executions}</td>
                <td className="p-4 font-bold text-emerald-400">{(strat.success_rate * 100).toFixed(0)}%</td>
                <td className="p-4 text-slate-200">{strat.avg_conversion_lift}</td>
                <td className="p-4 text-purple-400">
                  {strat.learning_curve.map((v) => `${(v * 100).toFixed(0)}%`).join(" → ")}
                </td>
                <td className="p-4">
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                      strat.status === "PROVEN"
                        ? "bg-emerald-950 text-emerald-400 border-emerald-800"
                        : "bg-rose-950 text-rose-400 border-rose-800"
                    }`}
                  >
                    {strat.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Learning Invariant Explanation */}
      <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-400 space-y-2">
        <span className="font-bold text-slate-200 block text-xs">Closed-Loop Learning Invariants:</span>
        <ul className="space-y-1 list-disc list-inside">
          <li><strong className="text-emerald-400">Auto-Promote (PROVEN):</strong> Interventions maintaining &gt;60% success rate over $N \ge 20$ executions are prioritized by specialist agents.</li>
          <li><strong className="text-rose-400">Auto-Demote (DEMOTED):</strong> Interventions falling below 30% success rate over $N \ge 10$ executions are automatically suppressed from future proposal candidates.</li>
        </ul>
      </div>
    </div>
  );
}
