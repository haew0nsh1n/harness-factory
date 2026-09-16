import { fireEvent, render, screen, within } from "@testing-library/react";

import catalog from "../../../../../../catalog/catalog.json";
import profile from "../../../../../../examples/github-issue/profile.json";
import scenarios from "../../../../../../examples/github-issue/scenarios.json";
import workflow from "../../../../../../examples/github-issue/workflow.json";
import { StructuredDesignEditors } from "@/components/studio/StructuredDesignEditors";

describe("StructuredDesignEditors proposal review", () => {
  test("shows complete human-readable review content and keeps raw JSON in a closed disclosure", () => {
    render(
      <StructuredDesignEditors
        documents={{ profile, workflow, scenarios, catalog }}
        authoritativeCatalog={catalog}
        onChange={vi.fn()}
        readOnly
      />,
    );

    expect(screen.getByText("Example Team (fictional)")).toBeInTheDocument();
    expect(
      screen.getByText("Acceptance ambiguity is the selected bottleneck."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("A repository with a runnable test command will be available at execution time."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Authentication and repository access must be checked on the actual customer machine."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Reduce acceptance rework without automating publication authority."),
    ).toBeInTheDocument();
    expect(screen.getByText("Clarify acceptance criteria")).toBeInTheDocument();
    expect(screen.getByText("github.issue-read")).toBeInTheDocument();
    expect(screen.getByText("Human maintainer publishes the PR")).toBeInTheDocument();
    expect(screen.getByText("normal-handoff")).toBeInTheDocument();
    expect(screen.getByText("hf-clarify")).toBeInTheDocument();
    expect(
      screen.getByRole("textbox", { name: "프로필 전체 JSON 검토" }),
    ).not.toBeVisible();

    fireEvent.click(screen.getByText("디버그 JSON"));
    expect(
      (screen.getByRole("textbox", {
        name: "프로필 전체 JSON 검토",
      }) as HTMLTextAreaElement).value,
    ).toContain('"customer_id": "example-team"');
    expect(
      (screen.getByRole("textbox", {
        name: "워크플로 전체 JSON 검토",
      }) as HTMLTextAreaElement).value,
    ).toContain('"id": "issue-to-reviewed-pr"');
    expect(
      (screen.getByRole("textbox", {
        name: "시나리오 전체 JSON 검토",
      }) as HTMLTextAreaElement).value,
    ).toContain('"id": "normal-handoff"');
    expect(
      (screen.getByRole("textbox", {
        name: "승인 카탈로그 전체 JSON 검토",
      }) as HTMLTextAreaElement).value,
    ).toContain('"id": "hf-clarify"');
  });

  test("shows step IDs and explicit predecessor dependencies without opening JSON", () => {
    const planWithoutDependency = {
      ...workflow.steps[1],
      needs: [],
    };
    const documents = {
      profile,
      workflow: {
        ...workflow,
        steps: [workflow.steps[0], planWithoutDependency],
      },
      scenarios,
      catalog,
    };
    const { rerender } = render(
      <StructuredDesignEditors
        documents={documents}
        authoritativeCatalog={catalog}
        onChange={vi.fn()}
        readOnly
      />,
    );

    const planReview = within(
      screen.getByRole("listitem", { name: "plan 단계 검토" }),
    );
    expect(planReview.getByText("단계 ID").parentElement).toHaveTextContent(
      "단계 ID · plan",
    );
    expect(planReview.getByText("선행 단계").parentElement).toHaveTextContent(
      "선행 단계 · 없음",
    );

    rerender(
      <StructuredDesignEditors
        documents={{
          ...documents,
          workflow: {
            ...documents.workflow,
            steps: [
              workflow.steps[0],
              { ...planWithoutDependency, needs: ["clarify"] },
            ],
          },
        }}
        authoritativeCatalog={catalog}
        onChange={vi.fn()}
        readOnly
      />,
    );

    expect(
      within(screen.getByRole("listitem", { name: "plan 단계 검토" }))
        .getByText("선행 단계").parentElement,
    ).toHaveTextContent("선행 단계 · clarify");
    expect(
      screen.getByRole("textbox", { name: "워크플로 전체 JSON 검토" }),
    ).not.toBeVisible();
  });

  test("labels authoritative and saved catalog JSON as distinct sources", () => {
    const serverCatalog = {
      schema_version: 1,
      skills: [
        {
          id: "server-skill",
          description: "Current server catalog",
          inputs: [],
          outputs: [],
          effects: ["read"],
        },
      ],
    };
    const savedCatalog = {
      schema_version: 1,
      skills: [
        {
          id: "snapshot-skill",
          description: "Saved design snapshot",
          inputs: [],
          outputs: [],
          effects: ["local"],
        },
      ],
    };

    render(
      <StructuredDesignEditors
        documents={{ profile, workflow, scenarios, catalog: savedCatalog }}
        authoritativeCatalog={serverCatalog}
        onChange={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "server-skill" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "snapshot-skill" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("카탈로그 원문 JSON"));

    const serverJson = screen.getByRole("textbox", {
      name: "현재 서버 승인 카탈로그 전체 JSON 검토",
    }) as HTMLTextAreaElement;
    const snapshotJson = screen.getByRole("textbox", {
      name: "설계에 저장된 카탈로그 스냅샷 전체 JSON 검토",
    }) as HTMLTextAreaElement;
    expect(serverJson.value).toContain("server-skill");
    expect(serverJson.value).not.toContain("snapshot-skill");
    expect(snapshotJson.value).toContain("snapshot-skill");
    expect(snapshotJson.value).not.toContain("server-skill");
  });
});
