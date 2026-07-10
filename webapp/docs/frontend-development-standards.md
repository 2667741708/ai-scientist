# Frontend Development Standards

This document turns the reusable frontend design rules from the pasted design-system notes into a long-lived development standard.

It is intentionally broader than `frontend-system-design.md`: this file defines how to build a reusable frontend system from foundations, components, patterns, and pages. The project-specific research workbench rules still live in `frontend-system-design.md` and take precedence for `open-coscientist/webapp/`.

Core principle:

```text
Do not start by making pretty pages. First define reusable rules, then compose pages from those rules.
```

## 1. Scope And Priority

Use this standard when creating or refactoring:

- Design tokens
- CSS variables or theme config
- Reusable React components
- Form controls
- Cards, drawers, modals, tables, tabs, and page sections
- Page layouts and responsive behavior
- Loading, empty, error, success, disabled, and focus states

Priority order:

1. User task and information architecture
2. Existing project-specific frontend contract
3. Existing runtime tokens and component patterns
4. This reusable standard
5. New visual ideas

If a project already has tokens, components, or interaction conventions, extend them instead of creating a second local style language.

## 2. Four-Layer Model

Every frontend system is built in four layers:

| Layer | Meaning | Output |
| --- | --- | --- |
| Foundations | Color, typography, spacing, radius, shadow, grid, motion | Design tokens and CSS variables |
| Components | Buttons, inputs, cards, tabs, modals, drawers, tables | Reusable UI primitives |
| Patterns | Header, form panel, evidence drawer, result list, settings panel | Reusable task sections |
| Screens | Home, data page, workflow page, output page, admin page | Product pages |

Rules:

- Do not hard-code page-specific values when a foundation token should exist.
- Do not rebuild common controls inside each page.
- Do not make full pages before component states are defined.
- Do not treat mock/demo output as proof of real product or scientific behavior.

## 3. Figma Structure

For a long-lived design file, use this page structure:

```text
00 Cover / Usage
01 Foundations
02 Components
03 Patterns
04 Screens
99 Archive
```

Meaning:

- `01 Foundations`: tokens, typography, spacing, grid, radius, shadows, color roles.
- `02 Components`: reusable primitives such as Button, Input, Card, Tabs, Modal.
- `03 Patterns`: composed sections such as login form, hypothesis list, reference drawer, pricing block.
- `04 Screens`: actual product pages.
- `99 Archive`: deprecated explorations that should not be copied into production.

Figma implementation:

- Use Auto Layout for component sizing, padding, gap, alignment, and responsive composition.
- Use Styles or Variables for reusable color, typography, shadow, and grid values.
- Use Components and Variants for repeated UI. Instances should inherit from the main component.
- Use slash-based naming for assets and components when it improves search and replacement.

## 4. Foundation Tokens

Tokens are named product decisions. A component should say `color/text/primary`, not `#0F172A`.

Required token families:

```text
color
space
radius
typography
shadow
grid
control
motion
```

Project rule:

```text
If runtime CSS tokens already exist, use those names in code. Generic token names below are the design-system vocabulary, not permission to duplicate tokens.
```

For this project, runtime tokens live in:

```text
open-coscientist/webapp/src/styles/tokens.css
```

### 4.1 Color

Color tokens are semantic roles, not decorative labels.

Required roles:

```text
color/brand/primary
color/brand/hover

color/text/primary
color/text/secondary
color/text/tertiary
color/text/inverse

color/bg/page
color/bg/surface
color/bg/subtle
color/bg/raised

color/border/default
color/border/strong
color/border/focus

color/status/success
color/status/warning
color/status/danger
color/status/info
```

Use roles this way:

| Role | Use |
| --- | --- |
| Brand primary | Main action, selected state, focus-related emphasis |
| Text primary | Page title, section title, important generated content |
| Text secondary | Body copy, descriptions, helper text |
| Text tertiary | Metadata, captions, low-priority labels |
| Page background | App/page background |
| Surface | Panels, cards, drawers, inputs, popovers |
| Border default | Normal separation and inactive controls |
| Border strong | Active dividers, strong control boundaries |
| Success | Completed task |
| Warning | Degraded capability or recoverable risk |
| Danger | Destructive action or serious error |

