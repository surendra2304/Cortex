"use client";

import React, { useState } from "react";
import { approveAction } from "@/lib/api";

export interface PendingAction {
  id: string;
  action_type: string;
  status: string;
  params: Record<string, any>;
  reason: string;
  proposed_by?: string;
  confidence?: number;
}

interface ApprovalModalProps {
  action: PendingAction | null;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export default function ApprovalModal({ action, isOpen, onClose, onSuccess }: ApprovalModalProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen || !action) return null;

  const handleApprove = async () => {
    setIsSubmitting(true);
    setError(null);
    try {
      await approveAction(action.id);
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Failed to approve action.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-5">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div>
            <span className="text-xs uppercase font-mono px-2 py-0.5 rounded bg-amber-950 text-amber-400 border border-amber-800">
              Policy Engine HITL Gate
            </span>
            <h3 className="text-lg font-bold text-slate-100 mt-1">Review Proposed Action</h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200">
            ?
          </button>
        </div>

        <div className="space-y-4 text-sm">
          <div>
            <span className="text-xs font-semibold text-slate-400 uppercase">Action Type</span>
            <p className="text-sky-400 font-mono font-medium text-base">{action.action_type}</p>
          </div>

          <div>
            <span className="text-xs font-semibold text-slate-400 uppercase">Reasoning & Justification</span>
            <p className="text-slate-200 mt-0.5 bg-slate-950/60 p-3 rounded border border-slate-800/80">
              {action.reason}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <span className="text-xs font-semibold text-slate-400 uppercase">Confidence Score</span>
              <p className="text-emerald-400 font-semibold text-base">
                {action.confidence ? `${(action.confidence * 100).toFixed(0)}%` : "88%"}
              </p>
            </div>
            <div>
              <span className="text-xs font-semibold text-slate-400 uppercase">Proposed By</span>
              <p className="text-slate-300 font-mono text-sm">{action.proposed_by || "agent_growth"}</p>
            </div>
          </div>

          <div>
            <span className="text-xs font-semibold text-slate-400 uppercase">Parameters</span>
            <pre className="bg-slate-950 text-slate-300 p-3 rounded border border-slate-800 font-mono text-xs overflow-x-auto mt-1">
              {JSON.stringify(action.params, null, 2)}
            </pre>
          </div>

          {error && <p className="text-xs text-rose-400 bg-rose-950/50 p-2 rounded border border-rose-800">{error}</p>}
        </div>

        <div className="flex items-center justify-end gap-3 border-t border-slate-800 pt-4">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-lg transition"
          >
            Cancel
          </button>
          <button
            onClick={handleApprove}
            disabled={isSubmitting}
            className="px-4 py-2 text-sm font-semibold bg-sky-500 hover:bg-sky-400 text-slate-950 rounded-lg transition shadow disabled:opacity-50"
          >
            {isSubmitting ? "Approving..." : "Approve & Execute"}
          </button>
        </div>
      </div>
    </div>
  );
}
