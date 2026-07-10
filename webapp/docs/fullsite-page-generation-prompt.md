# Open Co-Scientist Webapp 全站页面规范长 Prompt

本文档用于给 Figma、Lovable、通用代码生成器或外包前端设计师提供一份基于当前 `open-coscientist/webapp` 真实实现的全站规范 prompt。它不是抽象设计建议，而是结合当前 repo 已存在页面、路由、组件、控件、状态和布局模式整理出的落地约束。

目标：

- 帮后续页面生成保持和当前研究工作台一致
- 防止把产品做成泛 SaaS 官网、后端控制台或 PPT 式 demo
- 把页面级信息架构、布局骨架、控件语义、状态设计和文案边界写死
- 为 landing / login / home / workflows / tools / data / workspace / projects / outputs / admin 提供统一生成规范

---

## 1. Repo 证据盘点

以下盘点基于当前 `src/` 目录的真实实现。

核对日期：2026-06-29。

建议重新核对时使用 PowerShell UTF-8 前缀后执行：

```powershell
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false);
rg -F -o --glob '*.tsx' '<button' .\src
```

本文中的数量是为了让生成器理解当前页面复杂度和控件语言，不应作为测试断言；真正修改前仍需以当前代码为准。
在 PowerShell 中递归统计 TSX 时，优先使用 `rg --glob '*.tsx'` 或 `Get-ChildItem -Recurse -Filter *.tsx`，不要依赖不稳定的 `**\*.tsx` 展开。
组件复用次数按 JSX opening tag 统计，例如 `<PageHeader`、`<DisclosurePanel`，不要用裸字符串 `PageHeader`，否则会把 import、类型和说明文字一起计入。

### 1.1 页面与路由

当前 `router.tsx` 定义的主路由位于：

- `src/app/router.tsx`

当前路由结构：

- 公共页：
  - `/login`
- 受保护主路径：
  - `/`
  - `/home`
  - `/workflows`
  - `/tools`
  - `/data`
  - `/projects`
  - `/projects/:projectId`
  - `/projects/:projectId/papers`
  - `/projects/:projectId/hypotheses`
  - `/projects/:projectId/experiments`
  - `/projects/:projectId/reports`
  - `/workspace`
  - `/workspace/:projectId`
  - `/outputs`
  - `/admin`
- 兼容跳转：
  - `/library` -> `/data`
  - `/library/papers` -> `/data?view=papers`
  - `/library/references` -> `/data?view=references`
  - `/settings` -> `/admin`

当前事实：

- `/` 不是公共 landing page，而是受保护 AppShell 下 redirect 到 `/home`
- 如果未来新增公共 landing，必须先显式调整 `router.tsx` 的根路径保护策略，不能在 prompt 中把未来设想描述成当前路由事实

### 1.2 Page 文件数量

当前 `src/pages/` 下共有 `12` 个 page 文件：

- `src/pages/admin/AdminPage.tsx`
- `src/pages/data/DataPage.tsx`
- `src/pages/home/HomePage.tsx`
- `src/pages/library/LibraryPage.tsx`
- `src/pages/login/LoginPage.tsx`
- `src/pages/outputs/OutputsPage.tsx`
- `src/pages/projects/ProjectDetailPage.tsx`
- `src/pages/projects/ProjectsPage.tsx`
- `src/pages/settings/SettingsPage.tsx`
- `src/pages/tools/ToolsPage.tsx`
- `src/pages/workflows/WorkflowsPage.tsx`
- `src/pages/workspace/WorkspacePage.tsx`

说明：

- `LibraryPage` 和 `SettingsPage` 目前属于兼容/旧入口语义，主路径已分别被 `/data` 和 `/admin` 吸收
- 二者虽然仍有完整 page 文件，但当前 `router.tsx` 中 `/library*` 和 `/settings` 都是 `Navigate`，不是 active route implementation；生成器不应把它们当作当前主页面目标
- 后续新增 `LandingPage` 时，推荐新增：
  - `src/pages/landing/LandingPage.tsx`

### 1.3 Shared 组件数量

当前 `src/components/` 下共有 `5` 个共享组件文件：

- `src/components/navigation/PrimaryNav.tsx`
- `src/components/feedback/states.tsx`
- `src/components/overlays/DisclosurePanel.tsx`
- `src/components/surfaces/PageHeader.tsx`
- `src/components/surfaces/cards.tsx`

当前共享组件导出主要包括：

- `PrimaryNav`
- `EmptyState`
- `LoadingState`
- `SkeletonState`
- `SuccessState`
- `ErrorState`
- `StatusBanner`
- `DisclosurePanel`
- `PageHeader`
- `SummaryList`
- `ProjectCard`
- `OutputCard`
- `ReferenceCard`

### 1.4 Feature 组件数量

当前 `src/features/` 下共有 `9` 个 TSX feature 文件：

- `features/auth/auth-context.tsx`
- `features/auth/ProtectedRoute.tsx`
- `features/evidence/ReferenceDrawer.tsx`
- `features/experiments/ExperimentsPanel.tsx`
- `features/hypotheses/HypothesisWorkspace.tsx`
- `features/reports/ReportsPanel.tsx`
- `features/runs/RunComposer.tsx`
- `features/runs/TimelinePanel.tsx`
- `features/runs/workbench-context.tsx`

说明：

- `auth-context.tsx` 与 `workbench-context.tsx` 是状态/context feature，不是可视页面骨架
- `queries.ts`、`useProjectRouteRun.ts` 等 hook/query 文件不计入 TSX feature 文件数，但属于 feature 层运行数据支撑

其中承担主要页面骨架职责的 feature 组件：

- `RunComposer`
- `HypothesisWorkspace`
- `ReferenceDrawer`
- `TimelinePanel`
- `ExperimentsPanel`
- `ReportsPanel`

### 1.5 共享状态、API 与 view-model 边界

当前全站状态和数据获取不是各页面自由组织，而是有明确边界：

- `src/app/providers.tsx`
  - `QueryClientProvider`
  - `AuthProvider`
  - `WorkbenchProvider`
- `src/features/runs/workbench-context.tsx`
  - 研究目标、模型选择、文献开关、参考文献范围、当前 run、历史 run、当前选中假设、详情 tab、运行阻塞状态
- `src/features/runs/queries.ts`
  - run history、run polling、create run mutation、local history cache
- `src/features/health/queries.ts`
  - health readiness query
- `src/lib/constants/queryKeys.ts`
  - React Query key 命名边界
- `src/lib/api/workbench.ts`
  - 前端访问 FastAPI bridge 的 typed API client
- `src/lib/view-models/workbench.ts`
  - 将后端 run、hypothesis、citation、evidence、outputs 映射为页面可消费 view model
- `src/types/workbench.ts`
  - 全站运行记录、假设、文献、PDF parse、工具 workflow、任务、schedule、delegation、session search 的共享类型

生成约束：

- 新增页面不要绕过 `lib/api/workbench.ts` 直接散落 `fetch('/api/...')`，除非同时补齐 typed API client 和错误处理。
- 新增 run / hypothesis / evidence 展示不要在组件里重复解析 raw schema，应优先扩展 `types/workbench.ts` 和 `lib/view-models/workbench.ts`。
- `WorkspacePage` 相关运行态必须接入 `WorkbenchProvider`，不要在页面局部重建第二套 `currentRunId`、`selectedIndex`、`activeDetailTab`、run history 状态。
- React Query server state、context workflow state、短生命周期 form state 要分清；不要把长耗时任务状态只存在局部组件里而丢失刷新后的可恢复路径。
- 所有新增 API 错误都必须转成任务化文案，不得把 raw exception、raw JSON、endpoint、request id 直接展示在默认 UI。

### 1.6 控件总量粗盘点

基于 JSX 标签粗统计，当前页面与组件层已出现：

- `button`: 51
- `input`: 31
- `select`: 4
- `textarea`: 1
- `Link`: 45
- `PageHeader`: 11
- `EmptyState`: 12
- `LoadingState`: 3
- `SkeletonState`: 4
- `SuccessState`: 0
- `ErrorState`: 0
- `StatusBanner`: 5
- `SummaryList`: 18
- `DisclosurePanel`: 3
- `ReferenceDrawer`: 1
- `aria-busy`: 16
- `aria-selected`: 7
- `role="dialog"`: 2
- `role="presentation"`: 2
- `<details>`: 5
- `<summary>`: 5
- `role="switch"`: 4
- `role="tablist"`: 5
- `role="tab"`: 6
- `role="listbox"`: 1
- `role="option"`: 1