Rules:

- Do not scatter random hex values through components.
- Do not use red except for destructive, invalid, or serious failure states.
- Do not use highly saturated color on every icon.
- A single viewport should have only one or two strongest visual accents.
- Body text should meet WCAG AA contrast where practical.

For new products without existing tokens, this seed palette is acceptable as a starting point:

```text
color/brand/primary  #2563EB
color/brand/hover    #1D4ED8
color/text/primary   #0F172A
color/text/secondary #475569
color/text/tertiary  #94A3B8
color/bg/page        #F8FAFC
color/bg/surface     #FFFFFF
color/border/default #E2E8F0
color/status/success #16A34A
color/status/warning #D97706
color/status/danger  #DC2626
```

Do not apply the seed palette to an existing product that already has a deliberate theme.

### 4.2 Typography

Recommended type roles:

| Token | Use |
| --- | --- |
| `typography/display` | Rare hero or empty-state headline |
| `typography/h1` | Page title |
| `typography/h2` | Major task or section title |
| `typography/h3` | Card, panel, or detail title |
| `typography/body-lg` | Important explanatory copy |
| `typography/body-md` | Normal content |
| `typography/body-sm` | Helper text and compact content |
| `typography/caption` | Metadata, chips, and small labels |
| `typography/button-md` | Button/control text |

Rules:

- Keep a page to a small type scale. Avoid twenty one-off font sizes.
- Do not use viewport-width font sizing.
- Letter spacing should stay `0` unless matching an existing brand system.
- Compact panels, cards, sidebars, and toolbars use smaller type than page headers.
- Button and tab text must fit across supported desktop and mobile widths.

Chinese-friendly font fallback:

```text
Inter / Noto Sans SC / Microsoft YaHei / PingFang SC / system-ui
```

### 4.3 Spacing

Use a small spacing scale:

| Token | Value | Typical use |
| --- | ---: | --- |
| `space/1` | 4 | Icon-to-label gap, tight metadata |
| `space/2` | 8 | Small control gaps |
| `space/3` | 12 | Form inner spacing |
| `space/4` | 16 | Card/content gap |
| `space/5` | 20 | Medium content rhythm |
| `space/6` | 24 | Panel padding and component gaps |
| `space/8` | 32 | Section inner spacing |
| `space/10` | 40 | Large task spacing |
| `space/12` | 48 | Page rhythm |
| `space/16` | 64 | Large page section |
| `space/20` | 80 | Landing-page section, only when appropriate |

Rules:

- Prefer `4`, `8`, `12`, `16`, `24`, `32`, `48`, and `64`.
- Avoid random spacing such as `13`, `17`, `23`, or `37`.
- State changes must not change external margins, grid tracks, or sibling positions.
- Use spacing and borders before adding heavy shadows.

### 4.4 Radius

Recommended radius roles:

| Token | Value | Use |
| --- | ---: | --- |
| `radius/none` | 0 | Hard-edged layouts |
| `radius/sm` | 4 | Small tags or compact elements |
| `radius/md` | 8 | Buttons, inputs, small panels |
| `radius/lg` | 12 | Cards in products that use softer panels |
| `radius/xl` | 16 | Dialogs or large panels, only if established |
| `radius/pill` | 999 | Pills, switches, badges |

Project rule:

- Operational workbench UIs should default controls and panels to 8px unless the existing system says otherwise.
- Avoid random radius values such as `7`, `11`, or `18`.

### 4.5 Shadow

Rules:

- Use shadows sparingly.
- Prefer border, spacing, and background contrast for structure.
- Heavy shadows are reserved for overlays, drawers, popovers, and elevated transient surfaces.
- Do not use decorative glow, gradient blobs, or visual ornaments as a substitute for hierarchy.

## 5. Component Standards

Every reusable component must define:

```text
Purpose
Variants
Sizes
States
Accessibility semantics
Layout constraints
Usage rules
Do-not-use cases
```

### 5.1 Button

Variants:

