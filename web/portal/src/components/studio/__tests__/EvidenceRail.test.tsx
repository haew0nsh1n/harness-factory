import { fireEvent, render, screen } from "@testing-library/react";

import { EvidenceRail } from "@/components/studio/EvidenceRail";

describe("EvidenceRail", () => {
  test("delegates proposed fact confirmation without mutating the item", () => {
    const onConfirm = vi.fn();

    render(
      <EvidenceRail
        items={[
          {
            id: "fact-1",
            statement: "리뷰에서 재작업이 발생함",
            kind: "proposed",
          },
        ]}
        onConfirm={onConfirm}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "사실 확인" }));

    expect(onConfirm).toHaveBeenCalledWith("fact-1");
    expect(screen.queryByText("확인 완료")).not.toBeInTheDocument();
  });

  test("distinguishes an empty evidence rail from an error", () => {
    render(<EvidenceRail items={[]} />);

    expect(screen.getByText("저장된 근거가 없습니다.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  test("renders HTML-like statements as plain text", () => {
    render(
      <EvidenceRail
        items={[
          {
            id: "unknown-1",
            statement: '<img src=x onerror="alert(1)">',
            kind: "unknown",
          },
        ]}
      />,
    );

    const statement = screen.getByText(/onerror=/);
    expect(statement.textContent).toContain("<img src=x");
    expect(statement.querySelector("img")).toBeNull();
  });

  test("renders every source turn as its own accessible link", () => {
    render(
      <EvidenceRail
        items={[
          {
            id: "fact-1",
            statement: "여러 답변에서 확인됨",
            kind: "confirmed",
            sourceTurnIds: ["turn-1", "turn-2"],
          },
        ]}
      />,
    );

    expect(screen.getByRole("link", { name: "출처 1: turn-1" })).toHaveAttribute(
      "href",
      "#turn-turn-1",
    );
    expect(screen.getByRole("link", { name: "출처 2: turn-2" })).toHaveAttribute(
      "href",
      "#turn-turn-2",
    );
  });
});