结论：

- 当前产品不是卡片展示型官网，而是任务驱动型研究工作台
- 高价值控件不是“营销 CTA”，而是：
  - 搜索输入
  - 表单输入
  - toggle
  - slider
  - table/list row
  - drawer
  - disclosure
  - detail tabs
  - status banner
  - state card

### 1.7 本次代码核对发现的统一性缺口

这些不是必须立刻改代码的 bug，而是后续页面生成或重构时必须统一的设计约束。

1. 当前控件统计会随页面增长快速变化，文档应保留“核对日期”和“核对命令”，避免把旧数字当作真实结构。
2. `DataPage`、`ToolsPage`、`AdminPage` 已经从简单页面扩展为高密度任务工作台，后续生成器必须把它们视为 product control surface，而不是普通列表页。
3. `DataPage` 的解析证据详情会显示 `parse_run_id`、`chunk_id`、文件路径等内部信息；当前默认解析成功反馈已经收敛为“已完成解析、生成知识库片段”，内部定位主要进入 drawer / evidence detail / expert inspection。后续生成器必须沿用这个方向，不要把审计编号重新放回默认列表、首页或卡片摘要。
4. `ToolsPage` 和 `DataPage` 现在共有 `details` 原生 disclosure，用于定位信息、证据文件、哈希、快照路径、章节路径等可审计字段；后续新增工具结果必须沿用“摘要默认展示、定位和 artifact 细节按需展开”的模式。
5. `AdminPage` 面向管理员，但仍是 product-facing control plane；允许在专家设置/管理员上下文中出现模型协议、角色、服务状态、OpenAI-compatible endpoint 这类运行策略文案，不允许把 provider key、raw endpoint、stack trace、repair command 或 raw health JSON 直接铺开。
6. 当前主导航由 `PrimaryNav` 固化为：研究主页、研究流程、研究工具、资料库、研究产出、运行准备；普通研究员隐藏“运行准备”。新增页面不应绕过这个角色可见性规则。
7. `ProjectDetailPage` 当前 `.detail-nav` 已经统一为中文任务标签：概览 / 论文 / 假设 / 实验 / 报告。后续重构应继续保持该语言边界，除非整页明确采用英文科研文档语境。
8. `SuccessState`、`ErrorState` 已在共享状态组件中导出但当前没有 JSX 使用；生成器可以复用它们，但不能把它们当作现有页面的高频模式。
9. 共享状态边界以前在本文中不够显式；后续新增页面应优先接入 `QueryClientProvider`、`AuthProvider`、`WorkbenchProvider`、typed API client 和 view-model 层，不要重造孤立页面状态。
10. `ToolsPage` 内部已经形成 `WorkflowCardHeader`、`WorkflowFeedback`、`SessionResultList`、`FileSnapshotPreview`、`WebExtractPreview`、`SchedulePlanner`、`DelegationPlanner`、`OperationList`、`BackgroundJobList` 等局部模式；这些虽未抽到 `components/`，但已经是工具工作台的事实规范，新增工具面板应沿用“任务说明 + scope/approval + submit + stable feedback + preview/details”的结构。
11. `DataPage` 和 `ReferenceDrawer` 都使用 drawer，且当前都具备 `role="dialog"`、`aria-modal`、Escape close、focus return 和 Tab 环绕。后续新增 drawer 应以这两个实现的交互质量作为目标模式。
12. segmented control / tab 目前依赖 `role="tablist"`、`role="tab"`、`aria-selected`；新增 tab、filter chip、mode switch 时必须补齐 ARIA，不要只做视觉按钮组。
13. `animejs` 动效已通过 `src/lib/motion/` 形成封装；新增页面效果应使用这些 hook 并尊重 `prefers-reduced-motion`，不要在页面组件里散落原始动画逻辑。
14. `HomePage` 和 `ToolsPage` 当前仍有指向 `/admin` 的入口；后续生成或重构时，所有“运行准备 / 查看阻塞 / 运行参数”等管理员入口必须和 `PrimaryNav` 一样按 `user.role === "admin"` 控制可见性。普通研究员默认只看到任务化的不可用提示或下一步，不应被引导到受限路由再撞权限页。
15. `LoginPage` 的登录模式切换已经补齐 `role="tablist"`、`role="tab"`、`aria-selected`、`aria-controls` 和 `tabpanel`。后续新增或重构 segmented control / tab 时，应继续按这个目标模式实现，不要退回只靠 `.selected` 的视觉按钮组。
16. `SettingsPage` 文件仍存在，但 `/settings` 已经跳转到 `/admin`；其中旧的参考文献 min/max slider 会互相改变可视范围，不应被复制。后续参考文献范围、模型预算、检索预算 slider 都以 `RunComposer` 和 `AdminPage` 的固定全量刻度为准，提交时再归一化 min/max。
17. `DataPage` 当前 RAG result 默认 footer 使用“已记录证据”这类任务文案，而不是直接显示 `evidence_id`；`parse_run_id`、`chunk_id` 和文件路径进入“查看审计定位”。后续生成器不得把 `evidence_id`、`parse_run_id`、`chunk_id`、`solve_dir`、本机路径或 artifact path 放进默认卡片、表格行、首页摘要或成功提示。
18. `ReferenceDrawer` 的 PDF 解析成功文案当前只显示“已解析并写入知识库、生成片段和媒体线索”，不再默认显示 `solve_dir`。后续产物目录、媒体路径和 parse run 定位只进详情 / 专家检查入口。
19. `ToolsPage` 默认 UI 中的内部治理词已经大多被翻译为任务语言，例如 “研究任务流程 / 方法模板 / 适用阶段 / 审查角色 / 本地审计记录 / 执行前确认”。后续生成器必须继续沿用这些译法；英文内部术语只允许在专家详情、审计详情或管理员上下文出现。
20. 错误展示不能只靠页面组件直接渲染 `error.message`。typed API client 或 view-model 层应先把后端错误、HTTP text、JSON detail、provider 报错转换成 safe user message；页面只展示任务化恢复文案。新增页面不得使用 raw `response.text()`、raw JSON、endpoint、request id、traceback 或 provider key 状态作为默认错误内容。
21. `StatusBanner`、`ErrorState`、`control-feedback`、`WorkflowFeedback` 等状态面必须统一语义：error 使用 `role="alert"`，success/running 使用 `role="status"`，loading 使用 `aria-busy`，warning 若会影响当前任务也应可被辅助技术感知。不要只靠颜色表达错误、警告或成功。
22. `info-trigger` 是现有 icon-only help pattern，依赖 `aria-label` 和 `data-tooltip`。新增 icon-only 帮助按钮必须有可读 `aria-label`、稳定尺寸、hover/focus tooltip；它只能解释上下文，不能承载主操作、长说明或错误恢复路径。
23. `HypothesisWorkspace` 已形成 `ResearchFlowGuide`、`DetailsTabs`、`StatusBadgeRow` 等事实模式；`DataPage` 已形成 `ParseRunChecklist`、`RagEvidenceSearch`、`EvidenceDetail`、`DataMetric` 等事实模式。它们虽未抽到 `components/`，但后续生成假设比较、证据检索、PDF 解析检查或质量灯时应优先沿用这些结构，而不是新造另一套流程卡、指标卡或证据结果卡。
24. `DataPage` 的数据服务错误目前使用 `EmptyState` 展示“数据资产暂时不可用”，这容易弱化错误语义。后续新页面应优先用 `ErrorState` 或 `StatusBanner tone="error"` 承载服务不可用、权限失败、解析失败等错误，并保留 `role="alert"`。
25. `DataPage` 的“人工/多模态复核”是 disabled future action。后续所有 disabled 按钮必须配套说明不可用原因、解锁条件或替代路径，不要只放一个没有解释的 disabled control。
26. `AdminPage` 当前账号创建和密码重置表单内有默认临时密码状态。后续生成器不能复制默认密码值；密码类字段应默认空值或使用 placeholder，并要求管理员显式输入或生成一次性临时密码。
27. 当前 repo 还没有“自动项目知识库索引 + 项目问答聊天框”的页面、typed API 和 view-model contract；已有 `session-search`、RAG search、research skills/tasks 可以作为支撑，但不能被宣传成完整项目知识问答。新增该能力时必须补齐索引来源、更新触发、回答引用、权限边界、状态设计和 progressive disclosure。
28. 项目知识问答的用户入口不应命名为“Memory / Vector DB / MCP / Agent Chat”；默认用户文案建议为“项目问答”或“项目知识助手”。内部实现可以叫 `project_knowledge_index`，但主导航和页面标题必须按研究员理解任务命名。
29. `frontend-system-design.md` 是更底层的可复用设计系统 contract；本文是面向生成器的全站 prompt。两者发生冲突时，以真实代码和 `frontend-system-design.md` 的硬性设计系统规则为准，再同步修正本文。

