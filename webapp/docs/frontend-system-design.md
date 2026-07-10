# Open Co-Scientist Frontend System Design

This document is the reusable frontend design-system contract for `open-coscientist/webapp/`.
It consolidates the project-relevant parts of the pasted frontend design principles into an implementation guide for this research workbench.

Companion standard:

```text
frontend-development-standards.md
```

Use the companion file for the reusable foundations/components/patterns/page-building method. Use this file for the project-specific research workbench contract, information hiding, evidence workflow, and AI-result semantics.

The goal is not to make a pretty page. The goal is to let expert users complete real research tasks with minimal cognitive load while preserving auditability, traceability, and long-term UI consistency.

## 1. Product Position

`open-coscientist/webapp/` is a knowledge work platform for AI-assisted research. It is not a PPT-style demo, marketing site, backend console, model-provider dashboard, or raw agent trace viewer.

The frontend exposes research workbench destinations:

```text
研究主页
研究流程
研究工具
资料库
研究产出
运行准备
```

The frontend hides implementation machinery by default:

```text
Agent
Workflow internals
Memory
Vector DB
MCP
Tool call
Prompt
Provider key
Raw API
Run ID
Request ID
Repair command
Stack trace
```

Core rule:

```text
Expose tasks. Hide system complexity. Preserve auditability behind intentional user actions.
```

## 2. Framework Contract

Use the current project stack unless there is a strong local reason to change it:

```text
React 19
TypeScript
Vite
CSS design tokens in src/styles.css
lucide-react for icon buttons and navigation glyphs
FastAPI bridge at webapp/backend
```

Implementation rules:

- Prefer native React components and the existing CSS token system.
- Do not introduce a UI framework unless the repeated component surface justifies it.
- Do not add another icon library while `lucide-react` covers the metaphor.
- Do not create one-off color, spacing, radius, or shadow values in feature code.
- Extract repeated UI patterns only when they remove real duplication or clarify ownership.
- Keep real controls code-native. Do not ship static screenshots as UI.

## 3. Information Architecture

The IA is goal driven, not system driven.

Current top-level navigation:

```text
研究主页
研究流程
研究工具
资料库
研究产出
运行准备
```

Meaning:

| Nav | User Goal | Hidden System Capabilities |
| --- | --- | --- |
| 研究主页 | Find workflows, tools, active research, and data readiness quickly | run history stitching, output aggregation |
| 研究流程 | Move through literature review, hypothesis generation, experiment design, reports, and audit | project/run adaptation, hidden IDs |
| 研究工具 | Search task tools such as parsing, citation checks, translation, evidence drawers, templates, and exports | MCP, model calls, hidden service details |
| 资料库 | Manage papers, references, datasets, figures, notes, ingestion jobs, and provenance | MCP, PubMed/fulltext, citation map |
| 研究产出 | Revisit findings, experiment plans, and report drafts | result synthesis, export surface |
| 运行准备 | Inspect runtime readiness, roles, services, queues, audit, and expert controls | provider availability, diagnostics, health |

Role visibility:

- `运行准备` is an admin-only destination in the primary nav.
- Any secondary entry to `/admin`, including Home quick actions, tool cards, empty states, readiness rails, and generated page links, must follow the same role visibility rule.
- Researchers should see task-oriented unavailable/recovery guidance, not a default link that routes them into a permission denial.

`研究工具` can include an evidence tool workbench and long-running research controls when they are framed as user tasks:

- Evidence tools must ask for scope approval before file, web, browser, code, or experiment actions.
- Session search, source snapshots, web evidence, schedules, skills, and delegations should show task summaries by default.
- Internal IDs, artifact paths, `result_ref`, hashes, and stored payload details must stay behind explicit details/inspection controls.
- Schedule tick actions may create ready tasks; they must not silently execute external tools or experiments.
- Delegation surfaces may create planned multi-role reviews; model execution still requires explicit approval and provider readiness.
- Default tool copy should translate implementation terms into user task language: `workflow` -> research task flow, `skills` -> method templates, `phases` -> applicable stages, `agents` -> review roles/subtasks, `SQLite provenance` -> local audit record, `approval guardrail` -> pre-execution confirmation.

Project-scoped secondary workflow:

```text
Projects/:projectId
├── Papers
├── Hypotheses
├── Experiments
└── Reports
```

Navigation anti-patterns:

