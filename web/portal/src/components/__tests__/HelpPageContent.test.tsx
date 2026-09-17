import { render, screen, within } from "@testing-library/react";

import { HelpPageContent } from "@/components/HelpPageContent";

describe("HelpPageContent", () => {
  test("shows the workflow steps in order", () => {
    render(<HelpPageContent />);

    expect(
      screen.getByRole("heading", { name: "Harness Factory 사용법" }),
    ).toBeInTheDocument();

    const flow = screen.getByRole("list", { name: "작업 흐름" });
    const steps = within(flow)
      .getAllByRole("listitem")
      .map((item) => item.querySelector(".help-flow-label")?.textContent);
    expect(steps).toEqual([
      "인터뷰",
      "디자인",
      "검증·승인",
      "빌드",
      "레지스트리",
      "설치",
    ]);
  });

  test("explains roles and lists the referenced skills with source and license", () => {
    render(<HelpPageContent />);

    expect(
      screen.getByRole("heading", { name: "역할별 권한" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/author —/)).toBeInTheDocument();

    expect(screen.getByText("hf-clarify")).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: "mattpocock/skills" }).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByRole("link", { name: "garrytan/gstack" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("MIT").length).toBe(6);
  });
});