---

## 2. 当前全站布局体系

当前布局主要由以下文件驱动：

- `src/styles.css` 入口文件
- `src/styles/index.css` 聚合入口
- `src/styles/layout.css`
- `src/styles/components.css`
- `src/styles/responsive.css`
- `src/styles/tokens.css`

说明：

- `src/styles.css` 只负责 import `styles/index.css`
- 真实 token 定义在 `src/styles/tokens.css`，经 `styles/index.css` 汇入全站
- 新增颜色、间距、圆角、阴影和控制高度时，应先扩展 token，而不是在页面或 feature 中散落一次性值

### 2.1 App Shell

全站主应用采用：

- 左侧固定 `nav rail`
- 右侧滚动 `workspace`

对应类名：

- `.app-shell`
- `.nav-rail`
- `.workspace`

页面工作区容器：

- `.page-stack`

结论：

- 登录页是单独布局，不进 AppShell
- 其余主页面都应默认服从 `AppShell + page-stack`

### 2.2 页面头部

几乎所有主页面统一使用：

- `PageHeader`

结构：

- kicker
- title
- description 可选
- actions 可选

设计要求：

- 顶部必须优先说明当前任务，不是装饰性 hero
- 页面第一屏必须回答：
  - 我在哪
  - 我现在能做什么
  - 下一步是什么

### 2.3 常见布局骨架

当前站内已出现以下高频布局模式：

1. 单列任务流
- `page-stack`
- `section-stack`

2. 项目概览主面板
- 优先使用候选假设板、当前选择和下一步操作。
- 不在 ProjectDetailPage 默认铺设“当前阶段 / 最近产出”两列静态卡；阶段和产出信息进入对应子工作区、报告页或按需详情。

3. 左表单右结果工作台
- `.studio-grid`
- 左：`RunComposer`
- 右：`HypothesisWorkspace`

4. 主内容 + 右侧 readiness rail
- `.home-command-layout`
- `.readiness-rail`

5. 登录双栏
- `.login-shell`
- `.login-card`
- `.login-status-panel`

6. 工具卡片 / 工作流卡片网格
- `.tool-grid`
- `.workflow-path`
- `.workflow-step-card`
- `.tool-card`

7. 项目详情二级导航
- `.detail-nav`

8. Surface 容器
- `.surface-card`
- `.task-surface`

结论：

- 后续新增页面应优先复用这些布局模式
- 不要重新引入另一套 dashboard grid 语言

### 2.4 响应式断点

当前响应式语义：

- `<= 1279px`
  - 两列开始折叠
  - `studio-grid` 变单列
  - `login-shell`、`home-command-layout`、`admin-grid` 变单列
- `<= 959px`
  - `nav-rail` 不再固定
  - 主内容变单列
  - `primary-nav` 变 3 列
  - `workflow-path`、`card-grid`、`overview-grid` 变单列
- `<= 639px`
  - `primary-nav` 变 2 列
  - 按钮、导航链接、关键行动区尽量 100% 宽
  - drawer 变全宽
  - 复杂表格变堆叠或横向滚动

硬约束：

- 所有关键 CTA 在移动端不能掉出首屏太远
- 不允许仅桌面可用
- 状态变化不能引起布局抖动

### 2.5 动效、drawer 与 overlay

当前动效和 overlay 主要由以下文件支撑：

- `src/lib/motion/useReducedMotion.ts`
- `src/lib/motion/useAnimeEntrance.ts`
- `src/lib/motion/useAnimatedNumber.ts`
- `src/styles/overlays.css`
- `src/styles/components.css`
- `src/styles/responsive.css`

当前已经存在的动效语义：

- route / page entrance
- hypothesis list / timeline / summary list entrance
- reference drawer entrance
- animated metric count
- skeleton loading pulse
- spinner loading feedback

生成约束：

- 动效只能表达层级、状态变化、任务推进或 loading feedback，不做装饰性循环动画。
- 新增动效应复用 `src/lib/motion/` hook，必须尊重 `prefers-reduced-motion`。
- 不要动画化会改变布局的 width、height、margin、padding、grid track 或 control height。
- drawer / overlay 必须使用 `role="dialog"`、`aria-modal`、明确标题、关闭按钮、Escape close 和焦点恢复；小屏时转近全屏或全屏。
- backdrop 可以使用 `role="presentation"`；真正可读内容必须位于 dialog 内，不能把交互放在 backdrop 上。

---

## 3. 当前页面职责与布局解析

本节是给页面生成器看的页面级 contract。

### 3.1 LoginPage

文件：

- `src/pages/login/LoginPage.tsx`

当前职责：

- 账号入口面
- researcher / register / admin 三模式切换
- 登录或注册
- 展示账号机制与工作区准备摘要

当前布局：

- 左：登录卡片
- 右：状态面板

关键控件：

- mode tabs
- email input
- password input
- password reveal button
- remember checkbox
- submit button
- admin entry / register toggle link

当前语义特点：

- 不是 marketing hero
- 偏账号机制和 workspace access
- 右侧说明身份边界、审计归属、SQLite 持久化、管理员/研究员差异

后续优化方向：

- 可继续保留 workspace access surface 定位
- 如新增 landing，login 仍不应转回营销页语义

### 3.2 HomePage

文件：

- `src/pages/home/HomePage.tsx`

当前职责：

- 已登录后的 command center
- 搜索工作流/工具
- 继续最近研究
- 进入 workflows / tools / data / admin

当前布局：

- `PageHeader`
- `command-center` 搜索区
- `home-command-layout`
  - 主列：继续工作、工作流、工具
  - 侧列：readiness rail

关键控件：

- search input
- quick action links
- workflow cards
- tool chip cards
- readiness actions

页面语义：

- 已经比较接近 command center
- 不是被动 dashboard

建议保持：

- 首页以“继续研究”和“下一步操作”为主
- 不要变成纯统计概览页

### 3.3 WorkflowsPage

文件：

- `src/pages/workflows/WorkflowsPage.tsx`

当前职责：

- 把研究工作流按阶段显式列出
- 提供 recent projects 继续入口

当前布局：

- `PageHeader`
- `workflow-path`
- `card-grid` 最近项目

关键控件：

- workflow step cards
- create research CTA
- recent project cards

页面语义：

- 强调 workflow first
- 用步骤卡组织，不是菜单堆砌

### 3.4 ToolsPage

文件：

- `src/pages/tools/ToolsPage.tsx`

当前职责：

- 工具工作台
- 不是“工具大全展示页”，而是带审批/状态/结果预览的任务面

当前已整合内容很多，包含：

- 工具分类筛选
- session search
- file snapshot workflow
- web extract workflow
- schedules
- delegations
- background jobs
- research skills
- research tasks

当前局部子组件和职责：

- `WorkflowCardHeader`
  - 每个工具 workflow 的标题、说明、状态 chip 和 readiness 文案
- `WorkflowFeedback`
  - idle / loading / success / error 的稳定反馈槽位
- `SessionResultList`
  - session search 结果摘要，按 result type / summary / target ref 可检查
- `FileSnapshotPreview`
  - 文件快照结果摘要，hash、snapshot path、定位信息放入 details
- `WebExtractPreview`
  - 网页证据抽取结果摘要，final URL、PDF links、artifact path 放入 details
- `ResearchSkillList`
  - research skill 模板的只读摘要
- `SchedulePlanner`
  - 创建 schedule 和 tick 到期任务，不直接执行外部工具
