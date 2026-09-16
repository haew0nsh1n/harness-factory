# Studio Visual Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing portal a polished, accessible consultant workspace without inventing an interview backend.

**Architecture:** Retain Next.js routing, the authenticated server shell, and existing client/API contracts. Add a consistent visual system and reusable workspace components; phase 3 will supply their live interview data.

**Tech Stack:** React 19, Next.js 15, TypeScript, CSS, Vitest/Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-15-studio-interview-cli-design.md`

## Global Constraints

- This is phase 1; finish before CLI distribution, then live interviews/forms.
- Every implementation agent uses `gpt-5.6-sol` and the globally installed `frontend-design` skill.
- Preserve existing APIs, role gates, approvals, validation, registry operations, and advanced JSON editing.
- Canvas `#F3F6F8`, surface `#FFFFFF`, ink `#172B3A`, muted `#526775`, action `#087F83`, border `#D4DFE5`.
- Korean user-facing copy across touched workflows; technical identifiers remain unchanged.
- No fake conversation, fake metrics, remote font/image dependencies, or enabled dead-end buttons.
- Keyboard focus, semantic labels, reduced motion, and 320px-width support are required.
- Never turn a model suggestion or visual status into approval or verification.
- Add required commit trailers; commit only owned files. Do not amend existing commits.

## File Structure

- `web/portal/src/app/globals.css`: design tokens and shared responsive primitives.
- `web/portal/src/components/AppShell.tsx`: authenticated navigation and page frame.
- `web/portal/src/components/{DashboardPageContent,StudioPageContent,StudioDesignPageContent,RegistryPageContent,RegistryDetailPageContent,StatusBadge,JsonEditor}.tsx`: real existing views.
- `web/portal/src/components/studio/{InterviewWorkspace,EvidenceRail,StageProgress}.tsx`: typed presentational components.
- `web/portal/src/components/studio/__tests__/InterviewWorkspace.test.tsx`: interaction/accessibility contract.
- `web/portal/playwright.config.ts`, `web/portal/e2e/studio-layout.spec.ts`: browser coverage and screenshots.
- `web/portal/package.json`, `web/portal/package-lock.json`: browser test tooling only if missing.

### Task 1: Cohesive shell and existing screens

**Files:** Modify the existing shell, styles, and view components listed above; update their existing tests and add `components/__tests__/AppShell.test.tsx`.

**Interfaces:**
- Consume the unchanged `api<T>()`, `apiRaw<T>()`, and `HarnessDesign`/registry DTOs in `src/lib`.
- Preserve component export names and URLs; change presentation and copy only.
- Shared classes include `workspace-panel`, `workspace-heading`, `button-primary`, `button-secondary`, and `field`.

- [ ] **Write regression expectations before redesigning.** Update label assertions deliberately; assert preserved actions and real empty/error states. Add a shell test with mocked `requirePortalSession` and no extra network work:

```tsx
expect(screen.getByRole("navigation", { name: "주요 메뉴" })).toBeVisible();
expect(screen.getByRole("link", { name: "스튜디오" })).toHaveAttribute("href", "/studio");
```

For Studio detail, retain tests that save modified JSON, validate, submit exact-digest approval, and queue a build. For registry, retain search/version/manifest/review behavior.

- [ ] **Run targeted tests red.**

```bash
cd web/portal && npm test -- src/components src/app
```

Expected: new copy/navigation assertions fail before changes; record unrelated baseline failures separately.

- [ ] **Implement the visual system and apply it to real content.** Start from:

```css
:root {
  --hf-canvas: #f3f6f8;
  --hf-surface: #ffffff;
  --hf-ink: #172b3a;
  --hf-muted: #526775;
  --hf-action: #087f83;
  --hf-border: #d4dfe5;
}
.workspace-panel { min-width: 0; background: var(--hf-surface); }
:focus-visible { outline: 3px solid var(--hf-action); outline-offset: 3px; }
```

