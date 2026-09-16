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
        <div className="brand-block">
          <a className="brand-mark" href="/" aria-label="Harness Factory 홈">
            HF
          </a>
          <div>
            <p className="brand-name">Harness Factory</p>
            <p className="brand-description">워크플로 설계 스튜디오</p>
          </div>
        </div>
        <nav aria-label="주요 메뉴">
          <a href="/">대시보드</a>
          <a href="/studio">스튜디오</a>
          <a href="/registry">레지스트리</a>
        </nav>
        <div className="sidebar-footer">
          {authState.mode === "development" ? (
            <p className="environment-note" role="status">
              개발 환경 ID 사용 중
            </p>
          ) : (
            <form action={signOutAction} className="session-block">
              <p>{authState.viewerLabel}</p>
              <button className="button-secondary button-compact" type="submit">
                로그아웃
              </button>
            </form>
          )}
        </div>
      </aside>
      <main className="main-content">{children}</main>
    </div>
  );
}
