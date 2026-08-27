"use client";

import React from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

export default function ExperimentsPage() {
  const { data: experiments } = useSWR("/v1/experiments", fetcher);
  const list = experiments || [];

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Experimentation &amp; Dynamic Personalization</h1>
          <p className="text-sm text-slate-400 mt-1">Autonomous A/B testing with two-proportion z-test statistical significance.</p>
        </div>
        <span className="text-xs font-mono bg-indigo-950 text-indigo-400 px-3 py-1 rounded border border-indigo-800">
          Active Experiments: {list.length}
        </span>
      </div>

      <div className="space-y-4">
        {list.map((exp: any) => {
          const stats = exp.statistics || {};
          return (
            <div key={exp.id} className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-4">
              <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
                <div>
                  <h2 className="font-semibold text-slate-100 text-sm">{exp.name}</h2>
                  <p className="text-xs text-slate-400 mt-0.5">{exp.hypothesis}</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-950 text-emerald-400 border border-emerald-800 font-bold">
                    {exp.status}
                  </span>
                  {stats.statistically_significant && (
                    <span className="px-2 py-0.5 rounded text-[10px] bg-purple-950 text-purple-400 border border-purple-800 font-bold">
                      p &lt; 0.05 SIGNIFICANT
                    </span>
                  )}
                </div>
              </div>

              {/* Statistical Metrics Banner */}
              {stats.statistically_significant !== undefined && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 bg-slate-950 p-3 rounded-lg border border-slate-800/60 text-xs">
                  <div>
                    <span className="text-slate-500 block text-[10px]">Confidence Level</span>
                    <span className="font-bold text-slate-200">{stats.confidence_pct}%</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px]">Z-Score</span>
                    <span className="font-mono text-sky-400 font-bold">{stats.z_score}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px]">Relative Lift</span>
                    <span className="font-bold text-emerald-400">+{stats.relative_lift_pct}%</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px]">p-value</span>
                    <span className="font-mono text-purple-400">{stats.p_value}</span>
                  </div>
                </div>
              )}

              {/* Variants Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {exp.variants?.map((v: any) => {
                  const cr = v.visitors_count > 0 ? ((v.conversions_count / v.visitors_count) * 100).toFixed(2) : "0.00";
                  return (
                    <div key={v.id} className="p-4 bg-slate-950 border border-slate-800 rounded-lg space-y-2">
                      <div className="flex justify-between items-center">
                        <span className="font-mono text-xs font-semibold text-sky-400">{v.name}</span>
                        <span className="text-[11px] text-slate-400">Weight: {v.weight * 100}%</span>
                      </div>
                      <div className="flex justify-between text-xs text-slate-300">
                        <span>Visitors: {v.visitors_count}</span>
                        <span>Conversions: {v.conversions_count}</span>
                        <span className="text-emerald-400 font-bold">CR: {cr}%</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
