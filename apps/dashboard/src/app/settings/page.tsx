"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

export default function SettingsPage() {
  const { data: settings } = useSWR("/v1/tenant/settings", fetcher);
  const { data: usage } = useSWR("/v1/tenant/usage", fetcher);

  const [onboardName, setOnboardName] = useState("");
  const [onboardEmail, setOnboardEmail] = useState("");
  const [onboardResult, setOnboardResult] = useState<any>(null);

  const handleOnboard = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch("http://localhost:8000/v1/tenants", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_name: onboardName, admin_email: onboardEmail, plan: "pro" })
      });
      const json = await res.json();
      setOnboardResult(json);
    } catch {
      setOnboardResult({ status: "error", message: "Failed to onboard tenant." });
    }
  };

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Multi-Tenant SaaS &amp; White-Label Settings</h1>
          <p className="text-sm text-slate-400 mt-1">Tenant isolation, usage metering, custom domains, and white-label branding.</p>
        </div>
        <span className="text-xs font-mono bg-purple-950 text-purple-400 px-3 py-1 rounded border border-purple-800 uppercase">
          Plan: {settings?.plan || "Enterprise"}
        </span>
      </div>

      {/* Usage Metering Quota Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow">
          <span className="text-slate-500 block text-[10px] uppercase font-semibold">Events Ingested (Month)</span>
          <span className="text-xl font-bold text-slate-100 font-mono">
            {usage?.events_ingested?.toLocaleString() || "184,500"}
          </span>
          <span className="text-[11px] text-slate-400 block mt-1">
            Quota: {usage?.monthly_limit?.toLocaleString() || "5,000,000"} ({usage?.usage_pct || 3.69}%)
          </span>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow">
          <span className="text-slate-500 block text-[10px] uppercase font-semibold">Connected Sites</span>
          <span className="text-xl font-bold text-sky-400 font-mono">
            {usage?.active_sites || 4} / {usage?.max_sites || 10}
          </span>
          <span className="text-[11px] text-slate-400 block mt-1">Isolated per tenant</span>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow">
          <span className="text-slate-500 block text-[10px] uppercase font-semibold">AI Universe Consultations</span>
          <span className="text-xl font-bold text-purple-400 font-mono">
            {usage?.ai_universe_calls || 1240}
          </span>
          <span className="text-[11px] text-slate-400 block mt-1">FAST / REVIEW / DEBATE</span>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow">
          <span className="text-slate-500 block text-[10px] uppercase font-semibold">Automated Workflow Runs</span>
          <span className="text-xl font-bold text-emerald-400 font-mono">
            {usage?.workflow_runs || 850}
          </span>
          <span className="text-[11px] text-slate-400 block mt-1">Closed-loop executions</span>
        </div>
      </div>

      {/* White-Label Branding & Custom Domain */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-4">
        <h2 className="text-sm font-semibold text-slate-200 border-b border-slate-800 pb-2">
          White-Label Customization &amp; Domain CNAME
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          <div>
            <span className="text-slate-500 block text-[10px] uppercase font-semibold">Custom CNAME Domain</span>
            <span className="font-mono text-sky-400 font-semibold">{settings?.branding?.custom_domain || "ops.enterprise-corp.com"}</span>
          </div>
          <div>
            <span className="text-slate-500 block text-[10px] uppercase font-semibold">Primary Theme Color</span>
            <div className="flex items-center gap-2 mt-1">
              <span className="h-4 w-4 rounded bg-[#0284c7] inline-block border border-slate-700"></span>
              <span className="font-mono text-slate-300">{settings?.branding?.primary_color || "#0284c7"}</span>
            </div>
          </div>
          <div>
            <span className="text-slate-500 block text-[10px] uppercase font-semibold">Telemetry Data Retention</span>
            <span className="font-semibold text-slate-300">{settings?.retention_days || 365} Days (Automated Purge)</span>
          </div>
        </div>
      </div>

      {/* New Tenant Onboarding Flow */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-4">
        <h2 className="text-sm font-semibold text-slate-200">Onboard New Tenant Organization</h2>
        <form onSubmit={handleOnboard} className="flex gap-3">
          <input
            type="text"
            value={onboardName}
            onChange={(e) => setOnboardName(e.target.value)}
            placeholder="Organization Name (e.g. Acme Corp)"
            className="bg-slate-950 border border-slate-800 rounded-lg px-4 py-2 text-xs text-slate-200 font-mono flex-1"
          />
          <input
            type="email"
            value={onboardEmail}
            onChange={(e) => setOnboardEmail(e.target.value)}
            placeholder="Admin Email (admin@acme.com)"
            className="bg-slate-950 border border-slate-800 rounded-lg px-4 py-2 text-xs text-slate-200 font-mono flex-1"
          />
          <button
            type="submit"
            className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold rounded-lg transition"
          >
            Provision Tenant
          </button>
        </form>

        {onboardResult && (
          <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 text-xs font-mono text-slate-300">
            <span className="text-slate-500 block text-[10px] uppercase font-bold mb-1">Provisioning Output:</span>
            <pre className="overflow-x-auto text-[11px] text-sky-400">
              {JSON.stringify(onboardResult, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
