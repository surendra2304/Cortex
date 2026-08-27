"use client";

import React from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

export default function VisitorsPage() {
  const { data, error, isLoading } = useSWR("/v1/visitors/vis_123", fetcher);

  const visitor = data?.visitor;

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Visitors & Identity</h1>
          <p className="text-sm text-slate-400 mt-1">Real-time visitor telemetry and stitched profiles.</p>
        </div>
        <span className="text-xs font-mono bg-sky-950 text-sky-400 px-3 py-1 rounded border border-sky-800">
          Live Session Sync
        </span>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-200">Active Visitors Stream</h2>
          <span className="text-xs text-slate-400">Endpoint: /v1/visitors/:id</span>
        </div>

        {isLoading ? (
          <div className="p-8 text-center text-sm text-slate-500">Loading live visitor stream...</div>
        ) : error ? (
          <div className="p-8 text-center text-sm text-rose-400">Failed to load visitor stream.</div>
        ) : (
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="bg-slate-950/60 text-xs uppercase text-slate-400 border-b border-slate-800">
              <tr>
                <th className="p-4">Visitor ID</th>
                <th className="p-4">Tenant / Site</th>
                <th className="p-4">Resolved Profile</th>
                <th className="p-4">Attributes</th>
                <th className="p-4">Last Seen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              <tr className="hover:bg-slate-800/40 transition">
                <td className="p-4 font-mono font-medium text-sky-400">{visitor?.id || "vis_123"}</td>
                <td className="p-4">{visitor?.tenant_id} / {visitor?.site_id}</td>
                <td className="p-4">
                  {visitor?.profile ? (
                    <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 text-xs">
                      {visitor.profile.primary_email || "Identified Profile"}
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-400 text-xs">
                      Pseudonymous
                    </span>
                  )}
                </td>
                <td className="p-4 font-mono text-xs text-slate-400">
                  {JSON.stringify(visitor?.attributes || {})}
                </td>
                <td className="p-4 text-xs text-slate-400">
                  {visitor?.last_seen_at ? new Date(visitor.last_seen_at).toLocaleTimeString() : "Just now"}
                </td>
              </tr>
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