| Variant | Use |
| --- | --- |
| Primary | One most important action in a region |
| Secondary | Normal secondary action |
| Ghost | Low-emphasis action |
| Danger | Destructive or irreversible action |
| Icon | Familiar compact tools such as search, filter, close, download |

Sizes:

| Size | Height | Horizontal padding | Use |
| --- | ---: | ---: | --- |
| `sm` | 32 | 12 | Dense toolbars |
| `md` | 40 | 16 | Default desktop control |
| `lg` | 48 | 20 | Prominent task action |

Required states:

```text
default
hover
active
focus-visible
disabled
loading
success where useful
warning where useful
```

Rules:

- A page region should have at most one primary button.
- Button copy uses verb plus outcome: `创建项目`, `生成候选假设`, `保存设置`, `发送邀请`.
- Avoid vague copy: `提交`, `点击`, `处理`, `确定` when the result is unclear.
- Loading state keeps the same height, width strategy, icon slot, and text alignment.
- Disabled buttons need visible reason or nearby explanatory text when the reason is not obvious.
- Icon-only buttons require `aria-label` and visible focus state.

### 5.2 Input, Textarea, Select

Required structure:

```text
Label
Control
Helper text
Error or warning text when needed
```

Required states:

```text
default
hover
focus-visible
filled
disabled
read-only
loading validation
success
warning
error
```

Rules:

- Every form field needs a visible label.
- Placeholder text cannot replace the label.
- Error state must include text, not just a red border.
- Helper text belongs near the field it explains.
- Advanced or risky fields belong behind expert settings.
- Field height should stay stable across validation states.

### 5.3 Card

Use cards for repeated objects:

```text
Hypothesis
Paper
Experiment
Report
Task
Template
Pricing plan
Feature item
```

Default structure:

```text
Optional icon/image/status
Title
Short description
Metadata or score
Primary local action
Secondary detail action
```

Rules:

- One card should describe one object or one idea.
- Card title should be short and should not overflow.
- Description should normally stay within two or three lines.
- Cards in the same grid should use consistent padding and spacing.
- Do not put cards inside cards.
- Do not show full references, raw metrics, raw traces, or long debug text by default.

### 5.4 Form

Rules:

- Prefer single-column forms unless comparison requires columns.
- Labels sit above inputs.
- Error text sits near the field that failed.
- Primary submit action sits at the end of the form.
- Ask for the minimum information needed to complete the current step.
- Split expert settings or optional configuration into disclosure panels.

Standard form section:

```text
Title
Short task description
Field group
Local validation or helper state
Primary action
Secondary escape or reset action
```

### 5.5 Tabs And Segmented Controls

Use tabs for peer views of the same object:

```text
概览
过程
假设
证据
排序依据
质量信号
```

Rules:

- Do not use tabs as primary navigation across unrelated tasks.
- Avoid nested tab systems in one viewport.
- Active tab must be visible and have `aria-selected`.
- Segmented controls for modes should use the same stable sizing and keyboard semantics.

### 5.6 Drawer, Modal, Popover, Toast

Drawer:

- Use for contextual inspection: references, evidence, metadata, review details.
- Must have title, close button, dialog semantics, Escape close, focus return, and focus trap when multiple focusable controls exist.
- Must belong to one selected object.
- Must not become a global debug console.

Modal:

- Use only for blocking decisions: destructive confirmation, permission resolution, export target.
- Do not use modal for ordinary reading when a drawer or inline disclosure is enough.

Popover:

- Use for short menus, filters, or compact explanations.
- Do not hide critical workflow actions inside popovers.

Toast:

- Use for short feedback: saved, copied, export started, upload failed.
- Do not put long explanations, raw JSON, stack traces, or provider errors in toast.

### 5.7 Table And List

Use tables for comparison and dense records. Use cards or lists for browsing.

Recommended table columns:

```text
Name
Status
Source/Owner
Updated
Quality or score when relevant
Action
```

Rules:

- Long text opens a detail panel or drawer.
- Low-frequency columns belong behind column settings or details.
- Support search, filter, and sort when data volume requires it.
- Empty and loading states must be distinct.

## 6. Pattern Standards

Patterns are composed sections made from components.

Common patterns:

