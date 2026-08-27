"use client";

import React from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

export default function FunnelsPage() {
  const { data, error, isLoading } = useSWR("/v1/analytics/funnel", fetcher);
  const { data: cohortData } = useSWR("/v1/analytics/cohorts", fetcher);

  const steps = data?.funnel_steps || [];
  const anomalies = data?.anomalies_detected || [];
  const cohorts = cohortData || [];

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Funnels & Cohort Retention</h1>
          <p className="text-sm text-slate-400 mt-1">Multi-step conversion rates, drop-off heatmaps, and weekly retention cohorts.</p>
        </div>
        <span className="text-xs font-mono bg-sky-950 text-sky-400 px-3 py-1 rounded border border-sky-800">
          Conversion Rate: {data?.overall_conversion_pct || 0}%
        </span>
      </div>

      {/* Anomalies Alert */}
      {anomalies.length > 0 && (
        <div className="p-4 bg-rose-950/40 border border-rose-800 rounded-xl space-y-1">
          <h3 className="text-sm font-semibold text-rose-400">⚠️ Conversion Anomaly Detected (&gt;2σ Deviation)</h3>
          {anomalies.map((a: any, idx: number) => (
            <p key={idx} className="text-xs text-rose-300">{a.message}</p>
          ))}
        </div>
      )}

      {/* Funnel Steps */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-4">
        <h2 className="text-sm font-semibold text-slate-200">Main Conversion Funnel Steps</h2>
        {isLoading ? (
          <div className="p-8 text-center text-sm text-slate-500">Calculating funnel telemetry...</div>
        ) : error ? (
          <div className="p-8 text-center text-sm text-rose-400">Failed to load funnel analytics.</div>
        ) : (
          <div className="space-y-3">
            {steps.map((s: any, idx: number) => (
              <div key={idx} className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="font-mono text-slate-300">{s.step}</span>
                  <span className="text-slate-400">
                    {s.visitors_count} visitors ({s.step_conversion_pct}% step, {s.drop_off_pct}% drop-off)
                  </span>
                </div>
                <div className="w-full h-3 bg-slate-950 rounded-full overflow-hidden border border-slate-800">
                  <div
                    className="h-full bg-gradient-to-r from-sky-500 to-emerald-400 rounded-full"
                    style={{ width: `${s.step_conversion_pct || 0}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Cohorts */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-4">
        <h2 className="text-sm font-semibold text-slate-200">Weekly Retention Cohorts</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="bg-slate-950 text-slate-400 border-b border-slate-800">
              <tr>
                <th className="p-3">Cohort Week</th>
                <th className="p-3">Size</th>
                <th className="p-3">Week 0 Retention</th>
                <th className="p-3">Week 1 Retention</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {cohorts.length > 0 ? (
                cohorts.map((c: any, idx: number) => (
                  <tr key={idx}>
                    <td className="p-3 font-mono text-sky-400">{c.cohort_week}</td>
                    <td className="p-3">{c.cohort_size} visitors</td>
                    <td className="p-3 text-emerald-400 font-bold">{c.week_0_retention_pct}%</td>
                    <td className="p-3 text-sky-400">{c.week_1_retention_pct}%</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={4} className="p-4 text-center text-slate-500 italic">No cohort telemetry recorded yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
