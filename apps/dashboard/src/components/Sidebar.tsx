import React from "react";
import Link from "next/link";

export const NAV_ITEMS = [
  { name: "Overview", href: "/" },
  { name: "Visitors", href: "/visitors" },
  { name: "Leads", href: "/leads" },
  { name: "Funnels", href: "/funnels" },
  { name: "Memory", href: "/memory" },
  { name: "Customers", href: "/customers" },
  { name: "Conversations", href: "/conversations" },
  { name: "Agents", href: "/agents" },
  { name: "Intelligence", href: "/intelligence" },
  { name: "Automation", href: "/automation" },
  { name: "Experiments", href: "/experiments" },
  { name: "Incidents", href: "/incidents" },
  { name: "Integrations", href: "/integrations" },
  { name: "Governance", href: "/governance" }
];

export default function Sidebar() {
  return (
    <aside className="w-64 bg-slate-900 text-slate-200 border-r border-slate-800 flex flex-col h-screen fixed left-0 top-0">
      <div className="p-5 border-b border-slate-800 flex items-center justify-between">
        <h1 className="text-xl font-bold tracking-wider text-sky-400">NEXUS</h1>
        <span className="text-xs bg-sky-950 text-sky-400 px-2 py-0.5 rounded border border-sky-800">Ops Intel</span>
      </div>
      <nav className="flex-1 overflow-y-auto p-4 space-y-1">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.name}
            href={item.href}
            className="flex items-center px-3 py-2 text-sm font-medium rounded-md hover:bg-slate-800 hover:text-white transition-colors"
          >
            {item.name}
          </Link>
        ))}
      </nav>
      <div className="p-4 border-t border-slate-800 text-xs text-slate-500">
        Connected to: <span className="text-emerald-400">api.nexus.dev</span>
      </div>
    </aside>
  );
}