```text
App shell
Page header
Task panel
Result list
Evidence drawer
Settings disclosure
Login form
Upload and parse form
Comparison table
Report surface
Empty state
Error recovery panel
```

Pattern rules:

- A pattern must answer one user intent.
- A pattern should expose one primary action.
- Audit or expert details stay behind explicit disclosure.
- Use stable grid tracks and min/max constraints.
- Pattern state changes must not cause layout shift.

## 7. Page Design Workflow

Create pages in this order:

1. Write the page goal.
2. Identify the primary user.
3. Define the one most important action.
4. Write the information structure.
5. Draw or sketch a grayscale wireframe.
6. Apply typography and color tokens.
7. Compose from existing components.
8. Add empty, loading, error, success, disabled, and permission states.
9. Verify desktop and mobile behavior.
10. Check whether advanced details are hidden until user intent.

Page goal template:

```text
Page:
Primary user:
Goal:
Primary action:
Required decision:
Required evidence/context:
Success state:
Failure/recovery state:
```

Before implementation, answer:

```text
1. Why is the user here?
2. What should they judge first?
3. What is the next action?
4. What can remain hidden until requested?
5. Which existing pattern already solves this?
```

## 8. Information Hierarchy

The first viewport should answer within three seconds:

```text
Where am I?
What task is active?
What is the current state?
What should I do next?
```

Hierarchy tools:

- Size: important content is larger, but only at page or section level.
- Weight: use bold for structure, not for every label.
- Color: reserve brand color for main actions and selected states.
- Spacing: related items are close; unrelated groups are separated.
- Position: primary task content appears before diagnostics and details.

Rules:

- One viewport should have only one or two strongest visual focal points.
- Do not make every button primary.
- Do not make every icon colorful.
- Do not use decoration to compensate for unclear page structure.

## 9. Conversion And Clarity

For marketing, onboarding, or activation pages, clarity matters more than decoration.

Rules:

- The first screen should state what the product is, what problem it solves, and the next action.
- A hero section should normally have one primary button and one secondary action.
- Main button text should describe the result, such as `免费创建项目`, not vague activity such as `立即体验`.
- Trust information should be factual and relevant.
- Forms should ask for the smallest set of fields needed to continue.

For operational tools and research workbenches:

- Do not create a marketing landing page when the user needs a working task surface.
- Lead with the active workflow, data status, result, or next action.
- Keep provider, API, prompt, tool, run ID, and debug concepts out of the primary path.

## 10. Naming Standards

Figma component naming:

```text
Button
Button/Primary/Default
Button/Primary/Hover
Button/Primary/Disabled
Input/Default
Input/Focus
Input/Error
Card/Default
Card/Selected
```

Preferred variant model:

```text
Component: Button
variant: primary / secondary / ghost / danger
size: sm / md / lg
state: default / hover / active / disabled / loading
iconLeft: true / false
iconRight: true / false
```

Code naming:

- Component names use product concepts, not visual styling names.
- CSS classes should describe role or component, not raw color.
- Avoid names such as `blue-card`, `big-box`, `left-thing`, `new-style`.
- Prefer names such as `evidence-drawer`, `task-panel`, `hypothesis-card`, `run-status`.

## 11. Responsive Rules

Responsive behavior should be designed, not left to chance.

Recommended breakpoints:

```text
Desktop wide: >= 1280px
Desktop/tablet: 960px - 1279px
Tablet/narrow: 640px - 959px
Mobile: < 640px
```

Rules:

- Desktop may use multi-column grids.
- Mobile should collapse repeated cards and form controls to one column.
- Dense diagnostics and expert settings should move behind drawers or disclosures.
- Controls should keep a touch target of at least 44px where practical.
- Text must wrap, clamp, or truncate intentionally.
- No horizontal overflow on narrow screens.

## 12. Accessibility Contract

Minimum requirements:

- Every form control has a label.
- Every interactive control has a visible focus state.
- Icon-only controls have `aria-label`.
- Error is not communicated only by color.
- Loading surfaces use `aria-busy` when appropriate.
- Error feedback that blocks progress uses `role="alert"`.
- Success or running feedback uses `role="status"`.
- Tabs use correct tab semantics where implemented as tabs.
- Drawer and modal surfaces use dialog semantics.
- Keyboard users can open, navigate, close, and return from overlays.