- `DelegationPlanner`
  - 创建 planned delegation，真正运行仍需要 approval 和 provider readiness
- `OperationList`
  - research task / delegation / schedule 等轻量队列行
- `BackgroundJobList`
  - 后台任务状态摘要和 result ref

关键控件类型非常丰富：

- category filter buttons
- search form
- text inputs
- numeric inputs
- checkbox approval
- textarea-like reason inputs
- submit buttons
- result preview panels
- status strips
- list panels

布局模式：

- 工具卡片网格
- 多 section 工作台面板
- “表单 + 结果预览 + 状态反馈”混合布局

生成约束：

- 默认显示任务化摘要
- 工具的高风险细节必须后置
- 不要把 ToolsPage 做成开发者终端或 API playground
- 新增工具面板必须保持同一结构：任务目标说明、scope/reason、approval checkbox、提交按钮、稳定反馈槽位、结果摘要、details 中的 artifact/provenance。
- file / web / browser / code / experiment 这类工具不得绕过 approval-backed workflow；普通工具页不应出现任意 shell、任意路径遍历、raw terminal 或 raw API console。
- schedule tick 只能创建 ready task；delegation 创建后默认是 planned 状态；background job 默认显示摘要和状态，不把完整 stdout/stderr/result payload 铺在页面上。

### 3.5 DataPage

文件：

- `src/pages/data/DataPage.tsx`

当前职责：

- 数据资产面
- PDF 解析与入库
- parse runs 管理
- evidence 检查
- RAG evidence search

当前布局特征：

- 顶部 `PageHeader`
- 搜索 + filter
- 资产列表
- 解析任务表单
- 解析任务详情
- evidence detail drawer/panel

关键控件：

- filter chips
- query search
- parse input mode toggle
- upload input
- local path input
- submit parse button
- rag query input
- rag result cards
- evidence detail close/open

当前局部子组件和职责：

- `ParseRunChecklist`
  - 展示 PDF parse run 的 item 状态、风险灯、媒体数量和可打开的 evidence item
- `RagEvidenceSearch`
  - 任务化 RAG 检索表单和结果卡片
- `EvidenceDetail`
  - parse item 的 source reliability、support level、section path、media、experiment summary 等审计信息
- `DataMetric`
  - 顶部数据准备摘要的轻量指标

页面语义：

- 是 evidence pipeline 的控制面
- 不是普通文件管理器

硬约束：

- PDF parsing 必须被表述为 evidence grounding 的一部分
- 不能变成“独立 PDF 转换工具站”
- 上传 PDF、输入本机路径、parse run 回查、RAG evidence search 都属于同一 evidence workflow，不应被拆成互不关联的文件工具。
- 解析成功默认反馈只说“已写入知识库、生成片段/媒体/证据项”；`parse_run_id`、`chunk_id`、`solve_dir`、本机绝对路径和 media artifact path 只进 drawer/detail/expert inspection。
- RAG 结果卡默认展示 query 命中摘要、support level、source reliability；长 chunk、section path、internal IDs 进入详情。
- PDF 解析 loading/disabled/success/error 必须保留稳定高度和 `aria-busy`，解析中禁止重复提交。

### 3.6 WorkspacePage

文件：

- `src/pages/workspace/WorkspacePage.tsx`

当前职责：

- 核心研究工作区
- 左侧 run composer
- 右侧 hypothesis workspace

布局：

- `studio-grid`

左侧：

- `RunComposer`

右侧：

- `HypothesisWorkspace`

这是当前最重要的产品主页面，后续任何 landing/home/workflow 优化都不能破坏这里的主工作流地位。

### 3.7 RunComposer

文件：

- `src/features/runs/RunComposer.tsx`

职责：

- 输入 `research goal`
- 展示 readiness / blocked reason
- 触发 run
- 提供 expert settings

关键控件：

- `textarea` for research goal
- run button
- refresh / start literature service / clear run
- model select
- think mode switch
- literature switch
- 4 个 slider：
  - initial hypotheses
  - iterations
  - min references
  - max references

页面语义：

- 强调 goal-driven workflow
- 明确文献服务未就绪时的阻塞反馈
- expert settings 默认折叠

### 3.8 HypothesisWorkspace

文件：

- `src/features/hypotheses/HypothesisWorkspace.tsx`

职责：

- 显示候选假设列表
- 选中假设详情
- 中文翻译
- 参考文献抽屉
- audit disclosure
- details tabs

主要结构：

- output header
- research flow guide
- hypothesis list
- selected hypothesis panel
- disclosure panel
- timeline panel
- detail tabs
- reference drawer

关键控件：

- hypothesis option cards
- references button
- translation button
- experiment / report links
- tabs
- audit disclosure toggle

重要语义：

- 默认不展开全部过程和证据
- 通过 disclosure 和 reference drawer 渐进展示
- 明确“先比较、再看证据、再进入实验”

这是整站“progressive disclosure”做得最典型的一页，后续新页面应参照它，而不是直接铺满细节。

### 3.9 ProjectsPage

文件：

- `src/pages/projects/ProjectsPage.tsx`

职责：

- 项目列表

布局：

- `PageHeader`
- `card-grid`

控件：

- project cards
- new research CTA

### 3.10 ProjectDetailPage

文件：

- `src/pages/projects/ProjectDetailPage.tsx`

职责：

- 项目详情容器
- 通过子路径切换 papers / hypotheses / experiments / reports / overview

布局：

- `PageHeader`
- `detail-nav`
- 主体根据子路径切换内容

视图类型：

- overview
- papers
- hypotheses
- experiments
- reports

该页是典型的“单资源多视图容器”，后续如果新增 `findings`、`figures`、`methods` 等项目子页，应沿用这种模式。

当前 `.detail-nav` 标签已经统一为中文 `概览 / 论文 / 假设 / 实验 / 报告`。如果后续新增项目子页，必须继续统一同一导航层的语言；普通中文产品路径优先使用中文任务标签，不要重新混用 `Overview / Papers / Hypotheses` 这类英文导航。

### 3.11 OutputsPage

文件：

- `src/pages/outputs/OutputsPage.tsx`

职责：

- 聚合研究产出

布局：

- `PageHeader`
- `compact-grid` output cards
- 无内容时 EmptyState

### 3.12 AdminPage

文件：

- `src/pages/admin/AdminPage.tsx`

职责：

- 运行控制面 / readiness / 账号管理

当前模块：

- admin metrics
- readiness 状态
- 用户与角色
- 研究能力状态
- 任务队列
- 账号管理表单
- 账号列表操作
- expert settings / slider / select / switch

关键控件：

- buttons
- inputs
- select
- sliders
- table rows
- action buttons for enable/disable/reset

重要语义：

- 它是 product-facing control plane
- 不应退化成裸开发者控制台

### 3.13 ProjectKnowledgeChat / 项目问答（新增规范）

当前状态：

- 当前 repo 还没有独立项目问答页面、聊天组件或项目知识库索引 API
- 已有支撑能力包括：
  - `GET /api/session-search`
  - `GET /api/knowledge/search`
  - `GET /api/knowledge/rag/search`
  - `GET /api/research-skills`
  - `GET /api/research-tasks`
  - `GET /api/tools/background-jobs`
  - `src/app/router.tsx`
  - `src/lib/api/workbench.ts`
  - `src/lib/view-models/workbench.ts`
  - `docs/frontend-system-design.md`
  - 本文档

建议用户入口：

- 主文案：`项目问答` 或 `项目知识助手`
- 可作为 `/home` 的 command center 入口、`/tools` 的知识工具入口，或未来新增 `/project-chat`
- 不应在普通导航中命名为 `Memory`、`Vector DB`、`MCP`、`Agent Chat`、`Tool Call`

自动项目知识库索引 contract：

- 索引目标是帮助研究员理解“这个项目目前具备什么功能、如何运行、哪些页面负责什么、哪些能力只是 demo/计划中”
- 必须索引当前 workspace 内与项目理解直接相关的文本来源：
  - `AGENTS.md`
  - `系统设计总纲.md`
  - `open-coscientist/README.md`
  - `open-coscientist/pyproject.toml`
  - `open-coscientist/webapp/package.json`
  - `open-coscientist/webapp/README.md`
  - `open-coscientist/webapp/docs/*.md`
  - `open-coscientist/webapp/src/app/router.tsx`
  - `open-coscientist/webapp/src/pages/**/*.tsx`
  - `open-coscientist/webapp/src/components/**/*.tsx`
  - `open-coscientist/webapp/src/features/**/*.tsx`
  - `open-coscientist/webapp/src/lib/api/**/*.ts`
  - `open-coscientist/webapp/src/lib/view-models/**/*.ts`
  - `open-coscientist/webapp/src/types/**/*.ts`
  - `open-coscientist/webapp/backend/app.py`
  - `open-coscientist/webapp/backend/requirements.txt`