Use system font stacks from the spec, explicit button variants, readable labels,
quiet borders, clear hierarchy, and compact navigation. Make status text map
to the same underlying status values; do not translate API values themselves.
Avoid inline raw status-to-authority claims. Preserve error details and pending
button behavior. Adjust all connected screens rather than creating an isolated
pretty landing page.

- [ ] **Run affected tests and typecheck, then commit owned files.**

```bash
cd web/portal && npm test -- src/components src/app && npm run typecheck
```

Commit subject: `feat: refresh portal workspace visual system`.

### Task 2: Evidence workspace and browser validation

**Files:** Create the three `components/studio` components and their tests; add Playwright config/spec; integrate shared layout into Studio detail without claiming interview functionality exists.

**Interfaces:**

```ts
export interface EvidenceItem {
  id: string;
  statement: string;
  sourceTurnId?: string;
  kind: "confirmed" | "assumption" | "unknown" | "proposed";
}
export interface InterviewWorkspaceProps {
  title: string;
  stage: string;
  evidence: EvidenceItem[];
  conversation: React.ReactNode;
  composer: React.ReactNode;
  onConfirm?: (id: string) => void;
}
```

`EvidenceRail` is presentational; its optional `onConfirm` calls an owner callback
and never mutates evidence internally. `StageProgress` names genuine SDLC stages,
not decorative sequential numbers. Export `InterviewWorkspace` as the phase-3
integration surface.

- [ ] **Write failing evidence and keyboard tests.**

```tsx
const onConfirm = vi.fn();
render(<EvidenceRail items={[{
  id: "fact-1", statement: "리뷰에서 재작업이 발생함", kind: "proposed",
}]} onConfirm={onConfirm} />);
fireEvent.click(screen.getByRole("button", { name: "사실 확인" }));
expect(onConfirm).toHaveBeenCalledWith("fact-1");
expect(screen.queryByText("확인 완료")).not.toBeInTheDocument();
```

Test empty evidence, safe rendering of HTML-like strings, mobile tab semantics,
and that changing the active tab does not erase composer content.

- [ ] **Run new component tests red.**

```bash
cd web/portal && npm test -- src/components/studio
```

- [ ] **Build the evidence rail and responsive layout.** Desktop columns are
navigation, conversation, evidence. Below tablet width use named tabs with
proper controls/panels. Render only actual profile facts on existing design
pages; label empty/unavailable interview state honestly. Do not introduce
frontend-owned approvals or unpersisted synthetic conversation.

- [ ] **Add browser coverage and capture actual layouts.** Add
`@playwright/test` to dev dependencies if absent, install its Chromium browser
only when needed, and use a dedicated loopback test port. The Playwright web
server starts the portal in explicit development mode; intercept only API
fixture requests and clearly label these tests as mocked visual coverage.

```ts
for (const width of [320, 768, 1440]) {
  test(`studio fits ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/studio");
    await expect(page.getByRole("heading", { name: "스튜디오" })).toBeVisible();
    expect(await page.evaluate(() =>
      document.documentElement.scrollWidth <= window.innerWidth
    )).toBe(true);
    await page.screenshot({ path: test.info().outputPath(`studio-${width}.png`), fullPage: true });
  });
}
```

Add fixtures for a populated studio and API failure. Keyboard-tab through
navigation and a real action; verify no hidden mobile sidebar traps focus.
Review screenshots and refine spacing/typography if the evidence workspace
looks like a generic dashboard. Keep screenshots out of source unless a test
snapshot is intentionally approved; report artifact paths.

- [ ] **Run portal checks, document the visual boundary, and commit.**

```bash
cd web/portal && npm test && npm run typecheck && npm run build && npx playwright test
```

Commit subject: `feat: add responsive studio evidence workspace`.

## Handoff

Continue with `2026-09-15-cli-distribution.md`. The live conversation is not
implemented in this phase. Keep workspace interfaces stable for phase 3.