- Do not expose `Agent`, `Workflow`, `Model`, `Tool`, `Prompt`, `MCP`, `Memory`, `Vector DB` as ordinary user navigation.
- Do not make users understand the agent graph before they can start a task.
- Do not spread the same task across multiple competing panels.

Future project knowledge Q&A:

- A project understanding assistant may be added as `项目问答` or `项目知识助手`.
- It should help researchers ask what this project can do, how to run it, which pages own which tasks, and which capabilities are implemented, demo-only, or planned.
- Do not name the user entry `Memory`, `Vector DB`, `MCP`, `Agent Chat`, or `Tool Call`.
- It is separate from hypothesis generation. It must not present project documentation or demo outputs as scientific evidence.

## 4. Layout Framework

Default desktop shell:

```text
App Shell
├── Left Nav Rail
├── Topbar
│   ├── Project title
│   └── Research goal summary
└── Main Work Surface
    ├── Current task panel
    └── Result / detail surface
```

Optional secondary surfaces:

```text
Drawer: references, detailed source evidence, contextual inspection
Disclosure: process log, ranking basis, quality signals
Expert Settings: provider/model/literature options
Modal: short blocking decision only
Toast: short system feedback only
```

Login, Data, and runtime-readiness page rules:

- Login is an entry surface for workspace and role selection, not a marketing hero.
- Home is the command center for workflows and tools, not a passive recent-output board.
- Data is an asset control surface. Use tables, filters, status chips, and detail drawers; do not expose raw citation maps by default.
- Data must support named literature libraries when multiple research directions need isolated evidence scope. The default state shows library name, paper count, parse count, chunk count, current write target, and one clear next action. Library internals, SQLite IDs, raw MCP payloads, local paths, and parse artifact paths stay behind explicit detail/audit entries.
- Literature discovery belongs on Data as a task flow: researcher selects a target literature library, enters a search query, authorizes the literature MCP search, reviews candidate paper cards, and parses a confirmed PDF into the selected library. If MCP is unavailable, the UI must show a limited state and offer PDF upload or PDF URL parsing; it must not present ordinary web fallback or model guesses as completed literature search.
- Single-paper interpretation belongs on Data as a task form with `PDF_PATH` and `OUTPUT_NAME`, plus clear loading, disabled, success, and error states. The user-facing result should list generated files, media count, Markdown image-link validation, DOI, BibTeX source, and plain-text source boundary; do not expose raw parser traces.
- Runtime readiness is a control plane. It may show role, readiness, service, queue, and audit state, but default copy must stay product-facing and hide endpoint, env var, repair command, raw provider detail, and internal IDs. Raw diagnostics must require an explicit expert/debug entry such as `/api/health/debug`.
- Workflows and Tools are user-goal destinations. They should route into Workspace/Data/Outputs/runtime readiness rather than exposing agent graph internals as navigation.
- Range controls that describe model search budgets, such as minimum and maximum references per hypothesis, must keep each user-controlled value on a stable full-scale slider. Do not change one slider's visual min/max from the other slider's current value; normalize the submitted execution range instead.
- Every live run must expose `safety_gate`, `citation_provenance_qa`, and `expert_feedback` state in the data layer. The default UI may summarize these as readiness, evidence quality, and expert review status, but raw citation maps, repair hints, endpoints, and internal IDs stay behind deliberate disclosure.
- Compatibility pages such as legacy Library/Settings implementations are not design sources when the router redirects them into Data/Admin. Do not copy old control patterns from inactive routes.
- API and view-model layers must provide safe user-facing error messages. Page components must not display raw HTTP response text, JSON detail, provider errors, endpoints, request IDs, tracebacks, or unsanitized `error.message` by default.

Layout rules:

- The first viewport must answer: where am I, what task is active, what is the next action.
- Main work surfaces should be full-width task regions, not a nested stack of presentation cards.
- Avoid card inside card. Cards are for repeated objects such as hypotheses, papers, tasks, or experiments.
- Long details should move into drawers, detail tabs, or disclosures.
- Right panels and drawers should be contextual, not always-on noise.

Responsive behavior:

```text
>= 1280px: nav rail + main work surface, optional drawer
960px - 1279px: compact nav + main, drawer overlays
640px - 959px: single-column task flow
< 640px: reading and light operations only; hide dense diagnostics behind drawers
```

## 5. Information Hiding