- 索引不应读取 `.auth/`、`.codex/`、`.coscientist_cache/`、`node_modules/`、`dist/`、日志文件、SQLite 私密账号库、环境变量、provider key 或任意 workspace 外路径
- 索引记录至少包含：
  - source type: `doc` / `route` / `page` / `component` / `api_client` / `backend_api` / `schema` / `test`
  - relative path
  - title / symbol / route / endpoint
  - summary
  - responsibilities
  - user-facing capability
  - implementation boundary
  - last indexed time
  - content hash
  - chunk refs
- 索引更新触发：
  - 首次打开项目问答时自动检查索引状态
  - 文件 hash 变化时提示“索引过期”
  - 用户点击“重新索引”后进入 indexing 状态
  - 长耗时索引应使用 background job 或等价任务状态，不阻塞主 UI

建议 API / typed client contract：

```text
GET  /api/project-knowledge/index
POST /api/project-knowledge/reindex
POST /api/project-knowledge/chat
GET  /api/project-knowledge/sources/{source_id}
```

前端必须通过 `src/lib/api/workbench.ts` 或拆出的 typed API client 调用，不要在组件里散落 raw fetch。响应进入 `src/types/workbench.ts` 和 view-model 层后再给 UI 使用。

聊天回答 contract：

- 回答只解释项目功能、运行方式、页面职责、API/工具边界、文档规范、已实现/未实现状态
- 不回答真实科学结论，除非问题引用已有 evidence source；不能把 demo/synthetic run 当作科学证据
- 每条回答必须带 `sources` 摘要，默认只显示 2-4 个 source chips
- source chip 默认显示相对路径或用户任务名，例如 `router.tsx`、`DataPage`、`PDF 解析 API`
- 完整 source path、hash、chunk id、raw excerpt、endpoint detail 进入 drawer / details / expert inspection
- 若索引缺失、过期、无法读取或来源不足，回答必须标注 `limited` / `index stale` / `source missing`
- 若问题要求执行运行、解析 PDF、调用外部工具或修改账号，聊天只能给任务入口和步骤，不得绕过已有 approval-backed workflow

ChatGPT 式聊天框 UI contract：

- 桌面推荐布局：
  - 左侧：`ProjectKnowledgeIndex` 摘要栏，列出页面、组件、API、文档、运行方式等索引块
  - 中间：`ProjectKnowledgeChat` 消息流
  - 底部：固定 `ChatComposer`
  - 右侧或 drawer：source/evidence detail，仅用户点击引用后打开
- 移动布局：
  - 单列消息流
  - 顶部 segmented tabs：`问项目` / `索引` / `来源`
  - source detail 使用全屏 drawer
- 消息组件：
  - `assistant` / `user` / `system` / `tool-status`
  - assistant 默认显示自然语言答案、mode badge、source chips、复制按钮、打开来源按钮
  - tool/indexing 状态不能显示 raw tool result
- composer：
  - 多行 textarea，固定最小高度，最大高度后内部滚动
  - `Enter` 发送、`Shift+Enter` 换行
  - send icon button 必须有 `aria-label`
  - loading 时保留按钮尺寸并设置 `aria-busy`
  - 禁用时必须说明原因，例如“索引不可用，先重新索引”
- 状态必须覆盖：
  - idle
  - indexing
  - answering
  - success
  - empty
  - error
  - limited / ungrounded
  - permission denied
  - offline
  - timeout
  - retrying
- 不允许：
  - 默认铺开 raw JSON / raw source excerpt / absolute local path
  - 把 Chat 做成全局客服悬浮球遮挡主工作流
  - 把 project knowledge chat 和 hypothesis generation chat 混成一个入口
  - 让聊天直接执行高风险工具、账号操作、文件写入或外部抓取

Figma 设计稿：

- 本次核对已创建可编辑 Figma 文件：
  - `Open Co-Scientist Project Knowledge Chat`
  - `https://www.figma.com/design/cAytW4WrbSJ8DAjxDEiczt`
- 文件中包含：
  - `Final Spec / Project Knowledge Chat Desktop`
  - `Final Spec / Project Knowledge Chat Mobile`
  - `Final Spec / Component State Contract`
- 后续若代码实现该功能，应以本节 contract 和 Figma `Final Spec` frame 为准，而不是早期草稿 frame。

### 3.14 LibraryPage 与 SettingsPage

这两页目前更多是兼容性残留：

- `LibraryPage` 已被 `/data` 路径吸收
- `SettingsPage` 已被 `/admin` 路径吸收
- 当前路由访问 `/library`、`/library/papers`、`/library/references`、`/settings` 时会直接跳转，不会渲染这两个 page 文件

生成新页面时：

- 不要再强化它们为新的主入口
- 可以吸收其局部 pattern，但最终应以 `/data`、`/admin` 为主

---

## 4. 全站复用控件语义

后续页面生成必须优先沿用以下控件类型，而不是另造一套视觉系统。

### 4.1 主按钮体系

现有按钮语义：

- `.button-primary`
- `.button-secondary`
- `.button-ghost`

规则：

- primary 只给当前页面主任务
- secondary 给次主操作
- ghost 给轻量恢复、折叠、辅助操作

### 4.2 状态反馈体系

现有状态组件：

- `EmptyState`
- `LoadingState`
- `SkeletonState`
- `SuccessState`
- `ErrorState`
- `StatusBanner`

规则：

- 页面不能只设计 happy path
- 至少要覆盖：
  - loading
  - empty
  - success
  - error
  - blocked / warning
  - disabled
- 当前高频使用的是 `EmptyState`、`LoadingState`、`SkeletonState`、`StatusBanner`；`SuccessState`、`ErrorState` 虽已导出但暂未在页面中使用。新增页面可以使用，但样式和文案必须与 `control-feedback` / `status-banner` 体系保持一致。

### 4.3 表单控件体系

已存在的表单模式：

- `field-stack`
- `field-label`
- `password-field`
- `slider-row`
- `toggle-row`
- checkbox row

规则：

- 每个输入控件都要有 label
- focus-visible 必须清楚
- loading/disabled 不能导致 layout shift
- reason / approval / scope 类型信息优先靠近提交按钮

### 4.4 渐进展开体系

当前站内主要通过以下方式隐藏复杂度：

- `DisclosurePanel`
- `ReferenceDrawer`
- `detail tabs`
- `detail-nav`
- `selected panel`

规则：

- 默认不直接展示：
  - agent trace
  - citation map
  - ranking reasoning
  - raw metrics
  - provider diagnostics
  - internal IDs
- 所有深层信息都需要用户主动展开

### 4.5 项目问答控件体系（新增规范）

项目问答不是 hypothesis generation chat，也不是全局客服浮窗。它是帮助研究员理解当前项目功能、运行方式、页面职责和能力边界的任务入口。

建议组件：

- `ProjectKnowledgeIndex`: 自动项目知识库索引摘要、索引状态、重新索引入口
- `ProjectKnowledgeChat`: ChatGPT 式消息流
- `ProjectKnowledgeMessage`: `user` / `assistant` / `system` / `tool-status` 消息
- `ProjectKnowledgeComposer`: 多行输入、发送按钮、禁用原因
- `ProjectKnowledgeSourceChip`: 默认 2-4 个来源摘要 chip
- `ProjectKnowledgeSourceDrawer`: 来源详情、chunk、hash、相对路径、excerpt
- `KnowledgeIndexStatus`: `ready` / `stale` / `indexing` / `limited` / `error`

规则：

