"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

export default function LeadsPage() {
  const [selectedLeadId, setSelectedLeadId] = useState<string | null>(null);
  const { data, error, isLoading } = useSWR("/v1/leads", fetcher);
  const { data: scoreData } = useSWR(selectedLeadId ? `/v1/leads/${selectedLeadId}/score` : null, fetcher);

  const leads = data?.leads || [];

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Predictive Leads Pipeline</h1>
          <p className="text-sm text-slate-400 mt-1">Autonomous ICP scoring, firmographics, and historical score trajectories.</p>
        </div>
        <span className="text-xs font-mono bg-emerald-950 text-emerald-400 px-3 py-1 rounded border border-emerald-800">
          Total Leads: {data?.total || leads.length}
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow">
          <div className="p-4 border-b border-slate-800 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-200">High-Intent Leads Queue</h2>
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
                  <th className="p-4">Lead Score</th>
                  <th className="p-4">Status</th>
                  <th className="p-4">Source</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {leads.length > 0 ? (
                  leads.map((l: any) => (
                    <tr
                      key={l.id}
                      onClick={() => setSelectedLeadId(l.id)}
                      className={`cursor-pointer transition hover:bg-slate-800/50 ${selectedLeadId === l.id ? "bg-sky-950/40" : ""}`}
                    >
                      <td className="p-4 font-mono font-medium text-sky-400">{l.id}</td>
                      <td className="p-4">
                        <span className="font-bold text-emerald-400">{l.score}</span>
                      </td>
                      <td className="p-4">
                        <span className="px-2 py-0.5 rounded bg-sky-950 text-sky-400 border border-sky-800 text-xs">
                          {l.status}
                        </span>
                      </td>
                      <td className="p-4 text-xs text-slate-400">{l.source || "web"}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} className="p-8 text-center text-slate-500 text-sm">
                      No leads recorded yet. Telemetry will automatically populate qualified visitors.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>

        {/* Lead Score Breakdown & Trajectory */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-4">
          <h2 className="text-sm font-semibold text-slate-200 border-b border-slate-800 pb-2">
            Score Breakdown & Trajectory
          </h2>
          {selectedLeadId && scoreData ? (
            <div className="space-y-4 text-xs">
              <div>
                <span className="text-slate-500">Lead ID:</span>
                <p className="font-mono text-sky-400">{selectedLeadId}</p>
              </div>
              <div className="p-3 bg-slate-950 rounded border border-slate-800 space-y-1">
                <div className="flex justify-between">
                  <span className="text-slate-400">Current Score:</span>
                  <span className="text-emerald-400 font-bold">{scoreData.current_score}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Status:</span>
                  <span className="text-sky-400">{scoreData.status}</span>
                </div>
              </div>
              <div>
                <span className="text-slate-400 font-semibold block mb-1">Score History:</span>
                <div className="space-y-1 max-h-48 overflow-y-auto">
                  {scoreData.score_history?.map((h: any) => (
                    <div key={h.score_id} className="p-2 bg-slate-950 rounded border border-slate-800 flex justify-between text-xs">
                      <span>Score: <b className="text-emerald-400">{h.total_score}</b></span>
                      <span className="text-slate-500">{new Date(h.created_at).toLocaleTimeString()}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <p className="text-slate-500 text-xs italic">Select a lead to inspect score model breakdown and history.</p>
          )}
        </div>
      </div>
    </div>
  );
}