Every control, window, drawer, detail panel, modal, popover, toast, and report surface must follow progressive disclosure.

Default state shows only:

```text
Title
Short summary
Current status
Primary action
One obvious next step
```

Hidden until user intent:

```text
Reference list
Citation map
Agent trace
Raw metrics
Ranking details
Review feedback
Provider diagnostics
API/config state
Internal IDs
Local absolute paths
Artifact paths
Content hashes
Raw response text
Long explanations
Raw JSON
```

Required entry examples:

| Hidden Information | User Intent Entry |
| --- | --- |
| Hypothesis references | `参考文献` button on the hypothesis card |
| Hypothesis Chinese translation | `翻译中文` action in the selected hypothesis panel |
| Process trace | `查看过程与证据` disclosure |
| Ranking/tournament | `排序依据` tab after disclosure |
| Quality metrics | `质量信号` tab after disclosure |
| Provider/model/Think mode controls | `专家设置` |
| Reference count range | `专家设置`, then reflected in the reference drawer |
| Error recovery | local task-level feedback, not global debug dump |
| Parse run / chunk / evidence IDs | evidence drawer, artifact detail, or expert inspection |
| Tool `target_ref` / `result_ref` | tool result details, never default list copy |
| Project knowledge source hash, chunk id, raw excerpt, or index scan log | source drawer or expert inspection |

Information hiding is not deletion. Audit fields remain in data structures and discoverable UI surfaces.

## 6. Design Tokens

The canonical runtime tokens live in `src/styles.css`. New components must use these token families.

### Spacing

Use the current 8px grid:

```css
--space-xs: 8px;
--space-sm: 16px;
--space-md: 24px;
--space-lg: 32px;
--space-xl: 48px;
```

Rules:

- Internal micro gaps: `4px` only for tight text relationships.
- Control and card gaps: `--space-xs` or `--space-sm`.
- Section gaps: `--space-md` or `--space-lg`.
- Large page rhythm: `--space-xl`.
- Do not create random `margin: 13px`, `padding: 18px`, or viewport-scaled font spacing.

### Grid

```css
--grid-columns-mobile: 4;
--grid-columns-tablet: 8;
--grid-columns-desktop: 12;
--grid-gutter: var(--space-sm);
--grid-margin: var(--space-md);
--layout-max-width: 1584px;
```

Rules:

- Use grid tracks and minmax constraints for panels, lists, and repeated cards.
- State changes must not alter grid track sizes.
- Hover and active states may change color, border, shadow, or small transform, but must not cause layout shift.

### Radius

```css
--radius-control: 8px;
--radius-panel: 8px;
```

Rules:

- Controls and panels use 8px radius.
- Avoid oversized rounded rectangles unless a component requires a pill shape.
- Icon buttons should use the same control radius unless there is an established local variant.

### Control Height

```css
--control-height-sm: 40px;
--control-height-md: 48px;
```

Rules:

- Desktop control target: at least 40px.
- Mobile/touch target: at least 44px when practical.
- Loading state must preserve the same height.
- Disabled state must preserve the same dimensions.

## 7. Color System

Use semantic color tokens. Do not name or reason about colors as decorative blue/gray/green variants in component code.

Current token family:

```css
--color-page-bg: #f6f7f8;
--color-surface-default: #ffffff;
--color-surface-muted: #f2f4f5;
--color-surface-raised: #fbfcfd;

--color-primary-default: #0a7d87;
--color-primary-hover: #075f66;
--color-primary-subtle: #e5f7f8;

--color-text-primary: #0b0d0f;
--color-text-secondary: #52606b;
--color-text-muted: #66717b;

--color-border-default: #e1e6ea;
--color-border-strong: #cbd4db;

--color-success-default: #18794e;
--color-success-subtle: #e9f7ef;
--color-warning-default: #9a5b10;
--color-warning-subtle: #fff5e7;
--color-danger-default: #b42318;
--color-danger-subtle: #fff1ef;
--color-focus-ring: rgba(10, 125, 135, 0.24);
```

Usage:

| Token Role | Use |
| --- | --- |
| Primary | one main action, selected nav, focused interaction |
| Surface | panels, drawers, form controls |
| Surface muted | subtle section background, inactive surface |
| Text primary | headings and important content |
| Text secondary/muted | descriptions, metadata, helper text |
| Border default | normal separation |
| Border strong | control borders and active dividers |
| Success | completed state |
| Warning | recoverable limitation or attention |
| Danger | destructive or irreversible action |
| Focus ring | keyboard focus outline |

