import type { ReactNode } from "react";

import { LocaleSwitcher } from "@/components/LocaleSwitcher";
import { getServerTranslations } from "@/i18n/server";
import { requirePortalSession, signOut } from "@/lib/auth";

interface AppShellProps {
  children: ReactNode;
}

export async function AppShell({ children }: AppShellProps) {
  const authState = await requirePortalSession();
  const { t } = await getServerTranslations();

  async function signOutAction(): Promise<void> {
    "use server";

    await signOut({ redirectTo: "/" });
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <a className="brand-mark" href="/" aria-label={t("brand.homeAriaLabel")}>
            HF
          </a>
          <div>
            <p className="brand-name">Harness Factory</p>
            <p className="brand-description">{t("brand.tagline")}</p>
          </div>
        </div>
        <nav aria-label={t("nav.menuLabel")}>
          <a href="/">{t("nav.dashboard")}</a>
          <a href="/studio">{t("nav.studio")}</a>
          <a href="/registry">{t("nav.registry")}</a>
        </nav>
        <div className="sidebar-footer">
          {authState.mode === "development" ? (
            <p className="environment-note" role="status">
              {t("footer.devBadge")}
            </p>
          ) : (
            <form action={signOutAction} className="session-block">
              <p>{authState.viewerLabel}</p>
              <button className="button-secondary button-compact" type="submit">
                {t("footer.signOut")}
              </button>
            </form>
          )}
          <LocaleSwitcher />
          <div className="sidebar-help-row">
            <a className="sidebar-help-link" href="/help">
              {t("nav.help")}
            </a>
            <a
              className="sidebar-settings-link"
              href="/settings"
              aria-label={t("nav.settings")}
              title={t("nav.settings")}
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
            </a>
          </div>
        </div>
      </aside>
      <main className="main-content">{children}</main>
    </div>
  );
}
