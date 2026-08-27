"use client";

import React from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

export default function LeadsPage() {
  const { data, error, isLoading } = useSWR("/v1/leads", fetcher);

  const leads = data?.leads || [];

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Predictive Leads Pipeline</h1>
          <p className="text-sm text-slate-400 mt-1">Autonomous ICP scoring, firmographics, and routing.</p>
        </div>
        <span className="text-xs font-mono bg-emerald-950 text-emerald-400 px-3 py-1 rounded border border-emerald-800">
          Total Leads: {data?.total || leads.length}
        </span>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-200">High-Intent Leads</h2>
          <span className="text-xs text-slate-400">Endpoint: /v1/leads</span>
        </div>

        {isLoading ? (
          <div className="p-8 text-center text-sm text-slate-500">Loading leads pipeline...</div>
        ) : error ? (
          <div className="p-8 text-center text-sm text-rose-400">Failed to load leads.</div>
        ) : (
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="bg-slate-950/60 text-xs uppercase text-slate-400 border-b border-slate-800">
              <tr>
                <th className="p-4">Lead ID</th>
                <th className="p-4">ICP Score</th>
                <th className="p-4">Status</th>
                <th className="p-4">Source</th>
                <th className="p-4">Created At</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {leads.length > 0 ? (
                leads.map((l: any) => (
                  <tr key={l.id} className="hover:bg-slate-800/40 transition">
                    <td className="p-4 font-mono font-medium text-sky-400">{l.id}</td>
                    <td className="p-4">
                      <span className="font-bold text-emerald-400">{l.score}</span> / 100
                    </td>
                    <td className="p-4">
                      <span className="px-2 py-0.5 rounded bg-sky-950 text-sky-400 border border-sky-800 text-xs">
                        {l.status}
                      </span>
                    </td>
                    <td className="p-4 text-xs text-slate-400">{l.source || "web"}</td>
                    <td className="p-4 text-xs text-slate-400">
                      {l.created_at ? new Date(l.created_at).toLocaleDateString() : "Today"}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} className="p-8 text-center text-slate-500 text-sm">
                    No leads recorded yet. Telemetry will automatically populate qualified visitors.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