Rules:

- A page should not be dominated by unrelated accent colors.
- Red is reserved for destructive or serious error semantics.
- Warning should explain limitation and recovery, not merely decorate.
- Focus outline must be visible and pass contrast expectations.
- Body text should target WCAG AA contrast: at least 4.5:1 for normal text.

## 8. Typography

Current font stack:

```css
"Geist", Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
```

Recommended type scale for this project:

```text
Display: 32px, tight line-height, project or empty-state hero only
H1: 28px - 32px, page/project title
H2: 20px - 24px, current task or major section
H3: 15px - 18px, card/detail title
Body: 13px - 15px, regular content
Caption: 12px - 13px, metadata and helper text
Small: 11px - 12px, dense tags and metric chips
```

Rules:

- Do not use viewport-scaled font sizes.
- Letter spacing stays `0` unless a tiny uppercase label needs explicit treatment.
- Compact panels, cards, sidebars, and toolbars use smaller type than page headers.
- Button and control text must be deliberately sized, never browser-default.
- Long text in buttons/cards must wrap or clamp without breaking layout.

## 9. Component Contract

### Button

Variants:

```text
Primary: one page-level main action
Secondary: ordinary task action
Ghost: low-priority action
Danger: destructive action
Icon Button: compact tool action
```

Rules:

- Button text uses verbs: `生成候选假设`, `上传论文`, `导出报告`, `运行实验`.
- Avoid vague labels such as `执行`, `提交`, `处理`, `打开`.
- Must implement default, hover, active, disabled, loading, and focus-visible states.
- Loading must use stable icon/text slots and `aria-busy` where appropriate.
- Button size must not change across states.
- Icon-only help buttons follow the `info-trigger` pattern: stable hit target, visible focus ring, `aria-label`, and hover/focus tooltip. They explain context only; they must not hide primary actions, long documentation, error recovery, or expert settings.
- Admin-only actions and links must respect role visibility everywhere, not just in the primary nav.

### Input, Textarea, Select

Rules:

- Always pair with a visible label.
- Helper text should explain task impact, not backend field names.
- Advanced fields go behind `专家设置`.
- Do not expose `temperature`, `top_p`, `retriever`, `chunk size`, `agent count`, or API key state in the primary path.
- Error text must stay near the field and explain recovery.

### Switch and Slider

Rules:

- Switches control binary modes with immediate visual state.
- Sliders control bounded numeric values with visible current value.
- Both must preserve layout when changed.
- Disabled state must be visible and readable.

### Tabs

Use tabs only for peer views inside the same object:

```text
概览
过程
假设
证据
排序依据
质量信号
```

Rules:

- Do not nest multiple tab systems in the same viewport.
- Expensive or expert-only tabs should sit behind disclosure.
- Active tab must be clear via color, background, and `aria-selected`.
- Segmented controls that switch mutually exclusive views, including login mode, data input mode, asset filters, and tool categories, must use `role="tablist"`, `role="tab"`, and `aria-selected`; a visual `.selected` class alone is not enough.

### Card

Cards are for repeated objects:

```text
Hypothesis
Paper
Experiment
Report
Task
Template
```

Hypothesis card default content:

```text
Rank/order
User-facing title
Short summary
Score/ranking signal
Primary local action
Reference drawer trigger
```

Rules:

- Cards should not show full references, full reviews, raw metrics, or trace by default.
- Card actions should be explicit: `参考文献`, `设计实验`, `写入报告`.
- Cards may be selectable, but avoid button-inside-button markup.

### Drawer

Use drawers for contextual deep information:

```text
Reference evidence
Object metadata
Related papers
Review details
AI suggestions
```

Rules:

- Drawer opens only from explicit user intent.
- Drawer has title, close button, `role="dialog"`, `aria-modal`, `aria-labelledby`, Escape close, focus return, and a focus trap when it contains multiple focusable controls.
- Drawer content belongs to one selected object.
- Drawer must not become a global debug console.
- Prefer the reference drawer interaction quality as the target pattern. Legacy drawers without a focus trap are compatibility debt, not a pattern to copy.

### Modal

Use modals only for blocking decisions:

