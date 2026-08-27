"use client";

import React from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

export default function ConnectorsPage() {
  const { data: connectors, error } = useSWR("/v1/connectors", fetcher);
  const list = connectors || [];

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Connector Registry &amp; Integration Ecosystem</h1>
          <p className="text-sm text-slate-400 mt-1">Universal Tool Contract integrations, live health monitors, and circuit breakers.</p>
        </div>
        <span className="text-xs font-mono bg-emerald-950 text-emerald-400 px-3 py-1 rounded border border-emerald-800">
          Active Integrations: {list.length}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {list.map((c: any) => (
          <div key={c.id} className="p-5 bg-slate-900 border border-slate-800 rounded-xl space-y-3 shadow">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-slate-200 text-sm">{c.name}</span>
              <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-950 text-emerald-400 border border-emerald-800 font-bold">
                {c.status}
              </span>
            </div>

            <div className="space-y-1 text-xs">
              <div className="flex justify-between text-slate-400">
                <span>Auth Scope:</span>
                <span className="font-mono text-sky-400">{c.scope}</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Failures:</span>
                <span className="font-mono text-slate-300">{c.failure_count} / 3</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Circuit Breaker:</span>
                <span className="text-emerald-400">CLOSED (Normal)</span>
              </div>
            </div>

            <div className="pt-2 border-t border-slate-800/60 flex justify-between items-center text-[10px] text-slate-500">
              <span>Last Sync:</span>
              <span>{new Date(c.last_sync).toLocaleTimeString()}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
