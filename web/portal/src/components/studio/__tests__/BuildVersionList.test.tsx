import { render, screen } from "@testing-library/react";

import { BuildVersionList } from "@/components/studio/BuildVersionList";
import type { BuildJob } from "@/lib/types";

function buildFixture(overrides: Partial<BuildJob>): BuildJob {
  return {
    id: "build-x",
    organization_id: "org-acme",
    design_id: "design-1",
    design_digest: "a".repeat(64),
    status: "succeeded",
    attempts: 1,
    artifact_key: "key",
    artifact_digest: "b".repeat(64),
    error_code: null,
    created_at: "2026-09-14T00:00:00Z",
    started_at: "2026-09-14T00:00:01Z",
    finished_at: "2026-09-14T00:00:02Z",
    updated_at: "2026-09-14T00:00:02Z",
    ...overrides,
  };
}

describe("BuildVersionList", () => {
  test("renders nothing when there are no builds", () => {
    const { container } = render(<BuildVersionList builds={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  test("shows at most the three most recent versions with short digests", () => {
    const builds = [
      buildFixture({ id: "b1", design_digest: "1".repeat(64) }),
      buildFixture({ id: "b2", design_digest: "2".repeat(64), status: "failed" }),
      buildFixture({ id: "b3", design_digest: "3".repeat(64) }),
      buildFixture({ id: "b4", design_digest: "4".repeat(64), status: "queued" }),
    ];

    render(<BuildVersionList builds={builds} />);

    expect(
      screen.getByRole("heading", { name: "산출물 버전" }),
    ).toBeInTheDocument();
    expect(screen.getByText("111111111111")).toBeInTheDocument();
    expect(screen.getByText("222222222222")).toBeInTheDocument();
    expect(screen.getByText("333333333333")).toBeInTheDocument();
    expect(screen.queryByText("444444444444")).not.toBeInTheDocument();
  });
});