```text
Confirm destructive action
Resolve permission issue
Choose export target
```

Do not use modal for ordinary reference inspection when a drawer is better.

### Toast

Use toast for short feedback:

```text
Saved
Copied
Export started
Upload failed
```

Do not put long explanations or raw errors in toast.

### Error Feedback

Rules:

- Error banners and error state cards use `role="alert"`.
- Success/running completion feedback uses `role="status"`.
- Loading surfaces and submit buttons use `aria-busy` while work is in progress.
- Warning feedback that blocks or changes the current task path must be textually explicit and assistive-technology visible.
- UI copy must describe recovery: what failed, what can still be used, and what to try next.
- Pages should receive safe user messages from API/view-model helpers. Do not render raw `error.message`, HTTP response text, JSON detail, provider errors, endpoints, request IDs, or stack traces by default.

### Table and List

Use tables for comparison. Use cards/lists for object browsing.

Table column rules:

```text
Name: what is this
Status: current state
Owner/source: who or where
Updated: recency
Action: next action
```

Rules:

- Long text should open detail, drawer, or side panel.
- Low-frequency columns go behind column settings.
- Tables should support search/filter/sort when data volume requires it.

### Project Knowledge Chat

Use this pattern only for project-understanding Q&A, not for scientific hypothesis generation.

Required components:

```text
ProjectKnowledgeIndex: index status, source groups, reindex action
ProjectKnowledgeChat: readable message stream
ProjectKnowledgeMessage: user, assistant, system, or tool-status message
ProjectKnowledgeComposer: multiline textarea plus send icon button
ProjectKnowledgeSourceChip: short source reference on assistant answers
ProjectKnowledgeSourceDrawer: source details opened by explicit user intent
KnowledgeIndexStatus: ready, stale, indexing, limited, error
```

Layout:

- Desktop: left index rail, center ChatGPT-like message stream, sticky bottom composer, source drawer on demand.
- Mobile: single-column message stream with top segmented tabs for `问项目`, `索引`, and `来源`; source detail becomes a full-screen drawer.
- Do not implement it as a floating customer-support bubble or a marketing chat page.

Interaction rules:

- The composer supports `Enter` to send and `Shift+Enter` for newline.
- The send action is an icon button with an `aria-label`, stable dimensions, disabled reason, and `aria-busy` while answering.
- Assistant answers show a concise natural-language answer, status badge, 2-4 source chips, copy action, and optional next step.
- Source chips open a drawer; raw excerpts, chunk ids, hashes, endpoint details, and relative paths stay out of the default message body.
- Indexing/reindexing states show task progress, not raw scan logs.
- The chat may suggest existing task entries such as PDF parsing, web evidence, admin readiness, or workflow run setup; it must not bypass approval-backed workflows or execute high-risk operations directly.

Index contract:

- Index only project-understanding sources: AGENTS/instructions, system design docs, READMEs, package/pyproject files, router, pages, components, features, typed API clients, view-models, types, backend API declarations, requirements, and tests when relevant.
- Exclude `.auth`, `.codex`, `.coscientist_cache`, `node_modules`, `dist`, logs, private account SQLite stores, environment variables, provider keys, generated large artifacts, and paths outside the workspace.
- Each indexed record should preserve source type, relative path, route/endpoint/symbol, summary, responsibilities, user-facing capability, implementation boundary, updated time, content hash, and chunk refs.
- Stale, missing, permission-denied, or partial index states must be visible in user-facing language.

## 10. State Design

Controls must be designed as stateful products, not static shapes. A control is:

```text
Appearance + state + feedback + behavior constraint
```

Canonical control states:

| State | Meaning | Required Surface |
| --- | --- | --- |
| Default | Normal usable state | all controls |
| Hover | Pointer feedback | buttons, links, cards, tabs, switches |
| Focus | Keyboard focus ring | all interactive controls |
| Active | Pressed or clicking state | buttons, links, tabs, switches |
| Disabled | Temporarily unavailable | buttons, fields, switches, sliders |
| Loading | Async work in progress | submit buttons, result surfaces |
| Selected | Current chosen item | tabs, nav, hypothesis cards |
| Checked | Binary value is on | switches, checkboxes |
| Error | Invalid or failed state | fields, task feedback, banners |
| Success | Completed valid state | task feedback, submit buttons |
| Warning | Risk or degraded capability | task feedback, fields, banners |
| Empty | No usable content yet | lists, result surfaces |
| Skeleton | Content is loading but layout is known | lists, cards, result surfaces |
| Read-only | Copyable but not editable | text fields, generated summaries |