- 默认只显示答案、模式标识、少量 source chips 和下一步建议
- 完整 source path、hash、chunk id、raw excerpt、endpoint detail 必须进入 drawer / details / expert inspection
- `ChatComposer` 必须支持 `Enter` 发送、`Shift+Enter` 换行、稳定高度、loading disabled 状态和 `aria-busy`
- 发送按钮优先使用 lucide icon button，并提供 `aria-label`
- 消息列表应使用可读宽度，不做全屏指标仪表盘；source index 可以在桌面左栏、移动端 tab 中出现
- index/reindex 是异步任务状态，不显示 raw tool result、traceback 或内部文件扫描日志
- 回答不应直接执行 PDF 解析、网页抓取、账号修改、实验运行或外部工具调用；只能引导用户进入已有 approval-backed workflow

### 4.6 数据展示体系

当前数据展示不是传统 chart dashboard，而是：

- `SummaryList`
- cards
- list rows
- table-like rows
- process timeline
- evidence cards

规则：

- 不要优先做花哨图表
- 先做能支持判断和操作的数据组织

### 4.7 审计与 artifact 细节展示

当前页面已经存在以下可审计细节：

- parse run / evidence item detail
- chunk、section path、source reliability、support level
- content hash、snapshot path、final URL
- schedule、task、background job、delegation 摘要

规则：

- 默认列表只显示用户能判断下一步的摘要，例如状态、覆盖、更新时间、支撑级别
- 内部定位字段只能放入 drawer、details、DisclosurePanel、专家设置或调试入口
- `run_id`、`parse_run_id`、`task_id`、`job_id`、`delegation_id`、`chunk_id`、本机绝对路径、artifact path、hash 不能成为默认卡片标题、首页指标或普通用户主路径文案
- `evidence_id`、`solve_dir`、`snapshot_path`、`content_hash`、`content_sha256`、`target_ref`、`result_ref`、`workflow_name` 也属于审计定位字段。默认 UI 只能展示用户可判断的摘要，例如“已入库”“已保存证据快照”“3 个 PDF 线索”；完整定位信息进入 details / drawer / expert inspection。
- 错误信息要任务化表达恢复路径，不显示 traceback、raw exception、raw JSON
- 如果旧实现、生成输出或未来改动又在默认反馈中暴露内部字段，例如解析成功摘要中的 `parse_run_id` 或空状态里的“后端 API”，后续重构应收敛为用户任务文案，并把内部字段移动到详情或专家检查入口。
- API client / view-model 层应输出 safe user message；页面组件不得直接把后端 `response.text()`、JSON detail、provider error、HTTP endpoint 或 `error.message` 当作默认用户反馈，除非该 message 已经过 `parseApiError` 或等价 sanitizer。

内部术语默认转译规则：

| 实现/治理词 | 默认用户文案 |
| --- | --- |
| workflow | 研究任务流程 |
| skills | 方法模板 |
| phases | 适用阶段 |
| agents | 审查角色 / 子任务 |
| SQLite provenance | 本地审计记录 |
| approval guardrail | 执行前确认 |
| provider | 模型通道 |
| endpoint | 服务地址，仅专家详情可见 |
| target_ref / result_ref | 关联对象 / 结果引用，仅审计详情可见 |

### 4.8 可访问性交互语义

当前站内已经出现的 ARIA / interaction pattern：

- drawer:
  - `role="dialog"`
  - `aria-modal="true"`
  - `aria-labelledby`
  - close button `aria-label`
  - Escape close
  - focus return
- segmented control / tabs:
  - wrapper `role="tablist"`
  - option `role="tab"`
  - selected state `aria-selected`
- hypothesis list:
  - list `role="listbox"`
  - item `role="option"`
  - selected state `aria-selected`
- switches:
  - `role="switch"`
  - `aria-checked`
- async feedback:
  - `aria-busy`
  - `role="status"` 或 `role="alert"`

规则：

- 新增 drawer、modal、side panel 必须补齐 dialog 语义、标题、关闭按钮、Escape close、焦点恢复；需要键盘困住焦点时，优先复用 `ReferenceDrawer` 的焦点遍历模式。
- 新增 segmented control 如果本质是互斥视图切换，使用 tablist/tab/aria-selected；如果只是普通 filter button，应明确 selected visual state 和键盘 focus-visible。
- 新增 switch 不能只是视觉 toggle，必须有 `role="switch"`、`aria-checked` 和禁用态。
- loading 只用 spinner 不够，提交按钮和结果区域要有 `aria-busy`；错误要靠文字和 `role="alert"`，不能只靠红色。
- `StatusBanner`、`ErrorState`、`WorkflowFeedback`、`control-feedback` 的语义必须和视觉 tone 对齐：error -> `role="alert"`，success/running -> `role="status"`，loading -> `aria-busy`，会阻塞当前任务的 warning 也应使用 alert 或明确的状态文案。
- icon-only help control 使用现有 `info-trigger` 模式：必须有 `aria-label`、稳定 40px 左右命中区域、hover/focus tooltip；它只解释上下文，不承载主操作、长文档、错误恢复或隐藏配置。
- native `<details>` 目前主要用于专家/证据文件折叠；新增时只放低频审计细节，不要用它承载主工作流。

---

## 5. 全站文案边界

### 5.1 必须坚持的产品表述

可以说：

- `Open Co-Scientist`
- `open adaptation / local workbench`
- `research workbench`
- `hypothesis generation`
- `literature grounding`
- `review / critique`
- `ranking / tournament`
- `evolution / refinement`
- `evidence inspection`

不能说：

- Google 官方原始系统
- 已实现生产级自动科学发现
- demo 输出就是真实科学发现

### 5.2 必须显式区分的三种模式

页面和文案必须始终能区分：

1. `Demo simulation`
- 仅用于 UI、流程、schema、交互验证

2. `Live model workflow`
- 使用真实模型运行 hypothesis workflow

3. `Literature-grounded workflow`
- 依赖文献、PDF/fulltext、知识库证据

若 grounding 不足，必须标注：

- `limited`
- `ungrounded`
- `latent-knowledge based`

不能伪装成文献已验证。

---

## 6. 未来页面生成硬规则

给任何生成器时，都要附带以下硬规则。

### 6.1 IA 规则

- 导航必须按研究任务组织
- 禁止把系统内部结构做成主导航：
  - Agent
  - Workflow internals
  - MCP
  - Prompt
  - Tool call
  - Memory
  - Vector DB
  - Provider key

### 6.2 页面优先级规则

所有页面第一屏只应突出：

- 当前任务
- 当前状态
- 当前主操作
- 明确下一步

### 6.3 默认隐藏规则

以下内容必须默认隐藏到 drawer / detail / disclosure / expert settings：

- reference list
- citation map
- agent trace
- raw metrics
- ranking details
- provider diagnostics
- internal IDs
- raw JSON
- stack trace
- local absolute paths
- artifact paths
- content hashes
- repair commands

### 6.4 状态设计规则

所有关键按钮和输入必须定义：

- default
- hover
- active
- focus-visible
- disabled
- loading
- success
- error

### 6.5 响应式规则

- mobile 首屏必须看得懂、点得到
- 平板不能只是桌面缩小版
- 大型表格必须可滚动或重组
- drawer 在小屏要转全屏/近全屏

### 6.6 视觉规则

- 克制、可信、科研工具感
- 不要 SaaS 紫色模板化
- 不要卡片套卡片泛滥
- 不要夸张动效
- 优先 readability 和 hierarchy

---

## 7. 给生成器的全站规范长 Prompt

下面这段可直接提供给 Lovable、Figma 或其他代码生成器。若是代码生成场景，建议把它作为 system/developer prompt；若是设计稿生成场景，建议作为 main brief。

