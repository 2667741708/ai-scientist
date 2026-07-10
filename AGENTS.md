# AGENTS.md - open-coscientist local notes

## Scope

This file is project-local guidance for `open-coscientist/`. Follow the root workspace `AGENTS.md` first, then use this file for implementation details inside this repository.

## Hypothesis Workbench Frontend Contract

The project hypotheses page is the main human review surface for generated hypotheses. It must let a researcher inspect, compare, translate, verify evidence, open references, discuss with project AI, move into experiment design, and draft reports without understanding backend internals.

Relevant frontend files:

- `webapp/src/features/hypotheses/HypothesisWorkspace.tsx`: page-level hypothesis review UI. Buttons such as `核验证据`, `查看详情`, decision checks, translation, project AI, experiment, and report drafting must open a visible panel or route with the selected hypothesis context.
- `webapp/src/features/evidence/ReferenceDrawer.tsx`: reference and evidence drawer. It should show citation map, support levels, knowledge-base support, experiment support, PDF parse actions, and evidence diagnostics.
- `webapp/src/lib/view-models/workbench.ts`: converts `RunRecord` into `ProjectViewModel`, `HypothesisCardViewModel`, and diagnostics. Backend fields should be normalized here before UI components render them.
- `webapp/src/types/workbench.ts`: frontend schema contract. Add stable typed fields here before using them in components.
- `webapp/src/pages/project-chat/ProjectKnowledgePage.tsx`: project AI surface. Links with `run`, `hypothesis`, and `intent=draft_report` should prefill a task-specific prompt instead of losing context.
- `webapp/src/features/reports/ReportsPanel.tsx`: local report drafting surface. It may generate a deterministic draft from existing run data and provide a project-AI route for live report writing.

## Backend Integration Boundary

Do not fetch backend data directly inside small visual components. Prefer this flow:

```text
FastAPI endpoint -> lib/api client -> workbench context/query -> view-model -> UI component
```

For evidence and citation features, preserve these distinctions:

- `citation_mismatch`: a citation/source claim does not align with the hypothesis claim. Show the source or support-level entry that caused the warning.
- `limited_fulltext`: evidence is abstract-only, metadata-only, public HTML, landing page, or otherwise weak. Do not present it as parsed fulltext support.
- `parsed_fulltext` and `experimental_data`: stronger support levels, but still require user inspection before report export.

For report drafting, use the existing research chat intent `draft_report` or the research skills API before adding a new report-specific backend. Relevant skills include `evidence-grounding-rubric`, `citation-provenance-qa`, `falsifiability-review`, and `experiment-design-checklist`.

## UI Rules

- Every button that promises to open evidence, details, process, or checks must either open an inline panel, open the reference drawer, or navigate to a route carrying `run_id` and selected hypothesis context.
- Do not expose provider keys, raw JSON, stack traces, local absolute paths, or internal run IDs in normal user-facing copy unless the user explicitly opens an expert/debug surface.
- Demo or synthetic records must remain labeled as demo/history and cannot be described as real scientific evidence.