Control-family requirements:

- Buttons must support default, hover, focus-visible, active, disabled, loading, success, and warning where applicable.
- Inputs and textareas must support default, hover, focus-visible, disabled, read-only, error, success, warning, and loading validation where applicable.
- Switches and checkboxes must support checked, unchecked, hover, focus-visible, active, and disabled.
- Tabs, nav items, and selectable cards must support selected via both visual state and ARIA state.
- Lists and result surfaces must distinguish empty from skeleton. Empty means no content exists; skeleton means content is expected but not ready.
- Shared state components and local feedback components must align semantic roles with tone: error -> `role="alert"`, success/running -> `role="status"`, loading -> `aria-busy`.
- State changes must not change external dimensions, grid tracks, layout gaps, or sibling positions.

Every page and major component must design:

```text
Loading
Empty
Success
Error
Partial Error
Permission Denied
Queued
Running
Streaming
Timeout
Retrying
```

State wording must be task-oriented:

```text
正在解析论文...
已生成 3 个候选假设
当前假设暂无可解析参考文献
文献服务暂不可用，可先按非文献支撑流程继续
```

Avoid:

```text
No data
Error occurred
Failed
Invalid input
Provider missing
```

Rules:

- Loading state keeps dimensions stable.
- Error state offers recovery.
- Empty state offers the next action.
- Partial error preserves usable intermediate results.
- Permission denied tells user where to go next.
- Streaming/running state shows current phase but hides raw trace by default.
- Error copy must be sanitized before display. Raw API text, JSON payloads, provider names, environment variables, endpoints, request IDs, stack traces, local paths, and internal IDs belong behind expert/debug inspection only.

## 11. AI Result Contract

AI output is not complete until it is controllable, inspectable, traceable, and reusable.

Hypothesis result should expose:

```text
User-facing hypothesis title
Plain summary
Technical hypothesis text behind detail
Literature grounding
Citation map / source metadata
Experiment or validation plan
Score / ranking signal
Review feedback
Next actions
```

Default view should show:

```text
Title
Summary
Score / ranking signal
Reference drawer trigger
Experiment/report next actions
```

Hidden behind user intent:

```text
Full technical text
Citation map
Review rubric
Tournament/ranking details
Agent process
Metrics
Raw trace
```

Tournament/ranking detail contract:

- Ranking details live behind `查看过程与证据` and the `排序依据` tab, never on the default hypothesis card.
- Each visible tournament row should expose the user-relevant audit chain: compared hypotheses, winner, loser, confidence, comparison mode, Elo before/after/delta, concise reasoning, and a short scheduling rationale such as proximity/new/top-ranked priority.
- Stable hypothesis IDs may appear in this deliberate audit surface, but they should stay compact and should not replace the user-facing hypothesis title or summary.

Demo/live/literature boundary:

- Demo simulation: UI, workflow, schema, and interaction validation only.
- Live model workflow: model-backed generation, review, ranking, and evolution.
- Literature-grounded workflow: source-backed claims with citation provenance.

Never present demo output as real scientific evidence.

Project knowledge answers:

- Answer project capability, usage, route, component, API, setup, and documentation questions from the automatic project knowledge index.
- Always expose source chips. If sources are missing, stale, or partial, mark the answer as limited.
- Do not answer as if the indexed project docs are biomedical literature or experimental evidence.
- Do not surface raw source excerpts, local absolute paths, hashes, chunk ids, endpoints, or scan logs by default.

## 12. Page Templates

### Project Page

Purpose:

```text
Define research goal and move into candidate hypothesis generation.
```

Required:

- Project H1 and research goal summary.
- Current task H2.
- Research goal input.
- One primary action.
- Suggested starting tasks.
- Expert settings collapsed.
- Candidate results after run.
- Process/evidence details collapsed.

### Papers Page

Purpose:

```text
Inspect evidence readiness, source coverage, and citation gaps.
```

Required:

- Clear evidence status.
- Literature availability state.
- Next action to generate or inspect hypotheses.
- No raw MCP diagnostics by default.

### Literature Library Surface

Purpose:

```text
Create named evidence collections and route uploads, PDF URLs, MCP-discovered candidates, parsing, and RAG search into the selected collection.
```