```text
请基于当前仓库 `open-coscientist/webapp` 的真实页面结构、路由组织、布局模式和研究工作台产品边界，生成新的页面或重构方案。你必须遵守以下 contract，不要把项目做成普通 SaaS 官网、宣传站、开发者控制台或 PPT 式 demo。

【项目身份】
- 产品名：Open Co-Scientist
- 这是一个基于公开论文思想的 open adaptation / local workbench
- 不是 Google 官方原始 AI co-scientist 系统
- 不是团队自动化 SaaS
- 不是营销站
- 核心任务是围绕 research goal 推进：
  - planning
  - literature grounding
  - hypothesis generation
  - review / critique
  - ranking / tournament
  - evolution / refinement
  - proximity / deduplication
  - evidence inspection
  - human-in-the-loop review

【当前页面结构】
当前 repo 已存在或已约定的主页面包括：
- /login
- / -> redirect to /home inside protected AppShell
- /home
- /workflows
- /tools
- /data
- /projects
- /projects/:projectId
- /workspace
- /outputs
- /admin

兼容页面存在：
- /library
- /settings

注意：当前 `/library*` 和 `/settings` 在 `router.tsx` 中会跳转到 `/data` 和 `/admin`，不要把 `LibraryPage`、`SettingsPage` 当作 active route contract 继续强化。
特别注意：`SettingsPage` 是旧兼容实现，不是新的控件规范来源。参考文献 min/max slider、运行准备入口、管理员设置都以 `/admin`、`RunComposer` 和 `AdminPage` 的当前模式为准。

如需新增公共落地页，新增：
- / -> LandingPage

注意：这会改变当前 `/` 的受保护 redirect 语义，必须同步修改 router、认证边界和导航入口；不要把 LandingPage 当作当前已存在页面。

如需新增项目知识问答页，可以新增：
- /project-chat

注意：当前 repo 还没有该 active route。新增时必须同步 router、导航入口、typed API client、types、view-model、索引任务状态和来源详情 drawer；不要把它命名为 `Memory`、`Vector DB`、`MCP` 或 `Agent Chat`。

【当前布局模式，必须优先复用】
1. AppShell：左侧 nav rail + 右侧 workspace
2. PageHeader：kicker + title + description + actions
3. page-stack：页面主栈
4. project overview：候选假设板 + 当前选择 + 下一步操作
5. studio-grid：左表单右结果
6. home-command-layout：主内容 + readiness rail
7. login-shell：双栏登录页
8. workflow-path / tool-grid：步骤卡和工具卡网格
9. surface-card / task-surface：任务面容器
10. detail-nav：项目详情二级导航
11. project-chat-layout：项目知识索引栏 + ChatGPT 式消息流 + source detail drawer（仅新增项目问答时使用）

CSS token 来源：
- `src/styles.css` 是 import 入口
- `src/styles/index.css` 聚合样式模块
- `src/styles/tokens.css` 是颜色、间距、圆角、阴影和控制高度 token 的真实定义位置

【当前技术与状态边界】
当前 runtime stack：
- React 19
- TypeScript
- Vite
- React Router
- @tanstack/react-query
- lucide-react
- animejs
- FastAPI bridge

状态与数据边界：
- `src/app/providers.tsx` 提供 QueryClientProvider、AuthProvider、WorkbenchProvider
- `src/features/runs/workbench-context.tsx` 持有 research goal、model、literature、reference budget、current run、selected hypothesis、detail tab、run history
- `src/features/runs/queries.ts` 和 `src/features/health/queries.ts` 负责 React Query 数据获取与轮询
- `src/lib/api/workbench.ts` 是 typed API client 边界
- `src/lib/view-models/workbench.ts` 是后端 run/evidence/schema 到 UI view model 的映射边界
- `src/types/workbench.ts` 是共享 schema 类型边界

生成新页面或重构时：
- 不要绕过 typed API client 直接在页面散落 raw fetch
- 不要在组件内重复解析 raw backend schema，应扩展 view-model 层
- 不要为 Workspace/run/hypothesis 重建第二套 context 状态
- React Query server state、workflow context state、短生命周期 form state 要分清
- API 错误必须转成任务化恢复文案，不展示 raw JSON、endpoint、request id 或 stack trace
- API client 或 view-model 层必须先产出 safe user message；页面不要直接渲染 raw `error.message`、HTTP response text、provider error、JSON detail 或后端 traceback
- 所有指向 `/admin` 的入口都必须遵守角色可见性。普通研究员不应在首页、工具页、空状态或卡片里看到会直接跳到受限路由的“运行准备 / 查看阻塞 / 运行参数”主入口

【当前复用组件语义】
- PageHeader：页面头部
- EmptyState / LoadingState / SkeletonState / SuccessState / ErrorState / StatusBanner：状态反馈。当前页面高频使用 EmptyState、LoadingState、SkeletonState、StatusBanner；SuccessState、ErrorState 已导出但不是高频现状。
- SummaryList：结构化摘要列表
- DisclosurePanel：默认隐藏复杂细节
- ReferenceDrawer：按需展开文献与证据
- ProjectCard / OutputCard / ReferenceCard：对象卡片
- info-trigger：icon-only 帮助按钮，必须有 `aria-label` 和 hover/focus tooltip，只解释上下文，不承担主操作
- HypothesisWorkspace 局部事实模式：ResearchFlowGuide、DetailsTabs、StatusBadgeRow
- DataPage 局部事实模式：ParseRunChecklist、RagEvidenceSearch、EvidenceDetail、DataMetric
- ToolsPage 局部事实模式：WorkflowCardHeader、WorkflowFeedback、SessionResultList、FileSnapshotPreview、WebExtractPreview、SchedulePlanner、DelegationPlanner、OperationList、BackgroundJobList
- ProjectKnowledgeChat 新增规范模式：ProjectKnowledgeIndex、ProjectKnowledgeChat、ProjectKnowledgeMessage、ProjectKnowledgeComposer、ProjectKnowledgeSourceChip、ProjectKnowledgeSourceDrawer、KnowledgeIndexStatus。当前还未实现，若新增必须按本文第 3.13 节和 Figma Final Spec 设计，不要另造全局客服浮窗。

【当前控件模式】
当前项目已经大量使用：
- button
- input
- select
- textarea
- checkbox
- range slider
- switch
- tabs
- drawer
- disclosure
- list row
- table row
- chat message list
- source chip
- source drawer
- multi-line chat composer

请延续这些控件模式，不要另外引入一整套和当前 repo 视觉/交互冲突的框架式组件语言。

ARIA 与可访问性必须匹配当前实现方向：
- drawer 使用 `role="dialog"`、`aria-modal`、标题、关闭按钮、Escape close、焦点恢复
- segmented control / tabs 使用 `role="tablist"`、`role="tab"`、`aria-selected`
- hypothesis selector 使用 `role="listbox"`、`role="option"`、`aria-selected`
- switch 使用 `role="switch"`、`aria-checked`
- async 提交和结果区域使用 `aria-busy`
- error 使用任务化文字和 `role="alert"`，success/running 使用 `role="status"`
- warning 如果会阻塞或改变当前任务路径，也要有清晰状态文案和辅助技术可感知语义
- 登录模式切换、数据类型筛选、工具分类切换等所有互斥 segmented control 都必须补齐 tab 语义，不要只用 `.selected`
- 项目问答消息流应有可感知的 answering/indexing 状态；composer loading 使用 `aria-busy`，source detail 用 drawer dialog 模式，source chip 必须是可聚焦按钮或链接

【信息架构硬约束】
默认界面必须优先暴露：
- 当前目标
- 当前任务
- 当前状态
- 主操作
- 下一步

不能把以下内容作为默认主界面结构：
- Agent
- Workflow internals
- MCP
- Tool call
- Prompt
- Memory
- Vector DB
- Provider key
- Raw API
- Run ID
- Request ID
- Stack trace
- Raw JSON

以下内容必须隐藏在 details / tabs / drawer / disclosure / expert mode 中：
- reference list
- citation map
- agent trace
- ranking reasoning
- raw metrics
- provider diagnostics
- internal IDs
- run_id / parse_run_id / task_id / job_id / chunk_id / evidence_id
- local absolute paths / artifact paths / solve_dir / snapshot_path / content hashes
- target_ref / result_ref / workflow_name
- project knowledge source hash / chunk id / raw excerpt / index scan log
- long debug payload

内部术语必须默认转译为用户任务语言：
- `workflow` -> 研究任务流程
- `skills` -> 方法模板
- `phases` -> 适用阶段
- `agents` -> 审查角色 / 子任务
- `SQLite provenance` -> 本地审计记录
- `approval guardrail` -> 执行前确认
- `provider` -> 模型通道

英文内部词只允许在专家详情、审计详情或管理员上下文中出现。

【三种运行模式必须显式区分】
1. Demo simulation
- 仅用于 UI、流程、schema、交互验证

2. Live model workflow
- 使用真实模型运行 hypothesis workflow

3. Literature-grounded workflow
- 依赖文献、PDF/fulltext 和知识库证据
- 若 grounding 不足，结果必须标记为 limited / ungrounded
- 不能伪装成已验证科学结论

【各页面职责】
1. LoginPage
- workspace access surface
- 不是营销页
- 展示 researcher/admin 身份边界与 readiness 摘要

2. HomePage
- 已登录后的研究主页 / command center
- 聚合继续工作、工作流入口、工具入口、数据准备状态
- 不是静态统计面板

3. WorkflowsPage
- 按研究步骤组织 workflow
- 不是系统菜单集合

4. ToolsPage
- 工具工作台
- 以任务 form + result preview + status 为主
- 不是 API playground
- 文件快照、网页证据、session search、schedule、delegation、background job 只能默认显示摘要；定位信息、hash、snapshot path、target_ref 必须放在 details/disclosure 中
- 新增工具面板沿用：任务说明、scope/reason、approval checkbox、提交按钮、WorkflowFeedback 风格反馈、结果摘要、details 中的 provenance/artifact
- schedule tick 只创建 ready task，不直接执行外部工具；delegation 默认 planned，真正运行仍需要 approval 和 provider readiness
- 默认文案不要裸露 workflow、skills、phases、agents、SQLite provenance、approval guardrail 等内部词；需要展示时先转成“研究任务流程 / 方法模板 / 适用阶段 / 审查角色 / 本地审计记录 / 执行前确认”
- 运行参数类工具入口属于管理员能力，普通研究员路径中应隐藏或改为任务化提示

5. DataPage
- 数据资产和证据面
- PDF parsing、knowledge ingestion、RAG evidence、parse runs
- 不是单独文件转换站
- PDF 解析成功反馈可以告诉用户已写入知识库和生成片段数量；本机路径、parse_run_id、chunk_id、solve_dir 等只能在详情或专家检查入口显示。若现有旧反馈已经出现内部 ID，重构时应移入 drawer/detail/expert inspection。
- 上传 PDF、本机路径解析、parse run 状态、RAG evidence search 必须被设计为同一 evidence workflow
- RAG result 默认显示摘要、support level、source reliability；长 chunk、section path、internal IDs 进入 drawer/detail
- RAG result 默认不得显示 evidence_id；资产默认说明不得包含 parse_run_id；“后端 API 不可用”应改写为“数据服务暂时不可用，可刷新或检查运行准备”
- PDF 解析成功反馈不得直接展示 solve_dir；产物目录只在详情或专家检查入口出现

6. WorkspacePage
- 核心研究工作区
- 左侧 RunComposer
- 右侧 HypothesisWorkspace
- 是主生产力页面

7. ProjectsPage
- 项目列表

8. ProjectDetailPage
- 单项目多视图容器
- papers / hypotheses / experiments / reports / overview
- 二级导航语言必须统一；中文产品路径优先使用 概览 / 论文 / 假设 / 实验 / 报告，不要混用中英文标签

9. OutputsPage
- 聚合研究产出

10. AdminPage
- readiness / control plane
- product-facing
- 不能退化成裸开发者控制台

11. ProjectKnowledgeChat（如新增）
- 项目功能问答和项目知识索引
- 解释当前项目能做什么、如何运行、页面/组件/API 职责和已实现/未实现边界
- 不是假设生成聊天，不产出科学发现，不替代 WorkspacePage
- 默认显示自然语言回答、limited/stale 等状态、2-4 个 source chips 和下一步建议
- 来源详情、chunk、hash、raw excerpt、相对路径和 endpoint detail 必须进入 drawer/details/expert inspection
- 索引来源限定在项目文档、路由、页面、组件、API client、view-model、types、backend API 和 requirements；不得读取 `.auth`、`.codex`、`.coscientist_cache`、`node_modules`、`dist`、日志、私密 SQLite 账号库、环境变量、provider key 或 workspace 外路径
- 重新索引、回答、来源详情都必须通过 typed API client 和 view-model contract，不要在组件里写 raw fetch 或渲染 raw backend schema

【视觉与交互要求】
- 整体气质：现代、克制、可信、科研工具感
- 可使用深色或中性色背景，但不要典型蓝紫 SaaS 模板
- 少量强调色可以使用 blue/cyan/slate
- 强调阅读清晰度和层级，不要过度玻璃化
- 动效轻微、克制
- hover / focus-visible / disabled / loading / error / success 状态必须完整
- 状态变化不能导致布局跳动
- 动效优先复用 `src/lib/motion/` hook，必须尊重 `prefers-reduced-motion`
- 不要动画化 width、height、margin、padding、grid track 或 control height

【响应式要求】
- Desktop：完整工作台
- Tablet：双列压缩或单列重排
- Mobile：单列优先，按钮可点，文本可读，抽屉可全屏化
- 不允许只优化桌面

【实现原则】
- 先复用现有页面结构和 CSS token 语言
- 先复用 PageHeader、SummaryList、StatusBanner、DisclosurePanel、drawer、state card
- 先复用 typed API client、React Query query/mutation、WorkbenchProvider 和 view-model 层
- 不要直接把 shadcn 官网模板贴进来
- 不要引入和当前 repo 冲突的重型 UI 框架
- 不要伪造 scientific claims
- 不要把 demo 内容说成真实研究发现

【输出要求】
- 给出需要修改或新增的文件列表
- 优先兼容现有路由和页面命名
- 组件命名应延续当前 repo 风格
- TypeScript 必须尽量无明显错误
- 需要完整处理 loading / empty / success / error / blocked / unavailable 等状态
- 如果新增项目问答，必须同时列出 indexer/API/types/view-model/component/CSS/route/navigation 的改动，并说明索引来源、排除路径、source drawer、stale/indexing/limited/error 状态和 Figma Final Spec 对齐情况
```

