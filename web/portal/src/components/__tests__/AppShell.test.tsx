import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { render, screen } from "@testing-library/react";

import { AppShell } from "@/components/AppShell";
import { requirePortalSession } from "@/lib/auth";

vi.mock("@/lib/auth", () => ({
  requirePortalSession: vi.fn(),
  signOut: vi.fn(),
}));

describe("AppShell", () => {
  test("renders the compact Korean navigation without extra network work", async () => {
    vi.mocked(requirePortalSession).mockResolvedValue({
      mode: "development",
      viewerLabel: null,
    });
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    render(await AppShell({ children: <p>작업 영역</p> }));

    expect(screen.getByRole("navigation", { name: "주요 메뉴" })).toBeVisible();
    expect(screen.getByRole("link", { name: "스튜디오" })).toHaveAttribute(
      "href",
      "/studio",
    );
    expect(screen.getByRole("link", { name: "레지스트리" })).toHaveAttribute(
      "href",
      "/registry",
    );
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  test("keeps authenticated session controls available in the mobile layout", async () => {
    vi.mocked(requirePortalSession).mockResolvedValue({
      mode: "entra",
      viewerLabel: "reviewer@example.com",
    });

    render(await AppShell({ children: <p>작업 영역</p> }));

    expect(screen.getByText("reviewer@example.com")).toBeVisible();
    expect(screen.getByRole("button", { name: "로그아웃" })).toBeVisible();

    const css = readFileSync(
      resolve(process.cwd(), "src/app/globals.css"),
      "utf8",
    );
    const mobileStyles = css.match(
      /@media \(max-width: 720px\) \{([\s\S]*?)\n\}/,
    )?.[1];

    expect(mobileStyles).toBeDefined();
    expect(mobileStyles).not.toMatch(
      /\.sidebar-footer\s*\{[^}]*display:\s*none/,
    );
  });
});