Required:

- Named literature library list with create action, selected state, paper count, parse count, and chunk count.
- Current target library visible next to upload/parse/search actions.
- PDF upload, local/remote PDF path parsing, and MCP-discovered candidate parsing all submit `library_id`.
- Candidate cards show title, source, short abstract, download method, PDF readiness, and a single parse action when a PDF URL is available.
- When a candidate has a direct PDF URL, show an in-page `阅读 PDF` action. This opens a bottom sheet / near-fullscreen reader over the current Data page, preserves the current search results behind it, supports Escape close and focus restoration, and provides fallback actions to open the PDF in a new window or parse it into the selected literature library.
- When a candidate has no direct PDF URL but has a landing page, DOI page, publisher page, or repository page, show a clear `机构访问` / `打开论文页面` action. This opens the user-facing source so the researcher can log in with institutional access and download the PDF themselves. The app must not bypass paywalls, CAPTCHA, login walls, or publisher access controls.
- Candidate results must provide a deliberate citation audit/download area. Researchers should be able to download structured candidate citation metadata for the current candidate set and per-candidate spot checks. BibTeX must not be locally generated from title/author/abstract guesses. It may only be downloaded when a trusted source returns it directly, such as DOI content negotiation, Crossref transform, DataCite content negotiation, or the publisher/journal landing page opened by the researcher. If no DOI or official BibTeX endpoint is available, show a limited state and route the user to the paper page or institutional access path.
- After manual/institutional download, the expected recovery path is to return to the selected literature library and upload the downloaded PDF for parsing and knowledge-base ingestion.
- MCP unavailable state is visible and recoverable through upload or explicit PDF URL input.
- RAG search and asset tables are scoped to the selected library.
- Raw MCP payload, internal IDs, local paths, artifact paths, SQLite path, and parse run IDs are hidden by default and only appear through detail/audit disclosure.
- PDF reading, PDF parsing, and PDF translation are separate product responsibilities. Browser/PDF viewer reading is for quick human inspection; the existing PyMuPDF parser remains the evidence-grounding path that extracts metadata, fulltext chunks, media, and knowledge-base provenance; BabelDOC or another layout-preserving translator may be added as an optional background translation workflow that outputs translated/bilingual PDFs, but it must not replace provenance parsing or claim support evidence.

### Hypotheses Page

Purpose:

```text
Compare candidate directions and inspect one hypothesis at a time.
```

Required:

- Hypothesis cards.
- `参考文献` trigger on each card.
- Experiment/report next actions.
- Details behind disclosure.

### Experiments Page

Purpose:

```text
Convert one selected hypothesis into falsifiable validation.
```

Required:

- Selected hypothesis title and summary.
- Experiment plan in user-facing language.
- Falsification criteria.
- Evaluation output.
- Link back to hypotheses and forward to report.

### Reports Page

Purpose:

```text
Organize findings, experiment plan, and limitations into a draft.
```

Required:

- Research finding.
- Experiment plan.
- Limitations.
- Demo/live/literature boundary note.
- No raw backend text.

### Project Knowledge Chat Page

Purpose:

```text
Help researchers understand the current project, its implemented capabilities, and how to run or use them.
```

Required:

- H1 such as `项目问答` or `项目知识助手`.
- Index readiness summary with stale/reindex/error states.
- ChatGPT-like message stream with a clear empty prompt state.
- Sticky composer with stable loading/disabled/focus states.
- Assistant answers with 2-4 source chips and limited/stale status when appropriate.
- Source drawer for relative paths, chunk details, hashes, and excerpts.
- No raw JSON, environment variables, provider keys, private account data, local absolute paths, or hidden tool logs in the default view.
- Clear separation from hypothesis generation, live model workflow, and literature-grounded scientific claims.

## 13. Content Density

Professional research products may be dense, but density must be hierarchical.

Recommended density:

```text
Project overview: low to medium density
Hypothesis comparison: medium density
Evidence drawer: medium-high density
Experiment analysis: high density
Report drafting: medium density
Expert settings: high density but collapsed
```

Rules:

- Dense information belongs in object detail, drawer, table, or expert panel.
- Default page should not become a debug dashboard.
- Do not overuse decorative cards to compensate for weak information architecture.

## 14. Copywriting

Interface copy should sound like product workflow, not database fields.

