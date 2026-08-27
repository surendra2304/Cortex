"use client";

import React, { useState, useEffect, useRef } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

export default function IncidentsPage() {
  const { data: incidentsData } = useSWR("/v1/friday/incidents", fetcher);
  const [liveIncidents, setLiveIncidents] = useState<any[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    try {
      const ws = new WebSocket("ws://localhost:8000/ws/v1/live?token=dev_operator");
      wsRef.current = ws;

      ws.onopen = () => {
        ws.send(JSON.stringify({ action: "subscribe", channel: "incidents" }));
      };

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.channel === "incidents" && payload.data) {
            setLiveIncidents((prev) => [payload.data, ...prev.slice(0, 20)]);
          }
        } catch {}
      };
    } catch {}

    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const items = liveIncidents.length > 0 ? liveIncidents : (incidentsData || []);

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Live Incident Feed &amp; Root-Cause Hypotheses</h1>
          <p className="text-sm text-slate-400 mt-1">Autonomous triage, anomaly detection, and deterministic root-cause diagnosis.</p>
        </div>
        <span className="text-xs font-mono bg-rose-950 text-rose-400 px-3 py-1 rounded border border-rose-800">
          Active Alerts: {items.length}
        </span>
      </div>

      <div className="space-y-4">
        {items.length > 0 ? (
          items.map((inc: any, idx: number) => (
            <div key={inc.incident_id || idx} className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold border uppercase ${
                    inc.severity === "critical"
                      ? "bg-rose-950 text-rose-400 border-rose-800"
                      : inc.severity === "high"
                      ? "bg-amber-950 text-amber-400 border-amber-800"
                      : "bg-slate-800 text-slate-300 border-slate-700"
                  }`}>
                    {inc.severity || "HIGH"}
                  </span>
                  <span className="font-mono text-xs font-semibold text-slate-200">{inc.event_type}</span>
                </div>
                <span className="text-xs text-slate-500 font-mono">
                  {inc.occurred_at ? new Date(inc.occurred_at).toLocaleTimeString() : "Live"}
                </span>
              </div>

              <div className="p-3 bg-slate-950 rounded-lg border border-slate-800/80 text-xs text-slate-300">
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">Deterministic Root-Cause Hypothesis:</span>
                <p className="mt-1 text-slate-200">{inc.root_cause_hypothesis || "Detected error pattern in recent event stream."}</p>
              </div>

              <div className="flex justify-between text-[11px] text-slate-500">
                <span>Site: {inc.affected_site_id || "default"}</span>
                <span>Tenant: {inc.affected_tenant_id || "default"}</span>
              </div>
            </div>
          ))
        ) : (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-12 text-center text-slate-500 text-xs italic">
            All systems operational. No active anomalies or incidents detected.
          </div>
        )}
      </div>
    </div>
  );
}
