import { render, screen } from "@testing-library/react";

import { StageProgress } from "@/components/studio/StageProgress";

describe("StageProgress", () => {
  test("names genuine SDLC stages and identifies the active stage", () => {
    render(<StageProgress stage="testing" />);

    expect(screen.getByRole("navigation", { name: "SDLC 단계" })).toBeInTheDocument();
    expect(screen.getByText("발견")).toBeInTheDocument();
    expect(screen.getByText("계획")).toBeInTheDocument();
    expect(screen.getByText("구현")).toBeInTheDocument();
    expect(screen.getByText("테스트")).toHaveAttribute("aria-current", "step");
    expect(screen.getByText("검토")).toBeInTheDocument();
    expect(screen.getByText("릴리스")).toBeInTheDocument();
    expect(screen.getByText("운영")).toBeInTheDocument();
  });

  test("does not claim a current stage when interview progress is unavailable", () => {
    render(<StageProgress stage="unavailable" />);

    expect(screen.getByText("인터뷰 단계 미제공")).toBeInTheDocument();
    expect(screen.queryByLabelText("현재 단계")).not.toBeInTheDocument();
  });

  test("shows only the selected SDLC stages and treats summary as terminal", () => {
    render(
      <StageProgress
        stage="summary"
        selectedStages={["planning", "implementation", "review"]}
      />,
    );

    expect(screen.queryByText("발견")).not.toBeInTheDocument();
    expect(screen.getByText("계획")).toBeInTheDocument();
    expect(screen.getByText("구현")).toBeInTheDocument();
    expect(screen.getByText("검토")).toBeInTheDocument();
    expect(screen.queryByText("테스트")).not.toBeInTheDocument();
    expect(screen.getByText("선택한 단계 완료")).toBeInTheDocument();
  });
});
