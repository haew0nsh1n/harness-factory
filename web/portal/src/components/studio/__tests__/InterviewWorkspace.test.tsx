import { fireEvent, render, screen } from "@testing-library/react";

import { InterviewWorkspace } from "@/components/studio/InterviewWorkspace";

describe("InterviewWorkspace", () => {
  test("uses labelled tab controls and panels for mobile evidence views", () => {
    render(
      <InterviewWorkspace
        title="Acme 설계"
        stage="planning"
        evidence={[
          {
            id: "fact-1",
            statement: "GitHub 이슈를 사용함",
            kind: "confirmed",
          },
          {
            id: "proposal-1",
            statement: "검토 전에 승인된 브리프를 요구함",
            kind: "proposed",
          },
        ]}
        conversation={<p>인터뷰는 아직 제공되지 않습니다.</p>}
        composer={<textarea aria-label="답변" defaultValue="작성 중인 답변" />}
      />,
    );

    const evidenceTab = screen.getByRole("tab", { name: "근거" });
    const proposalTab = screen.getByRole("tab", { name: "제안" });

    expect(evidenceTab).toHaveAttribute("aria-selected", "true");
    const evidencePanel = screen.getByRole("tabpanel", { name: "근거" });
    expect(evidenceTab).toHaveAttribute("aria-controls", evidencePanel.id);
    expect(proposalTab.getAttribute("aria-controls")).not.toBe(evidencePanel.id);

    fireEvent.click(proposalTab);

    expect(proposalTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: "제안" })).toHaveTextContent(
      "검토 전에 승인된 브리프를 요구함",
    );
  });

  test("switching tabs does not erase composer content", () => {
    render(
      <InterviewWorkspace
        title="Acme 설계"
        stage="testing"
        evidence={[]}
        conversation={<p>대화 없음</p>}
        composer={<textarea aria-label="답변" defaultValue="" />}
      />,
    );

    const composer = screen.getByLabelText("답변");
    fireEvent.change(composer, { target: { value: "보존해야 하는 답변" } });
    fireEvent.click(screen.getByRole("tab", { name: "제안" }));
    fireEvent.click(screen.getByRole("tab", { name: "근거" }));

    expect(screen.getByLabelText("답변")).toHaveValue("보존해야 하는 답변");
  });

  test("supports keyboard activation of evidence tabs", () => {
    render(
      <InterviewWorkspace
        title="Acme 설계"
        stage="review"
        evidence={[]}
        conversation={<p>대화 없음</p>}
        composer={<p>작성 기능 없음</p>}
      />,
    );

    const evidenceTab = screen.getByRole("tab", { name: "근거" });
    evidenceTab.focus();
    fireEvent.keyDown(evidenceTab, { key: "ArrowRight" });

    expect(screen.getByRole("tab", { name: "제안" })).toHaveFocus();
    expect(screen.getByRole("tab", { name: "제안" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });
});
