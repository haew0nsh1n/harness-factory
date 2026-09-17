import {
  analyzeDependencies,
  readProfileForm,
  updateDocumentField,
  updateProfileName,
} from "@/lib/designForms";

describe("design form adapters", () => {
  test("preserves every untouched and unmapped field during a form edit", () => {
    const profile = {
      schema_version: 1,
      customer_id: "acme",
      name: "Before",
      roles: ["author"],
      extension: { future: true },
      invalid_optional_shape: 42,
    };

    const updated = updateProfileName(profile, "After");

    expect(updated).toEqual({
      ...profile,
      name: "After",
    });
    expect(updateDocumentField(profile, "name", "After")).toEqual(updated);
  });

  test("reports invalid typed values instead of blanking them", () => {
    const result = readProfileForm({
      schema_version: 1,
      customer_id: "acme",
      name: 42,
    });

    expect(result.values.name).toBeNull();
    expect(result.errors.name).toMatch(/문자열/);
  });

  test("reports cycles and missing workflow nodes from actual dependency edges", () => {
    const result = analyzeDependencies({
      steps: [
        { id: "a", needs: ["b", "missing"] },
        { id: "b", needs: ["a"] },
      ],
    });

    expect(result.missing).toEqual([{ stepId: "a", dependencyId: "missing" }]);
    expect(result.cycles).toContainEqual(["a", "b", "a"]);
  });
});
