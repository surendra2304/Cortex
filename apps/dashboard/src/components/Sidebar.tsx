"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { name: "Overview", href: "/", mark: "⌂" },
  { name: "Leads", href: "/leads", mark: "◎" },
  { name: "Activity", href: "/activity", mark: "⌁" },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sidebar">
      <Link href="/" className="brand" aria-label="Cortex home">
        <span className="brand-mark">C</span>
        <span className="brand-name">cortex<span>.</span></span>
      </Link>

      <div className="workspace-label">WORKSPACE</div>
      <nav className="main-nav" aria-label="Main navigation">
        {NAV_ITEMS.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link key={item.href} href={item.href} className={`nav-link${active ? " active" : ""}`} aria-current={active ? "page" : undefined}>
              <span className="nav-mark" aria-hidden="true">{item.mark}</span>
              <span>{item.name}</span>
              {item.name === "Leads" && <span className="nav-arrow">↗</span>}
            </Link>
          );
        })}
      </nav>

      <div className="sidebar-bottom">
        <div className="sidebar-note">
          <span className="note-icon">i</span>
          <p>Activity and lead totals come from the connected CORTEX API.</p>
        </div>
        <div className="operator-card">
          <div className="operator-avatar">S</div>
          <div className="operator-copy"><strong>Workspace</strong><span>Operator console</span></div>
          <span className="operator-menu">···</span>
        </div>
      </div>
    </aside>
  );
}