---

## 8. 推荐使用方式

### 8.1 给 Lovable

建议把本文第 7 节整体作为主 prompt，再附加你这次要改的页面目标。

示例：

- “基于这份全站 contract，只重做 `/` 和 `/login`”
- “基于这份全站 contract，把 `/home` 调整为 research command center”
- “基于这份全站 contract，为 `/data` 新增更清晰的 PDF parsing evidence flow”
- “基于这份全站 contract，新增 `/project-chat` 项目问答，但必须沿用 typed API、view-model、source drawer 和 project knowledge index contract”

额外提醒：

- Lovable 适合根据 contract 生成页面方案或外部原型，但回写本仓库时必须映射回现有 React Router、React Query、WorkbenchProvider、typed API client、CSS token 和 view-model 边界。
- 不要让 Lovable 生成脱离当前 repo 的新登录系统、新导航、新 API client、新 UI framework 或独立 dashboard。
- 如果 Lovable 生成项目问答，必须把它实现为项目知识索引和来源可审计问答，不要生成全局客服浮窗、聊天营销页或新的 hypothesis chat。
- 如果 Lovable 输出引入了新的页面效果、控件模式或状态模式，应先补回本文和 `frontend-system-design.md`，再进入代码实现。

### 8.2 给 Figma

建议保留：

- 第 1 节 repo 证据盘点
- 第 2 节布局体系
- 第 3 节页面职责
- 第 5 节文案边界
- 第 6 节硬规则

并补一句：

- “请输出 desktop / tablet / mobile 三套结构稿和关键状态稿”
- “项目问答请参考 Figma 文件 `Open Co-Scientist Project Knowledge Chat` 的 `Final Spec / Project Knowledge Chat Desktop`、`Final Spec / Project Knowledge Chat Mobile` 和 `Final Spec / Component State Contract` frame：`https://www.figma.com/design/cAytW4WrbSJ8DAjxDEiczt`”

### 8.3 给人工前端开发

建议将本文作为设计和实现前的共同 contract，并在任务单中附加：

- 这次修改影响哪些页面
- 是否新增公共 landing
- 是否涉及 `/admin` 权限边界
- 是否会新增 drawer / detail / tab 入口

---

## 9. 本文档结论

当前 `open-coscientist/webapp` 已经具备较明确的页面体系，核心不是“缺页面”，而是“需要一份能约束新增页面不跑偏的全站 contract”。这份文档的用途就是：

- 固化当前 repo 已有布局和控件模式
- 固化 research workbench 而不是 SaaS 官网的产品定位
- 固化 progressive disclosure 和 evidence-first 的 UI 逻辑
- 为后续 landing / login / home / data / tools / workspace / admin 的任何重构提供统一 prompt 基线
