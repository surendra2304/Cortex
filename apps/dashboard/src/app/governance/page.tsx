"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import ApprovalModal, { PendingAction } from "@/components/ApprovalModal";

export default function GovernancePage() {
  const { data: auditData } = useSWR("/v1/audit/export", fetcher);
  const [selectedAction, setSelectedAction] = useState<PendingAction | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [exportVid, setExportVid] = useState("vis_123");
  const [privacyOutput, setPrivacyOutput] = useState<any>(null);

  const pendingActions: PendingAction[] = [
    {
      id: "act_high_1",
      action_type: "banner_injection",
      status: "pending_approval",
      reason: "High bounce rate on pricing table; suggesting annual discount CTA banner to increase conversion.",
      confidence: 0.88,
      proposed_by: "agent_growth",
      params: { variant: "annual_discount_banner", target: "pricing_cta" }
    },
    {
      id: "act_high_2",
      action_type: "experiment_mutate",
      status: "pending_approval",
      reason: "Significant conversion lift detected on variant B; propose increasing traffic allocation to 80%.",
      confidence: 0.94,
      proposed_by: "agent_growth",
      params: { experiment_id: "exp_checkout_split", traffic_allocation: 0.8 }
    }
  ];

  const handleExport = async () => {
    try {
      const res = await fetch(`http://localhost:8000/v1/privacy/export/${exportVid}`, { method: "POST" });
      const json = await res.json();
      setPrivacyOutput(json);
    } catch {
      setPrivacyOutput({ status: "error", message: "Failed to generate privacy export." });
    }
  };

  const handleDelete = async () => {
    try {
      const res = await fetch(`http://localhost:8000/v1/privacy/delete/${exportVid}`, { method: "POST" });
      const json = await res.json();
      setPrivacyOutput(json);
    } catch {
      setPrivacyOutput({ status: "error", message: "Failed to execute hard erasure." });
    }
  };

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Governance, Privacy &amp; Compliance Suite</h1>
          <p className="text-sm text-slate-400 mt-1">
            GDPR / CCPA data subject rights, consent telemetry gating, and tamper-evident audit logs.
          </p>
        </div>
        <span className="text-xs font-mono bg-emerald-950 text-emerald-400 px-3 py-1 rounded border border-emerald-800">
          Audit Retention: 7 Years
        </span>
      </div>

      {/* GDPR / CCPA Subject Rights Toolbar */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-4">
        <h2 className="text-sm font-semibold text-slate-200">Data Subject Rights (GDPR Art. 15 / 17 &amp; CCPA)</h2>
        <div className="flex gap-3 items-center">
          <input
            type="text"
            value={exportVid}
            onChange={(e) => setExportVid(e.target.value)}
            placeholder="Enter Visitor ID (e.g. vis_123)"
            className="bg-slate-950 border border-slate-800 rounded-lg px-4 py-2 text-xs text-slate-200 font-mono w-64"
          />
          <button
            onClick={handleExport}
            className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold rounded-lg transition"
          >
            Generate JSON Export (Art. 15)
          </button>
          <button
            onClick={handleDelete}
            className="px-4 py-2 bg-rose-700 hover:bg-rose-600 text-white text-xs font-semibold rounded-lg transition"
          >
            Execute Hard Erasure (Art. 17)
          </button>
        </div>

        {privacyOutput && (
          <div className="p-3 bg-slate-950 rounded-lg border border-slate-800/80 text-xs font-mono text-slate-300">
            <span className="text-slate-500 block text-[10px] uppercase font-bold mb-1">Compliance Response:</span>
            <pre className="overflow-x-auto text-[11px] text-sky-400">
              {JSON.stringify(privacyOutput, null, 2)}
            </pre>
          </div>
        )}
      </div>

      {/* Pending Operator Approvals (HITL Queue) */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-200">Pending Operator Approvals (HITL Queue)</h2>
          <span className="text-xs text-slate-400">Click row to review &amp; approve</span>
        </div>

        <table className="w-full text-left text-sm text-slate-300">
          <thead className="bg-slate-950/60 text-xs uppercase text-slate-400 border-b border-slate-800">
            <tr>
              <th className="p-4">Action ID</th>
              <th className="p-4">Tool / Operation</th>
              <th className="p-4">Agent</th>
              <th className="p-4">Confidence</th>
              <th className="p-4">Reasoning</th>
              <th className="p-4">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {pendingActions.map((act) => (
              <tr
                key={act.id}
                onClick={() => {
                  setSelectedAction(act);
                  setIsModalOpen(true);
                }}
                className="hover:bg-slate-800/60 cursor-pointer transition"
              >
                <td className="p-4 font-mono font-medium text-sky-400">{act.id}</td>
                <td className="p-4 font-mono text-xs text-slate-200">{act.action_type}</td>
                <td className="p-4 font-mono text-xs text-purple-400">{act.proposed_by}</td>
                <td className="p-4 font-semibold text-emerald-400">
                  {act.confidence ? `${(act.confidence * 100).toFixed(0)}%` : "88%"}
                </td>
                <td className="p-4 text-xs text-slate-300 max-w-xs truncate">{act.reason}</td>
                <td className="p-4">
                  <button className="px-3 py-1 text-xs font-semibold bg-sky-500/20 text-sky-400 hover:bg-sky-500 hover:text-slate-950 rounded border border-sky-500/30 transition">
                    Review
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Immutable Audit Log Browser */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-3">
        <div className="flex justify-between items-center border-b border-slate-800 pb-2">
          <h2 className="text-sm font-semibold text-slate-200">Immutable Audit Trail (Hash-Chained)</h2>
          <span className="text-[10px] font-mono text-slate-400">
            Hash: {auditData?.tamper_evidence_hash?.slice(0, 24)}...
          </span>
        </div>

        <div className="space-y-2 text-xs">
          {auditData?.records?.map((rec: any, idx: number) => (
            <div key={idx} className="p-3 bg-slate-950 border border-slate-800 rounded-lg flex justify-between items-center">
              <div>
                <span className="font-mono text-sky-400 font-bold">{rec.action}</span>
                <span className="text-slate-400 ml-2">Actor: <strong className="text-slate-200">{rec.actor}</strong></span>
              </div>
              <span className="text-[10px] text-slate-500 font-mono">{rec.timestamp}</span>
            </div>
          ))}
        </div>
      </div>

      <ApprovalModal
        action={selectedAction}
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSuccess={() => {}}
      />
    </div>
  );
}
