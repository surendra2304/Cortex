"use client";

import React, { useState, useEffect, useRef } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

export default function VisitorsPage() {
  const [selectedVid, setSelectedVid] = useState<string>("vis_123");
  const [isLiveMode, setIsLiveMode] = useState<boolean>(true);
  const [wsEvents, setWsEvents] = useState<any[]>([]);
  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const wsRef = useRef<WebSocket | null>(null);

  // SWR fallback polling
  const { data, error, isLoading } = useSWR("/v1/events?limit=20", fetcher, {
    refreshInterval: isLiveMode ? 0 : 3000
  });
  const { data: profileData } = useSWR(selectedVid ? `/v1/visitors/${selectedVid}/profile` : null, fetcher);

  useEffect(() => {
    if (!isLiveMode) {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setWsConnected(false);
      return;
    }

    try {
      const ws = new WebSocket("ws://localhost:8000/ws/v1/live?token=dev_operator");
      wsRef.current = ws;

      ws.onopen = () => {
        setWsConnected(true);
        ws.send(JSON.stringify({ action: "subscribe", channel: "visitors" }));
        ws.send(JSON.stringify({ action: "subscribe", channel: "events" }));
      };

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type && payload.data) {
            setWsEvents((prev) => [
              {
                event_id: payload.data.event_id || payload.trace_id,
                actor_id: payload.data.actor_id || "live_visitor",
                type: payload.type,
                source: payload.channel,
                occurred_at: payload.timestamp
              },
              ...prev.slice(0, 30)
            ]);
          }
        } catch {}
      };

      ws.onclose = () => {
        setWsConnected(false);
      };

      ws.onerror = () => {
        setWsConnected(false);
      };
    } catch {
      setWsConnected(false);
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [isLiveMode]);

  const displayEvents = isLiveMode && wsEvents.length > 0 ? wsEvents : (data || []);

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Live Visitor Journeys &amp; Real-Time Operations</h1>
          <p className="text-sm text-slate-400 mt-1">Real-time visitor telemetry stream, WebSocket push, and stitched identity graphs.</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setIsLiveMode(!isLiveMode)}
            className={`px-3 py-1 rounded text-xs font-semibold border transition ${
              isLiveMode
                ? "bg-emerald-950 text-emerald-400 border-emerald-800"
                : "bg-slate-800 text-slate-300 border-slate-700"
            }`}
          >
            {isLiveMode ? "LIVE WEBSOCKET ON" : "POLLING (SWR)"}
          </button>
          <span className={`text-[10px] px-2 py-0.5 rounded border ${
            wsConnected
              ? "bg-emerald-950 text-emerald-400 border-emerald-800"
              : "bg-amber-950 text-amber-400 border-amber-800"
          }`}>
            {wsConnected ? "STREAM CONNECTED (<50ms)" : "FALLBACK ACTIVE"}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Stream Table */}
        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow">
          <div className="p-4 border-b border-slate-800 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-200">Real-Time Event Stream</h2>
            <span className="text-xs text-slate-400">Channel: ws/v1/live (events)</span>
          </div>

          <table className="w-full text-left text-sm text-slate-300">
            <thead className="bg-slate-950/60 text-xs uppercase text-slate-400 border-b border-slate-800">
              <tr>
                <th className="p-3">Actor / Visitor</th>
                <th className="p-3">Event Type</th>
                <th className="p-3">Source / Channel</th>
                <th className="p-3">Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {displayEvents.length > 0 ? (
                displayEvents.map((e: any, idx: number) => (
                  <tr
                    key={e.event_id || idx}
                    onClick={() => setSelectedVid(e.actor_id)}
                    className={`cursor-pointer transition hover:bg-slate-800/60 ${selectedVid === e.actor_id ? "bg-sky-950/40" : ""}`}
                  >
                    <td className="p-3 font-mono text-xs text-sky-400">{e.actor_id}</td>
                    <td className="p-3">
                      <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-200 text-xs font-mono">
                        {e.type}
                      </span>
                    </td>
                    <td className="p-3 text-xs text-slate-400">{e.source || "live-ws"}</td>
                    <td className="p-3 text-xs text-slate-500">
                      {new Date(e.occurred_at || Date.now()).toLocaleTimeString()}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={4} className="p-8 text-center text-slate-500 text-xs italic">
                    Awaiting live visitor events...
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Profile Details Panel */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-4">
          <h2 className="text-sm font-semibold text-slate-200 border-b border-slate-800 pb-2">
            Stitched Identity Profile
          </h2>

          <div className="space-y-3 text-xs">
            <div>
              <span className="text-slate-500 block text-[10px] uppercase">Selected Visitor ID</span>
              <span className="font-mono text-sky-400 break-all">{selectedVid}</span>
            </div>

            <div>
              <span className="text-slate-500 block text-[10px] uppercase">Identified Status</span>
              <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                profileData?.is_identified ? "bg-emerald-950 text-emerald-400 border border-emerald-800" : "bg-slate-800 text-slate-400"
              }`}>
                {profileData?.is_identified ? "IDENTIFIED LEAD" : "PSEUDONYMOUS VISITOR"}
              </span>
            </div>

            <div>
              <span className="text-slate-500 block text-[10px] uppercase">Primary Email</span>
              <span className="text-slate-200">{profileData?.primary_email || "Anonymous (No email attached)"}</span>
            </div>

            <div>
              <span className="text-slate-500 block text-[10px] uppercase">Resolution Graph Links</span>
              <span className="text-slate-300 font-mono">{profileData?.linked_identities_count || 1} identity keys linked</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