Good Chinese labels:

```text
生成候选假设
参考文献
查看过程与证据
生成实验设计
写入报告草稿
当前假设暂无可解析参考文献
文献服务暂不可用，可先按非文献支撑流程继续
```

Avoid:

```text
Submit
Execute
Process
No data
Invalid
Provider key missing
Raw API
Run ID
```

Rules:

- Buttons use verbs.
- Empty states name the next action.
- Error states name the recovery path.
- Technical nouns can appear in expert settings, but not in primary workflow.

## 15. Accessibility

Minimum contract:

- Every form control has a label.
- Every interactive control has focus-visible styling.
- Keyboard users can reach buttons, tabs, drawers, and close actions.
- Error is not communicated only by color.
- Icon-only controls have `aria-label`.
- Drawer/modal uses dialog semantics.
- Body text contrast targets WCAG AA.
- Click targets are at least 40px on desktop and 44px on touch surfaces when practical.

## 16. Motion Design

Motion is part of task feedback, not decoration. This project uses Anime.js v4 for scoped UI motion in `src/lib/motion/`.

Allowed motion:

```text
Route/page entrance
Card/list stagger entrance
Reference drawer entrance
Disclosure/detail reveal
Run-state feedback
Metric/count transitions
```

Rules:

- Motion must clarify hierarchy, state change, or task progression.
- Motion must not expose hidden information earlier than the user action allows.
- Motion must not change layout dimensions, grid tracks, control height, or surrounding spacing.
- Use `transform` and `opacity` first; avoid animating width, height, margin, or padding in task surfaces.
- Every Anime.js hook must respect `prefers-reduced-motion`.
- Keep animation ownership in `src/lib/motion/`; feature components should consume hooks instead of embedding raw animation logic.
- Route and list animations should be short: 180-520ms, with small stagger intervals.
- Do not add decorative SVG/path animation, floating ornaments, or attention-grabbing loops to research workflow pages.
- Loading animation is allowed only for ongoing async work and must preserve stable button/control dimensions.

Current primitives:

```text
useReducedMotion
useRouteEntranceMotion
useListEntranceMotion
useDrawerEntranceMotion
useAnimatedNumber
```

## 17. Build And Verification

After substantial frontend changes:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false);
Set-Location .\open-coscientist\webapp
npm run build
```

Browser verification checklist:

```text
1. Page renders nonblank.
2. Default page exposes no raw API/provider/internal ID text.
3. Main workflow action works.
4. Loading, disabled, success, and empty states are visible.
5. Focus-visible outline exists on keyboard-accessible controls.
6. Hypothesis references open only after clicking `参考文献`.
7. Process/evidence details stay collapsed until user clicks.
8. No text overlap or layout shift on hover/active/loading.
9. Mobile/narrow viewport does not overflow.
10. Demo/live/literature boundary is clearly labeled.
11. Researcher-visible pages do not expose admin-only `/admin` entry points.
12. Error feedback shows safe recovery copy, not raw API/provider/debug payloads.
13. Project knowledge chat, when present, shows source chips, hides raw source details by default, and clearly marks stale/limited index states.
```

## 18. Per-Change Review Checklist

Use this before shipping any frontend page or component:

```text
1. Is the page organized by user task rather than system module?
2. Can the user understand page, task, state, and next action in 3 seconds?
3. Is there one clear primary action?
4. Is advanced or audit information hidden until user intent?
5. Are controls using existing tokens for color, spacing, radius, and typography?
6. Do all controls have default, hover, active, disabled, loading, and focus-visible states when applicable?
7. Does the component preserve dimensions across state changes?
8. Are colors semantic rather than decorative?
9. Are AI results inspectable and traceable without flooding the default view?
10. Are demo outputs clearly marked as non-scientific evidence?
11. Is there a recovery path for errors or unavailable literature services?
12. Does the UI avoid raw API, provider key, endpoint, stack trace, run_id, or raw JSON?
13. Does the component work with realistic data length?
14. Does the user have a next step after success?
15. Did `npm run build` pass?
16. Does motion support task feedback without layout shift or information leakage?
17. Are admin-only links hidden from researcher paths?
18. Are errors, warnings, success, and loading states using the right ARIA semantics?
19. If project knowledge chat is touched, are index sources, excluded paths, source drawer, stale/limited states, and no-direct-execution boundaries preserved?
```
