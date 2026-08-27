"use client";

import React, { useState, useEffect, useRef } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

export default function AgentsPage() {
  const { data, error, isLoading } = useSWR("/v1/agents", fetcher);
  const [liveActivities, setLiveActivities] = useState<any[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    try {
      const ws = new WebSocket("ws://localhost:8000/ws/v1/live?token=dev_operator");
      wsRef.current = ws;

      ws.onopen = () => {
        ws.send(JSON.stringify({ action: "subscribe", channel: "agent_activity" }));
      };

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.channel === "agent_activity" && payload.data) {
            setLiveActivities((prev) => [payload.data, ...prev.slice(0, 10)]);
          }
        } catch {}
      };
    } catch {}

    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const agents = data?.agents || [];

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Live Agent Monitor &amp; Cognitive Loop State</h1>
          <p className="text-sm text-slate-400 mt-1">Real-time inspection of active 10-phase cognitive reasoning cycles across specialist agents.</p>
        </div>
        <span className="text-xs font-mono bg-purple-950 text-purple-400 px-3 py-1 rounded border border-purple-800">
          Agents Active: {agents.length || 6}
        </span>
      </div>

      {/* Live Cognitive Loop Monitor Feed */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-3">
        <h2 className="text-sm font-semibold text-slate-200 flex items-center justify-between">
          <span>Active Cognitive Loop Execution Monitor</span>
          <span className="text-xs text-emerald-400 flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></span>
            Streaming Live
          </span>
        </h2>

        {liveActivities.length > 0 ? (
          <div className="space-y-2">
            {liveActivities.map((act: any, idx: number) => (
              <div key={idx} className="p-3 bg-slate-950 border border-slate-800 rounded-lg flex items-center justify-between text-xs">
                <div>
                  <span className="font-mono text-sky-400 font-bold">{act.agent_id}</span>
                  <span className="text-slate-400 ml-2">Phase: <strong className="text-purple-400">{act.current_phase || "Reasoning"}</strong></span>
                  <p className="text-slate-300 mt-0.5">{act.decision_summary || "Evaluating event stream context."}</p>
                </div>
                <span className="text-[10px] text-slate-500 font-mono">{act.time || "Just now"}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-4 bg-slate-950 rounded-lg border border-slate-800/80 text-xs text-slate-400">
            Specialist agents standby. Next incoming event will stream live phase-by-phase execution trace.
          </div>
        )}
      </div>

      {/* Specialist Agent Directory */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {agents.map((ag: any) => (
          <div key={ag.id} className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono uppercase bg-slate-800 text-sky-400 px-2 py-0.5 rounded">
                {ag.domain}
              </span>
              <span className="text-xs flex items-center gap-1.5 text-emerald-400">
                <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></span>
                Online &amp; Active
              </span>
            </div>
            <div>
              <h3 className="text-lg font-bold text-slate-100 font-mono">{ag.id}</h3>
              <p className="text-xs text-slate-400 mt-1">
                Autonomous domain specialist executing input-driven cognitive reasoning and closed-loop learning.
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
    </div>
  );
}
