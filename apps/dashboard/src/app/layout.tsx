import React from "react";
import Sidebar from "@/components/Sidebar";
import "../globals.css";

export const metadata = {
  title: "NEXUS Control Center",
  description: "Autonomous Website & Web App Operations Intelligence Dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-slate-950 text-slate-100 min-h-screen">
        <Sidebar />
        <main className="pl-64 min-h-screen">
          <header className="h-16 border-b border-slate-800 flex items-center justify-between px-8 bg-slate-900/50 backdrop-blur">
            <h2 className="text-lg font-semibold text-slate-200">Control Center</h2>
            <div className="flex items-center gap-3">
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
              <span className="text-xs font-medium text-slate-400">Autonomous Mode: Active</span>
            </div>
          </header>
          <div className="p-8">{children}</div>
        </main>
      </body>
    </html>
  );
}
