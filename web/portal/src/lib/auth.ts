import NextAuth from "next-auth";
import MicrosoftEntraID from "next-auth/providers/microsoft-entra-id";
import { redirect } from "next/navigation";

declare module "next-auth/jwt" {
  interface JWT {
    accessToken?: string;
  }
}

export type PortalAuthMode = "development" | "entra";

const authMode: PortalAuthMode =
  process.env.NEXT_PUBLIC_HF_AUTH_MODE === "entra" ? "entra" : "development";

const entraConfigured =
  typeof process.env.AUTH_MICROSOFT_ENTRA_ID_ID === "string" &&
  process.env.AUTH_MICROSOFT_ENTRA_ID_ID.length > 0 &&
  typeof process.env.AUTH_MICROSOFT_ENTRA_ID_SECRET === "string" &&
  process.env.AUTH_MICROSOFT_ENTRA_ID_SECRET.length > 0 &&
  typeof process.env.AUTH_MICROSOFT_ENTRA_ID_ISSUER === "string" &&
  process.env.AUTH_MICROSOFT_ENTRA_ID_ISSUER.length > 0;

const providers =
  authMode === "entra" && entraConfigured
    ? [
        MicrosoftEntraID({
          clientId: process.env.AUTH_MICROSOFT_ENTRA_ID_ID,
          clientSecret: process.env.AUTH_MICROSOFT_ENTRA_ID_SECRET,
          issuer: process.env.AUTH_MICROSOFT_ENTRA_ID_ISSUER,
        }),
      ]
    : [];

export const { handlers, auth, signOut } = NextAuth({
  trustHost: true,
  session: { strategy: "jwt" },
  providers,
  callbacks: {
    async jwt({ token, account }) {
      if (typeof account?.access_token === "string") {
        token.accessToken = account.access_token;
      }
      return token;
    },
    async session({ session }) {
      return session;
    },
  },
});

export function getPortalAuthMode(): PortalAuthMode {
  return authMode;
}

export function isDevelopmentMode(): boolean {
  return authMode === "development";
}

export function isEntraMode(): boolean {
  return authMode === "entra";
}

export async function requirePortalSession(): Promise<{
  mode: PortalAuthMode;
  viewerLabel: string | null;
}> {
  if (isDevelopmentMode()) {
    return { mode: "development", viewerLabel: null };
  }

  if (!entraConfigured) {
    throw new Error("Microsoft Entra authentication is not fully configured.");
  }

  const session = await auth();
  if (!session?.user) {
    redirect("/api/auth/signin");
  }

  return {
    mode: "entra",
    viewerLabel: session.user.name ?? session.user.email ?? "Signed in",
  };
}
