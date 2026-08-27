"use client";

import React from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

export default function AgentsPage() {
  const { data, error, isLoading } = useSWR("/v1/agents", fetcher);

  const agents = data?.agents || [];

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Specialist Agent Ecosystem</h1>
          <p className="text-sm text-slate-400 mt-1">Autonomous domain specialists executing continuous cognitive reasoning.</p>
        </div>
        <span className="text-xs font-mono bg-purple-950 text-purple-400 px-3 py-1 rounded border border-purple-800">
          4 Agents Active
        </span>
      </div>

      {isLoading ? (
        <div className="p-8 text-center text-sm text-slate-500">Loading specialist agents...</div>
      ) : error ? (
        <div className="p-8 text-center text-sm text-rose-400">Failed to load agent registry.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {agents.map((ag: any) => (
            <div key={ag.id} className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono uppercase bg-slate-800 text-sky-400 px-2 py-0.5 rounded">
                  {ag.domain}
                </span>
                <span className="text-xs flex items-center gap-1.5 text-emerald-400">
                  <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></span>
                  Ready
                </span>
              </div>
              <div>
                <h3 className="text-lg font-bold text-slate-100 font-mono">{ag.id}</h3>
                <p className="text-xs text-slate-400 mt-1">
                  Autonomous operator specializing in {ag.domain} interventions and cognitive loop cycles.
                </p>
              </div>
              <div className="border-t border-slate-800 pt-3">
                <span className="text-xs font-semibold text-slate-400 uppercase">Capabilities</span>
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {ag.capabilities.map((cap: string) => (
                    <span key={cap} className="text-xs font-mono bg-slate-950 text-slate-300 px-2 py-0.5 rounded border border-slate-800">
                      {cap}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
