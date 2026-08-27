"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

export default function VisitorsPage() {
  const [selectedVid, setSelectedVid] = useState<string>("vis_123");
  const { data, error, isLoading } = useSWR("/v1/events?limit=20", fetcher);
  const { data: profileData } = useSWR(selectedVid ? `/v1/visitors/${selectedVid}/profile` : null, fetcher);

  const events = data || [];

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Live Visitor Journeys & Profiles</h1>
          <p className="text-sm text-slate-400 mt-1">Real-time visitor telemetry stream and stitched identity resolution graphs.</p>
        </div>
        <span className="text-xs font-mono bg-sky-950 text-sky-400 px-3 py-1 rounded border border-sky-800">
          Live Ingestion Stream
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Stream Table */}
        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow">
          <div className="p-4 border-b border-slate-800 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-200">Recent Live Events</h2>
            <span className="text-xs text-slate-400">Endpoint: /v1/events</span>
          </div>

          {isLoading ? (
            <div className="p-8 text-center text-sm text-slate-500">Loading live visitor stream...</div>
          ) : error ? (
            <div className="p-8 text-center text-sm text-rose-400">Failed to load visitor stream.</div>
          ) : (
            <table className="w-full text-left text-sm text-slate-300">
              <thead className="bg-slate-950/60 text-xs uppercase text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="p-3">Actor / Visitor</th>
                  <th className="p-3">Event Type</th>
                  <th className="p-3">Source</th>
                  <th className="p-3">Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {events.length > 0 ? (
                  events.map((e: any) => (
                    <tr
                      key={e.event_id}
                      onClick={() => setSelectedVid(e.actor_id)}
                      className={`cursor-pointer transition hover:bg-slate-800/60 ${selectedVid === e.actor_id ? "bg-sky-950/40" : ""}`}
                    >
                      <td className="p-3 font-mono text-xs text-sky-400">{e.actor_id}</td>
                      <td className="p-3">
                        <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-200 text-xs font-mono">
                          {e.type}
                        </span>
                      </td>
                      <td className="p-3 text-xs text-slate-400">{e.source}</td>
                      <td className="p-3 text-xs text-slate-500">
                        {e.occurred_at ? new Date(e.occurred_at).toLocaleTimeString() : "Just now"}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} className="p-8 text-center text-slate-500 text-xs">
                      No events in stream yet. SDK events will appear here in real time.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>

        {/* Selected Visitor Profile & Resolution Graph */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-4">
          <h2 className="text-sm font-semibold text-slate-200 border-b border-slate-800 pb-2">
            Resolved Identity Profile
          </h2>
          <div className="text-xs space-y-2">
            <div>
              <span className="text-slate-500">Selected ID:</span>
              <p className="font-mono text-sky-400">{selectedVid}</p>
            </div>
            <div>
              <span className="text-slate-500">Primary Email:</span>
              <p className="text-emerald-400 font-medium">
                {profileData?.profile?.primary_email || "Anonymous Visitor"}
              </p>
            </div>
            <div>
              <span className="text-slate-500">Linked Identities:</span>
              <div className="mt-1 space-y-1">
                {profileData?.linked_identities?.length > 0 ? (
                  profileData.linked_identities.map((l: any) => (
                    <span key={l.link_id} className="block font-mono bg-slate-950 px-2 py-1 rounded text-slate-400 border border-slate-800">
                      {l.source_type}: {l.source_value} (conf: {l.confidence})
                    </span>
                  ))
                ) : (
                  <span className="text-slate-500 italic">No linked identities yet.</span>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
