import { render, screen } from "@testing-library/react";

import { SdlcScope } from "@/components/studio/SdlcScope";

describe("SdlcScope", () => {
  test("shows every SDLC stage and marks only the selected ones", () => {
    render(<SdlcScope selected={["planning", "review"]} />);

    for (const label of [
      "발견",
      "계획",
      "구현",
      "테스트",
      "검토",
      "릴리스",
      "운영",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }

    const selected = screen
      .getAllByRole("listitem")
      .filter((item) => item.getAttribute("data-selected") === "true")
      .map((item) => item.textContent);
    expect(selected).toEqual(["계획", "검토"]);
  });

  test("marks nothing when the selection is empty", () => {
    render(<SdlcScope selected={[]} />);

    const selected = screen
      .getAllByRole("listitem")
      .filter((item) => item.getAttribute("data-selected") === "true");
    expect(selected).toHaveLength(0);
    expect(screen.getAllByRole("listitem")).toHaveLength(7);
  });
});
