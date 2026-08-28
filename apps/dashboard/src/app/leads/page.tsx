"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

const STAGES = ["new", "qualified", "contacted", "opportunity", "customer"];

export default function LeadsPage() {
  const [selectedLead, setSelectedLead] = useState<any>(null);
  const { data: leadsData } = useSWR("/v1/leads", fetcher);

  const initialLeads = leadsData?.leads || [
    {
      id: "lead_ent_01",
      email: "director@bigcorp.com",
      company: "BigCorp",
      stage: "qualified",
      score: 0.88,
      breakdown: { behavior: 0.38, firmographic: 0.30, engagement: 0.12, source: 0.08 },
      evidence: ["pricing_views=3", "demo_views=1", "is_enterprise_domain=True"],
      ai_consultation: { mode: "REVIEW", confidence: 0.92, decision: "ROUTE_ENTERPRISE_LEAD" },
      next_best_action: "Schedule technical executive demo with Solutions Architect"
    },
    {
      id: "lead_mid_02",
      email: "growth@saasco.io",
      company: "SaaSCo",
      stage: "new",
      score: 0.65,
      breakdown: { behavior: 0.28, firmographic: 0.20, engagement: 0.10, source: 0.07 },
      evidence: ["pricing_views=1", "doc_depth=4"],
      ai_consultation: { mode: "FAST", confidence: 0.78, decision: "ROUTE_MIDMARKET_LEAD" },
      next_best_action: "Send personalized automated follow-up email via SendGrid"
    },
    {
      id: "lead_opp_03",
      email: "vp@cloudinfra.net",
      company: "CloudInfra",
      stage: "opportunity",
      score: 0.94,
      breakdown: { behavior: 0.40, firmographic: 0.30, engagement: 0.16, source: 0.08 },
      evidence: ["pricing_views=5", "demo_requested=True", "enterprise_security_page=True"],
      ai_consultation: { mode: "DEBATE", confidence: 0.96, decision: "PRIORITY_CLOSING" },
      next_best_action: "Dispatch security compliance whitepaper and pricing custom contract"
    }
  ];

  const [pipeline, setPipeline] = useState<any[]>(initialLeads);

  const moveStage = (leadId: string, direction: "left" | "right") => {
    setPipeline((prev) =>
      prev.map((l) => {
        if (l.id !== leadId) return l;
        const currIdx = STAGES.indexOf(l.stage);
        const nextIdx = direction === "right" ? Math.min(currIdx + 1, STAGES.length - 1) : Math.max(currIdx - 1, 0);
        return { ...l, stage: STAGES[nextIdx] };
      })
    );
  };

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Predictive Lead Intelligence &amp; Pipeline Board</h1>
          <p className="text-sm text-slate-400 mt-1">Autonomous 4-factor scoring, next-best-action routing, and lifecycle stage progression.</p>
        </div>
        <span className="text-xs font-mono bg-purple-950 text-purple-400 px-3 py-1 rounded border border-purple-800">
          Pipeline Leads: {pipeline.length}
        </span>
      </div>

      {/* 5-Column Interactive Pipeline Board */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
        {STAGES.map((stg) => {
          const inStage = pipeline.filter((l) => l.stage === stg);
          return (
            <div key={stg} className="bg-slate-900 border border-slate-800 rounded-xl p-3 space-y-3 flex flex-col min-h-[300px]">
              <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                <span className="text-xs font-mono uppercase font-bold text-slate-300">{stg}</span>
                <span className="text-[10px] font-mono bg-slate-950 text-slate-400 px-1.5 py-0.5 rounded border border-slate-800">
                  {inStage.length}
                </span>
              </div>

              <div className="space-y-2 flex-1">
                {inStage.map((lead) => (
                  <div
                    key={lead.id}
                    onClick={() => setSelectedLead(lead)}
                    className={`p-3 bg-slate-950 border rounded-lg cursor-pointer transition space-y-2 ${
                      selectedLead?.id === lead.id ? "border-sky-500 shadow-md shadow-sky-950" : "border-slate-800 hover:border-slate-700"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-200 truncate">{lead.company || lead.email}</span>
                      <span className="text-xs font-mono font-bold text-emerald-400">{(lead.score * 100).toFixed(0)}</span>
                    </div>

                    <div className="flex justify-between items-center pt-1 text-[10px]">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          moveStage(lead.id, "left");
                        }}
                        className="px-2 py-0.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded"
                      >
                        ◀
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          moveStage(lead.id, "right");
                        }}
                        className="px-2 py-0.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded"
                      >
                        ▶
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* Selected Lead Detail & AI Reasoning Drawer */}
      {selectedLead && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h2 className="text-base font-bold text-slate-100">{selectedLead.company || selectedLead.email}</h2>
              <span className="text-xs text-slate-400 font-mono">Lead ID: {selectedLead.id}</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs font-mono bg-emerald-950 text-emerald-400 px-3 py-1 rounded border border-emerald-800 font-bold">
                Overall Lead Score: {selectedLead.score}
              </span>
              <button onClick={() => setSelectedLead(null)} className="text-slate-500 hover:text-slate-300 text-sm">
                ✕
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
            {/* 4-Factor Scoring Breakdown */}
            <div className="p-4 bg-slate-950 border border-slate-800 rounded-lg space-y-2">
              <span className="text-[10px] font-mono uppercase text-slate-400 font-bold block">4-Factor Scoring Weights</span>
              <div className="space-y-1">
                <div className="flex justify-between">
                  <span>Behavior (40%):</span>
                  <span className="font-mono text-emerald-400">{selectedLead.breakdown?.behavior}</span>
                </div>
                <div className="flex justify-between">
                  <span>Firmographic (30%):</span>
                  <span className="font-mono text-sky-400">{selectedLead.breakdown?.firmographic}</span>
                </div>
                <div className="flex justify-between">
                  <span>Engagement (20%):</span>
                  <span className="font-mono text-purple-400">{selectedLead.breakdown?.engagement}</span>
                </div>
                <div className="flex justify-between">
                  <span>Source (10%):</span>
                  <span className="font-mono text-amber-400">{selectedLead.breakdown?.source}</span>
                </div>
              </div>
            </div>

            {/* AI Universe Consultation History */}
            <div className="p-4 bg-slate-950 border border-slate-800 rounded-lg space-y-2">
              <span className="text-[10px] font-mono uppercase text-purple-400 font-bold block">AI Universe Deliberation</span>
              <div className="space-y-1">
                <div className="flex justify-between">
                  <span>Mode:</span>
                  <span className="font-mono text-purple-400 font-bold">{selectedLead.ai_consultation?.mode}</span>
                </div>
                <div className="flex justify-between">
                  <span>Confidence:</span>
                  <span className="font-mono text-emerald-400">{selectedLead.ai_consultation?.confidence}</span>
                </div>
                <div className="flex justify-between">
                  <span>Decision:</span>
                  <span className="font-mono text-sky-400">{selectedLead.ai_consultation?.decision}</span>
                </div>
              </div>
            </div>

            {/* Next Best Action */}
            <div className="p-4 bg-sky-950/30 border border-sky-800/60 rounded-lg space-y-2">
              <span className="text-[10px] font-mono uppercase text-sky-400 font-bold block">Autonomous Next-Best-Action</span>
              <p className="text-slate-200 text-xs">{selectedLead.next_best_action}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
