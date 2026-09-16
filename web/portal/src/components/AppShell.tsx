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
        </div>
      </aside>
      <main className="main-content">{children}</main>
    </div>
  );
}
