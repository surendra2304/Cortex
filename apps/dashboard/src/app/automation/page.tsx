"use client";

import React, { useState } from "react";
import useSWR, { mutate } from "swr";
import { fetcher } from "@/lib/api";

export default function AutomationPage() {
  const { data: workflows } = useSWR("/v1/workflows", fetcher);
  const { data: pendingApprovals } = useSWR("/v1/approvals/pending", fetcher);
  const [selectedApproval, setSelectedApproval] = useState<any>(null);
  const [actionMessage, setActionMessage] = useState<string>("");

  const list = workflows || [];
  const approvals = pendingApprovals || [];

  const handleDecision = async (actionId: string, decision: "approve" | "reject") => {
    try {
      const res = await fetch(`http://localhost:8000/v1/actions/${actionId}/${decision}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ operator_id: "operator_alex", reason: decision === "approve" ? "Approved in dashboard" : "Rejected by operator" })
      });
      if (res.ok) {
        setActionMessage(`Action ${actionId} successfully ${decision}d.`);
        setSelectedApproval(null);
        mutate("/v1/approvals/pending");
      }
    } catch (err) {
      setActionMessage(`Error submitting ${decision}.`);
    }
  };

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Workflow Automation & Approvals</h1>
          <p className="text-sm text-slate-400 mt-1">Autonomous state machines and human-in-the-loop approval gates.</p>
        </div>
        <span className="text-xs font-mono bg-purple-950 text-purple-400 px-3 py-1 rounded border border-purple-800">
          Pending Approvals: {approvals.length}
        </span>
      </div>

      {actionMessage && (
        <div className="p-3 bg-emerald-950/40 border border-emerald-800 text-emerald-400 text-xs rounded-lg">
          {actionMessage}
        </div>
      )}

      {/* Pending Approvals Queue */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-4">
        <h2 className="text-sm font-semibold text-slate-200 flex items-center justify-between">
          <span>Human-in-the-Loop Approval Queue</span>
          <span className="text-xs text-slate-400">Endpoint: /v1/approvals/pending</span>
        </h2>

        {approvals.length > 0 ? (
          <div className="space-y-3">
            {approvals.map((a: any) => (
              <div key={a.id} className="p-4 bg-slate-950 border border-slate-800 rounded-lg flex items-center justify-between">
                <div className="space-y-1 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sky-400 font-semibold">{a.action_type}</span>
                    <span className="px-2 py-0.5 rounded bg-rose-950 text-rose-400 border border-rose-800 text-[10px]">
                      Risk: {a.risk_score}
                    </span>
                  </div>
                  <p className="text-slate-300">{a.rationale}</p>
                  <span className="text-[11px] text-slate-500">Target: {a.target} | Expires: {new Date(a.expires_at).toLocaleTimeString()}</span>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleDecision(a.id, "approve")}
                    className="px-3 py-1.5 bg-emerald-900 hover:bg-emerald-800 text-emerald-200 text-xs font-medium rounded transition"
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => handleDecision(a.id, "reject")}
                    className="px-3 py-1.5 bg-rose-900 hover:bg-rose-800 text-rose-200 text-xs font-medium rounded transition"
                  >
                    Reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-slate-500 text-xs italic">No high-impact actions pending operator review.</p>
        )}
      </div>

      {/* Available Workflows */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-4">
        <h2 className="text-sm font-semibold text-slate-200">First-Class Operational Workflows</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {list.map((w: any) => (
            <div key={w.name} className="p-4 bg-slate-950 rounded-lg border border-slate-800 space-y-2">
              <span className="font-mono text-sky-400 font-semibold text-xs block">{w.name}</span>
              <p className="text-xs text-slate-300">{w.description}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