## 13. Implementation Mapping

For React/CSS projects:

- Put reusable values in CSS variables, theme config, or a token file.
- Import tokens globally once, then consume them via semantic classes.
- Prefer existing component wrappers before creating new primitives.
- Use `lucide-react` or the existing icon library for familiar icon buttons.
- Keep state classes explicit: `.is-loading`, `.is-selected`, `.is-disabled`, `.has-error`.
- Keep dimensions stable with fixed control heights, min/max widths, grid tracks, and aspect ratios.
- Avoid style-only components that duplicate behavior without accessibility.

For this project:

```text
Tokens: open-coscientist/webapp/src/styles/tokens.css
Component styles: open-coscientist/webapp/src/styles/components.css
Layout styles: open-coscientist/webapp/src/styles/layout.css
Project-specific contract: open-coscientist/webapp/docs/frontend-system-design.md
```

## 14. State Checklist

Every page and major component should cover:

```text
Loading
Empty
Success
Error
Partial error
Disabled
Permission denied
Offline or unavailable service
Queued
Running
Retrying
Timeout
```

State wording should be task-oriented:

```text
正在解析论文
已写入知识库
当前没有可解析参考文献
文献服务暂不可用，可先按非文献支撑流程继续
```

Avoid:

```text
No data
Failed
Invalid
Provider missing
Raw API error
```

## 15. Review Checklist

Before shipping a frontend change:

```text
1. Is the page organized by user task rather than system internals?
2. Can the user identify page, task, state, and next action in three seconds?
3. Is there only one primary action in each region?
4. Are colors, spacing, typography, radius, and shadows token-based?
5. Are repeated controls implemented as reusable components or established patterns?
6. Are default, hover, active, focus, disabled, loading, success, and error states covered?
7. Do state changes preserve dimensions and avoid layout shift?
8. Are raw API, provider, run ID, stack trace, local path, and raw JSON hidden by default?
9. Are labels and errors accessible to keyboard and assistive-technology users?
10. Does the layout work on desktop, tablet, and mobile widths?
11. Does realistic long text fit or degrade intentionally?
12. Are demo, live, and evidence-grounded outputs clearly distinguished when relevant?
13. Did the implementation reuse existing project tokens and component conventions?
14. Did the build and browser smoke test pass when code changed?
```

## 16. Learning Path For New Contributors

For contributors new to frontend design systems:

```text
Day 1: Learn frame, layout, padding, and gap.
Day 2: Define color and typography tokens.
Day 3: Build Button variants and states.
Day 4: Build Input, Textarea, Select, and Form patterns.
Day 5: Build Card and repeated-object patterns.
Day 6: Compose one real page from patterns.
Day 7: Review hierarchy, spacing, state, accessibility, and responsiveness.
```

The durable habits:

```text
1. Start with the page goal.
2. Define structure before styling.
3. Use tokens for visual decisions.
4. Build repeated UI as components.
5. Hide advanced detail until user intent.
6. Verify states and responsive behavior.
7. Keep the product clear, consistent, readable, usable, and maintainable.
```

## 17. References

Useful Figma concepts:

- Auto Layout: layout direction, gap, padding, alignment, resizing.
- Styles: reusable color, text, shadow, and grid style definitions.
- Variables: reusable values for tokens and theme switching.
- Components: reusable elements with main component and instances.
- Component naming: slash-based organization for discoverability.

Reference links:

- [Figma Auto Layout](https://help.figma.com/hc/en-us/articles/360040451373-Explore-auto-layout-properties)
- [Figma Variables](https://help.figma.com/hc/en-us/articles/15339657135383-Guide-to-variables-in-Figma)
- [Figma Styles](https://help.figma.com/hc/en-us/articles/360039238753-Styles-in-Figma-Design)
- [Figma Components](https://help.figma.com/hc/en-us/articles/360038662654-Guide-to-components-in-Figma)
- [Figma Component Naming](https://help.figma.com/hc/en-us/articles/360038663994)
