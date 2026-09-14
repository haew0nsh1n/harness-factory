import type { ReactNode } from "react";

import { requirePortalSession, signOut } from "@/lib/auth";

interface AppShellProps {
  children: ReactNode;
}

export async function AppShell({ children }: AppShellProps) {
  const authState = await requirePortalSession();

  async function signOutAction(): Promise<void> {
    "use server";

    await signOut({ redirectTo: "/" });
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <h1>Harness Factory</h1>
        <nav aria-label="Primary">
          <a href="/">Dashboard</a>
          <a href="/studio">Harness Studio</a>
          <a href="/registry">Asset Registry</a>
        </nav>
        {authState.mode === "development" ? (
          <p className="banner" role="status">
            Development identity
          </p>
        ) : (
          <form action={signOutAction}>
            <p className="muted">{authState.viewerLabel}</p>
            <button type="submit">Sign out</button>
          </form>
        )}
      </aside>
      <main className="main-content">{children}</main>
    </div>
  );
}
