import React from "react";
import Sidebar from "@/components/Sidebar";
import CredentialControl from "@/components/CredentialControl";
import "../globals.css";

export const metadata = {
  title: "CORTEX — Growth console",
  description: "A live lead and activity workspace powered by the CORTEX API.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Sidebar />
        <main className="shell-main">
          <header className="topbar">
            <div className="topbar-context"><span className="topbar-kicker">CORTEX WORKSPACE</span><span className="topbar-separator">/</span><span>Growth console</span></div>
            <div className="topbar-actions"><span className="api-caption">API access</span><CredentialControl /></div>
          </header>
          <div className="page-content">{children}</div>
          <footer className="app-footer"><span>CORTEX</span><span>Live data is shown only when returned by the API.</span></footer>
        </main>
      </body>
    </html>
  );
}
