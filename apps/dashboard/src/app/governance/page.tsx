"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import ApprovalModal, { PendingAction } from "@/components/ApprovalModal";

export default function GovernancePage() {
  const { data, mutate } = useSWR("/v1/audit/actions", fetcher);
  const [selectedAction, setSelectedAction] = useState<PendingAction | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Mock pending action list awaiting human approval
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

  const handleActionClick = (action: PendingAction) => {
    setSelectedAction(action);
    setIsModalOpen(true);
  };

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Governance & Policy Engine</h1>
          <p className="text-sm text-slate-400 mt-1">
            Human-in-the-Loop approval queue and immutable audit trail records.
          </p>
        </div>
        <span className="text-xs font-mono bg-amber-950 text-amber-400 px-3 py-1 rounded border border-amber-800">
          2 Actions Pending Approval
        </span>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-200">Pending Operator Approvals (HITL Queue)</h2>
          <span className="text-xs text-slate-400">Click row to review & approve</span>
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
                onClick={() => handleActionClick(act)}
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

      <ApprovalModal
        action={selectedAction}
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSuccess={() => {
          mutate();
        }}
      />
    </div>
  );
}
