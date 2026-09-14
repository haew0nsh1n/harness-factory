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

    fireEvent.change(screen.getByLabelText("Workflow JSON"), {
      target: { value: "{not-json" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save Workflow" }));

    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText(/Workflow JSON is invalid:/i)).toBeInTheDocument();
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

    fireEvent.change(screen.getByLabelText("Profile JSON"), {
      target: { value: "{bad-json" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save Profile" }));

    expect(screen.getByText(/Profile JSON is invalid:/i)).toBeInTheDocument();
  });
});
