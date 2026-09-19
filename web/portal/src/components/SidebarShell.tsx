"use client";

import { useEffect, useState, type ReactNode } from "react";

const STORAGE_KEY = "hf-sidebar-collapsed";

export function SidebarShell({
  sidebar,
  children,
  collapseLabel,
  expandLabel,
}: {
  sidebar: ReactNode;
  children: ReactNode;
  collapseLabel: string;
  expandLabel: string;
}): React.JSX.Element {
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    setCollapsed(window.localStorage?.getItem(STORAGE_KEY) === "1");
  }, []);

  const toggle = () => {
    setCollapsed((value) => {
      const next = !value;
      window.localStorage?.setItem(STORAGE_KEY, next ? "1" : "0");
      return next;
    });
  };

  return (
    <div className={`app-shell${collapsed ? " app-shell--collapsed" : ""}`}>
      <aside className="sidebar">{sidebar}</aside>
      <button
        type="button"
        className="sidebar-toggle"
        aria-label={collapsed ? expandLabel : collapseLabel}
        aria-expanded={!collapsed}
        onClick={toggle}
      >
        <span aria-hidden="true">{collapsed ? "›" : "‹"}</span>
      </button>
      <main className="main-content">{children}</main>
    </div>
  );
}
