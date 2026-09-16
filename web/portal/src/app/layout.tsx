import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AppShell } from "@/components/AppShell";
import { I18nProvider } from "@/i18n/I18nProvider";
import { getServerTranslations } from "@/i18n/server";

import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getServerTranslations();
  return {
    title: t("app.title"),
    description: t("app.description"),
  };
}

export default async function RootLayout({ children }: { children: ReactNode }) {
  const { locale } = await getServerTranslations();

  return (
    <html lang={locale}>
      <body>
        <I18nProvider locale={locale}>
          <AppShell>{children}</AppShell>
        </I18nProvider>
      </body>
    </html>
  );
}
