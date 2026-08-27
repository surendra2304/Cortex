"use client";

import React from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

export default function MemoryPage() {
  const { data, error, isLoading } = useSWR("/v1/memory/strategy/agent_growth:banner_injection", fetcher);

  const entries = data?.entries || [];

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Cognitive Memory & Strategy Learnings</h1>
          <p className="text-sm text-slate-400 mt-1">Outcome memory store and strategy performance learnings per operational cycle.</p>
        </div>
        <span className="text-xs font-mono bg-purple-950 text-purple-400 px-3 py-1 rounded border border-purple-800">
          Trust Classified Memory
        </span>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-4">
        <h2 className="text-sm font-semibold text-slate-200">Recent Strategy Outcome Memories</h2>
        <span className="text-xs text-slate-400 block">Scope: strategy | Scope ID: agent_growth:banner_injection</span>

        {isLoading ? (
          <div className="p-8 text-center text-sm text-slate-500">Loading strategy outcome memories...</div>
        ) : error ? (
          <div className="p-8 text-center text-sm text-rose-400">Failed to load memory store.</div>
        ) : (
          <div className="space-y-3">
            {entries.length > 0 ? (
              entries.map((m: any) => (
                <div key={m.id} className="p-4 bg-slate-950 rounded-lg border border-slate-800 space-y-2">
                  <div className="flex justify-between items-center text-xs">
                    <span className="font-mono text-purple-400 font-semibold">{m.key}</span>
                    <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px]">
                      {m.trust_label}
                    </span>
                  </div>
                  <pre className="text-xs font-mono text-slate-300 bg-slate-900 p-3 rounded overflow-x-auto border border-slate-800">
                    {JSON.stringify(m.content, null, 2)}
                  </pre>
                  <div className="text-[11px] text-slate-500 flex justify-between">
                    <span>Source: {m.source}</span>
                    <span>{new Date(m.created_at).toLocaleString()}</span>
                  </div>
                </div>
              ))
            ) : (
              <p className="text-slate-500 text-xs italic">No strategy outcome memories recorded yet. They will be generated during the Learn phase of the cognitive loop.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
