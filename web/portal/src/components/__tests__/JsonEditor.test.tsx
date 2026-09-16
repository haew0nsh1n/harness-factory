import { fireEvent, render, screen } from "@testing-library/react";

import { JsonEditor } from "@/components/JsonEditor";

describe("JsonEditor", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("stops save when edited document is invalid json", () => {
    const onSave = vi.fn();

    render(
      <JsonEditor
        label="Workflow"
        value={{ name: "draft-flow" }}
        onSave={onSave}
      />,
    );

    fireEvent.change(screen.getByLabelText("워크플로우 JSON"), {
      target: { value: "{not-json" },
    });
    fireEvent.click(screen.getByRole("button", { name: "워크플로우 저장" }));

    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText(/워크플로우 JSON이 올바르지 않습니다:/i)).toBeInTheDocument();
  });

  test("never renders password or token fields", () => {
    render(
      <JsonEditor
        label="Catalog"
        value={{ tools: [] }}
        onSave={vi.fn()}
      />,
    );

    expect(screen.queryByLabelText(/password|token|credential/i)).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/password|token|credential/i)).not.toBeInTheDocument();
  });

  test("identifies the specific editor when json is invalid", () => {
    render(
      <JsonEditor
        label="Profile"
        value={{ name: "customer-profile" }}
        onSave={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText("프로필 JSON"), {
      target: { value: "{bad-json" },
    });
    fireEvent.click(screen.getByRole("button", { name: "프로필 저장" }));

    expect(screen.getByText(/프로필 JSON이 올바르지 않습니다:/i)).toBeInTheDocument();
  });
});
