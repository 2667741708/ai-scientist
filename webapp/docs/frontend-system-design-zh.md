# Open Co-Scientist 前端系统设计（中文版）

本文档是 `open-coscientist/webapp/` 的可复用前端设计系统契约。它将粘贴的前端设计原则中与项目相关的部分整合为本研究工作台的实现指南。

目标不是做一个好看的页面。目标是让专家用户以最小认知负担完成真实研究任务，同时保持可审计性、可追踪性和长期 UI 一致性。

## 1. 产品定位

`open-coscientist/webapp/` 是一个用于 AI 辅助研究的知识工作平台。它不是 PPT 风格演示、营销网站、后端控制台、模型提供商仪表盘或原始代理轨迹查看器。

前端呈现研究任务和工作队列：

```text
全局动作
  新建项目
  项目 AI
  任务队列
  资料库
  搜索

项目树
  置顶项目
    论文
    假设
    实验
    报告
    项目 AI
  其他最近项目

专家与运行
  研究工具
  研究产出
  运行准备
```

前端默认隐藏实现机制：

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

核心规则：

```text
暴露任务。隐藏系统复杂性。在用户明确操作后保留可审计性。
```

当前产品外壳刻意采用 Codex-style work queue / project tree，而不是传统功能菜单。项目 AI 的交互也应接近 Codex/Hermes：用户用自然语言表达目标，系统做语义路由、生成确认卡，并在明确授权后调用工具执行。

## 2. 框架契约

除非有强烈的本地理由，否则使用当前项目栈：

```text
React 19
TypeScript
Vite
CSS design tokens in src/styles.css
lucide-react for icon buttons and navigation glyphs
FastAPI bridge at webapp/backend
```

实现规则：

- 优先使用原生 React 组件和现有 CSS token 系统。
- 不要引入 UI 框架，除非重复的组件面真的需要它。
- 在 `lucide-react` 已经覆盖图标隐喻的情况下，不要添加另一个图标库。
- 在功能代码中不要创建一次性颜色、间距、圆角或阴影值。
- 仅当提取重复 UI 模式能够删除真实重复或澄清所有权时才提取。
- 保持真实控件代码原生。不要把静态截图作为 UI 发布。

## 3. 信息架构

信息架构以目标驱动，而不是系统驱动。

当前侧边栏信息架构：

```text
全局动作
  新建项目
  项目 AI
  任务队列
  资料库
  搜索

置顶
  当前或最近研究项目
    论文
    假设
    实验
    报告
    项目 AI

项目
  其他最近研究项目

专家与运行
  研究工具
  研究产出
  运行准备
```

含义：

| 导航 | 用户目标 | 隐藏的系统能力 |
| --- | --- | --- |
| 新建项目 | 输入研究目标并启动研究任务 | supervisor, planner, model request |
| 项目 AI | 通过对话询问项目能力、页面职责、运行步骤和证据边界 | RAG, semantic routing, tool proposal |
| 任务队列 | 查看正在运行或待确认的研究任务 | durable queue, worker, run state |
| 资料库 | 管理论文、网页证据、PDF 解析和知识库入库 | MCP, fulltext parser, citation map |
| 搜索 | 查找项目、资料和历史上下文 | session search, local indices |
| 项目子工作区 | 在项目上下文中进入论文、假设、实验、报告和项目 AI | run id, hypothesis id, evidence refs |
| 专家与运行 | 管理研究工具、产出和运行准备 | provider readiness, audit, diagnostics |

导航反模式：

- 不要将 `Agent`、`Workflow`、`Model`、`Tool`、`Prompt`、`MCP`、`Memory`、`Vector DB` 作为普通用户导航暴露。
- 不要让用户在开始任务前就理解代理图。
- 不要把同一任务分散到多个竞争面板。

### 项目 AI 与语言路由

项目 AI 是自然语言命令面，不是关键字命令面。用户可以说“帮我联网查一下世界杯目前如何了”“抓取这些网页并整理”“这个项目现在能做什么”，系统应通过 LLM 语义路由判断意图、输入缺口和风险边界。

推荐交互链路：

```text
自然语言请求
-> LLM 语义路由
-> 确认卡
-> 用户授权
-> 工具执行
-> 模型整理结果
-> 证据边界与下一步
```

规则：

- 前端不应维护大量业务关键字表作为主要意图路由。关键字只能作为低风险快捷入口、兜底或本地提示，不能成为工具选择的唯一依据。
- 写入型或外部访问型动作必须通过确认卡，包括 PDF 解析、网页抓取、公开 Web Search、外部文献 MCP、terminal/SSH 等。
- 确认卡面向用户说明“会做什么、访问什么、风险是什么、会产出什么”，而不是展示 raw tool schema。
- Web Search 只返回 URL、标题和 snippet 线索；如果用户需要“聚合网站里的内容”，必须继续通过 `browser.web_extract` 授权抓取网页正文，再由模型基于正文整理回答。
- 工具执行后的默认回答应是模型整理过的用户答案，并附带证据边界；raw JSON、result_ref、内部路径和 provider 细节隐藏到审计入口。
- 这套交互可以在视觉和行为上接近 Codex/Hermes：左侧项目树与工作队列、右侧对话命令面、人类确认、工具执行、结果回填。

## 4. 布局框架

默认桌面外壳：

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

可选辅助界面：

```text
Drawer: references, detailed source evidence, contextual inspection
Disclosure: process log, ranking basis, quality signals
Expert Settings: provider/model/Think mode/literature/reference-count options
Modal: short blocking decision only
Toast: short system feedback only
```

资料管理页规则：

- 资料管理是资产控制面，应使用表格、筛选、状态标签和详情抽屉，不要默认暴露 raw citation map。
- 单篇论文解读属于资料管理页的任务表单，输入为 `PDF_PATH` 和 `OUTPUT_NAME`，必须有 loading、disabled、success、error 状态。
- 解读结果面向用户展示生成文件、媒介截图数量、Markdown 图片链接校验、DOI、BibTeX 来源和 plain text 来源边界，不展示 raw parser trace。

布局规则：

- 第一屏必须回答：我在哪、当前任务是什么、下一步操作是什么。
- 主要工作区域应为全宽任务区域，而不是嵌套展示卡片的堆栈。
- 避免卡片内卡片。卡片用于假设、论文、任务或实验等重复对象。
- 长详情应移入抽屉、详情选项卡或 disclosure。
- 右侧面板和抽屉应具有上下文意义，而不是始终存在的噪音。

响应式行为：

```text
>= 1280px: nav rail + main work surface, optional drawer
960px - 1279px: compact nav + main, drawer overlays
640px - 959px: single-column task flow
< 640px: reading and light operations only; hide dense diagnostics behind drawers
```

## 5. 信息隐藏

每个控件、窗口、抽屉、详情面板、模态框、弹出框、Toast 和报告面都必须遵循渐进披露。

默认状态仅显示：

```text
Title
Short summary
Current status
Primary action
One obvious next step
```

用户意图前隐藏：

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
Long explanations
Raw JSON
```

必需的入口示例：

| 隐藏信息 | 用户意图入口 |
| --- | --- |
| 假设参考文献 | `参考文献` 按钮在假设卡上 |
| 候选假设中文翻译 | 选中假设行动面板中的 `翻译中文` |
| 过程 trace | `查看过程与证据` disclosure |
| 排序/锦标赛 | `排序依据` 选项卡在 disclosure 后 |
| 质量指标 | `质量信号` 选项卡在 disclosure 后 |
| 提供者/模型/Think mode 控制 | `专家设置` |
| 参考文献数量范围 | `专家设置`，并在参考文献抽屉中反馈 |
| 错误恢复 | 本地任务级反馈，而不是全局调试转储 |

信息隐藏不是删除。审计字段保留在数据结构中，并可在 UI 面上发现。

## 6. 设计令牌

规范运行时令牌位于 `src/styles.css`。新组件必须使用这些令牌族。

### 间距

使用当前 8px 网格：

```css
--space-xs: 8px;
--space-sm: 16px;
--space-md: 24px;
--space-lg: 32px;
--space-xl: 48px;
```

规则：

- 内部微间距：仅在紧密文本关系时使用 `4px`。
- 控件和卡片间距：`--space-xs` 或 `--space-sm`。
- 区块间距：`--space-md` 或 `--space-lg`。
- 大页面节奏：`--space-xl`。
- 不要创建随机 `margin: 13px`、`padding: 18px` 或视口缩放字体间距。

### 网格

```css
--grid-columns-mobile: 4;
--grid-columns-tablet: 8;
--grid-columns-desktop: 12;
--grid-gutter: var(--space-sm);
--grid-margin: var(--space-md);
--layout-max-width: 1584px;
```

规则：

- 使用网格轨道和 minmax 约束来布局面板、列表和重复卡片。
- 状态变化不得改变网格轨道尺寸。
- 悬停和激活状态可以改变颜色、边框、阴影或小变换，但不得导致布局偏移。

### 圆角

```css
--radius-control: 8px;
--radius-panel: 8px;
```

规则：

- 控件和面板使用 8px 圆角。
- 除非组件需要胶囊形状，否则避免过大的圆角矩形。
- 图标按钮应使用相同的控件圆角，除非存在已建立的本地变体。

### 控件高度

```css
--control-height-sm: 40px;
--control-height-md: 48px;
```

规则：

- 桌面控件目标：至少 40px。
- 移动/触控目标：在可行时至少 44px。
- 加载状态必须保持相同高度。
- 禁用状态必须保持相同尺寸。

## 7. 颜色系统

使用语义颜色令牌。组件代码中不要将颜色命名或推理为装饰性的蓝色/灰色/绿色变体。

当前令牌族：

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

用法：

| 令牌角色 | 用途 |
| --- | --- |
| Primary | 主要操作、选中导航、聚焦交互 |
| Surface | 面板、抽屉、表单控件 |
| Surface muted | 细微区域背景、非活动面 |
| Text primary | 标题和重要内容 |
| Text secondary/muted | 描述、元数据、辅助文本 |
| Border default | 正常分隔 |
| Border strong | 控件边框和激活分割线 |
| Success | 完成状态 |
| Warning | 可恢复的注意状态 |
| Danger | 破坏性或不可逆操作 |
| Focus ring | 键盘聚焦轮廓 |

规则：
- 页面不应被无关强调色主导。
- 红色保留用于破坏性或严重错误语义。
- 警告应说明限制和恢复，而不是单纯装饰。
- 焦点轮廓必须可见并满足对比要求。
- 正文应针对 WCAG AA 对比：正常文本至少 4.5:1。

## 8. 排版

当前字体栈：

```css
"Geist", Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
```

本项目推荐字号：

```text
Display: 32px, tight line-height, project or empty-state hero only
H1: 28px - 32px, page/project title
H2: 20px - 24px, current task or major section
H3: 15px - 18px, card/detail title
Body: 13px - 15px, regular content
Caption: 12px - 13px, metadata and helper text
Small: 11px - 12px, dense tags and metric chips
```

规则：

- 不要使用视口缩放字体大小。
- 字母间距保持 `0`，除非小写大写标签需要显式处理。
- 紧凑面板、卡片、侧边栏和工具栏使用比页面标题更小的字号。
- 按钮和控件文本必须明确设置大小，绝不使用浏览器默认。
- 按钮/卡片中的长文本必须自动换行或截断，而不破坏布局。

## 9. 组件契约

### 按钮

变体：

```text
Primary: one page-level main action
Secondary: ordinary task action
Ghost: low-priority action
Danger: destructive action
Icon Button: compact tool action
```

规则：

- 按钮文字使用动词：`生成候选假设`、`上传论文`、`导出报告`、`运行实验`。
- 避免模糊标签如 `执行`、`提交`、`处理`、`打开`。
- 必须实现默认、悬停、激活、禁用、加载和 focus-visible 状态。
- 加载状态必须使用稳定的图标/文本槽位，并在适当时使用 `aria-busy`。
- 按钮尺寸不得在状态间变化。

### 输入、文本区域、选择框

规则：

- 必须始终配对可见标签。
- 助手文本应解释任务影响，而不是后端字段名。
- 高级字段应放在 `专家设置` 后面。
- 不要在主要路径中暴露 `temperature`、`top_p`、`retriever`、`chunk size`、`agent count` 或 API 密钥状态。
- 错误文本必须保持在字段附近，并解释恢复方式。

### 开关和滑块

规则：

- 开关控制二元模式，并具有立即可见状态。
- 滑块控制有界数值，并显示当前值。
- 两者在更改时必须保持布局稳定。
- 禁用状态必须可见且可读。

### 选项卡

仅在同一对象内部的同级视图中使用选项卡：

```text
概览
过程
假设
证据
排序依据
质量信号
```

规则：

- 不要在同一视口中嵌套多个选项卡系统。
- 昂贵或专家专用选项卡应放在 disclosure 后。
- 激活选项卡必须通过颜色、背景和 `aria-selected` 清晰区分。

### 卡片

卡片用于重复对象：

```text
Hypothesis
Paper
Experiment
Report
Task
Template
```

假设卡默认内容：

```text
Rank/order
User-facing title
Short summary
Score/ranking signal
Primary local action
Reference drawer trigger
```

规则：

- 卡片默认不应显示完整参考、完整评审、原始指标或 trace。
- 卡片操作应明确：`参考文献`、`设计实验`、`写入报告`。
- 卡片可以是可选的，但避免按钮内嵌按钮的标记。

### 抽屉

将抽屉用于上下文深度信息：

```text
Reference evidence
Object metadata
Related papers
Review details
AI suggestions
```

规则：

- 抽屉仅从明确的用户意图打开。
- 抽屉应具有标题、关闭按钮、`role="dialog"`、`aria-modal` 和 Escape 关闭。
- 抽屉内容属于一个选定对象。
- 抽屉不能成为全局调试控制台。

### 模态框

仅将模态框用于阻断性决策：

```text
Confirm destructive action
Resolve permission issue
Choose export target
```

当抽屉更合适时，不要使用模态框来进行普通参考检查。

### Toast

将 toast 用于短反馈：

```text
Saved
Copied
Export started
Upload failed
```

不要把长解释或原始错误放在 toast 中。

### 表格和列表

表格用于比较。列表/卡片用于对象浏览。

表格列规则：

```text
Name: what is this
Status: current state
Owner/source: who or where
Updated: recency
Action: next action
```

规则：

- 长文本应打开详情、抽屉或侧面板。
- 低频列应放在列设置后。
- 当数据量需要时，表格应支持搜索/筛选/排序。

## 10. 状态设计

每个页面和主要组件必须设计：

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

状态措辞必须以任务为导向：

```text
正在解析论文...
已生成 3 个候选假设
当前假设暂无可解析参考文献
文献服务暂不可用，可先按非文献支撑流程继续
```

避免：

```text
No data
Error occurred
Failed
Invalid input
Provider missing
```

规则：

- 加载状态保持尺寸稳定。
- 错误状态提供恢复方式。
- 空状态提供下一步行动。
- 部分错误保留可用的中间结果。
- 权限被拒绝时告知用户下一步去哪里。
- Streaming/Running 状态显示当前阶段，但默认隐藏原始 trace。

## 11. AI 结果契约

AI 输出只有在可控、可检查、可追踪和可重用时才算完整。

假设结果应展示：

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

默认视图应显示：

```text
Title
Summary
Score / ranking signal
Reference drawer trigger
Experiment/report next actions
```

用户意图后隐藏：

```text
Full technical text
Citation map
Review rubric
Tournament/ranking details
Agent process
Metrics
Raw trace
```

演示/实时/文献边界：

- 演示模拟：仅验证 UI、工作流、架构和交互。
- 实时模型工作流：模型驱动的生成、评审、排序和演化。
- 文献支撑工作流：带有引用来源证明的基于来源的声明。

绝不要将演示输出呈现为真实科学证据。

## 12. 页面模板

### 项目页面

目的：

```text
Define research goal and move into candidate hypothesis generation.
```

必需：

- 项目 H1 和研究目标摘要。
- 当前任务 H2。
- 研究目标输入。
- 一个主要操作。
- 建议的起始任务。
- 折叠的专家设置。
- 运行后的候选结果。
- 折叠的过程/证据详情。

项目详情 / 概览补充：

- 概览默认聚焦候选假设、当前选择、证据边界和下一步操作。
- 不默认铺设“当前阶段”和“最近产出”两张静态卡；这些信息已经由项目子导航、工作区、报告页和候选假设详情承载。
- 阶段状态只在运行中、错误恢复、或用户主动查看过程时出现；最近产出进入 `报告` / `研究产出` 页面或对象列表。
- 如果后续恢复阶段/产出摘要，必须能说明它推动当前项目下一步，而不是重复侧栏、header 或子工作区已有信息。

### 文献页面

目的：

```text
Inspect evidence readiness, source coverage, and citation gaps.
```

必需：

- 清晰的证据状态。
- 文献可用性状态。
- 生成或检查假设的下一步行动。
- 默认不要显示原始 MCP 诊断。

### 假设页面

目的：

```text
Compare candidate directions and inspect one hypothesis at a time.
```

必需：

- 假设卡片。
- 每张卡片上的 `参考文献` 触发器。
- 实验/报告下一步行动。
- 详情放在 disclosure 后。

### 实验页面

目的：

```text
Convert one selected hypothesis into falsifiable validation.
```

必需：

- 选中假设的标题和摘要。
- 用户可读的实验计划。
- 可证伪标准。
- 评估输出。
- 链接回假设并前往报告。

### 报告页面

目的：

```text
Organize findings, experiment plan, and limitations into a draft.
```

必需：

- 研究发现。
- 实验计划。
- 限制说明。
- 演示/实时/文献边界说明。
- 不要显示原始后端文本。

## 13. 内容密度

专业研究产品可以密集，但密度必须有层次。

推荐密度：

```text
Project overview: low to medium density
Hypothesis comparison: medium density
Evidence drawer: medium-high density
Experiment analysis: high density
Report drafting: medium density
Expert settings: high density but collapsed
```

规则：

- 密集信息应放在对象详情、抽屉、表格或专家面板。
- 默认页面不应变成调试仪表盘。
- 不要过度使用装饰性卡片来弥补信息架构薄弱。

## 14. 文案

界面文案应听起来像产品工作流，而不是数据库字段。

好的中文标签：

```text
生成候选假设
参考文献
查看过程与证据
生成实验设计
写入报告草稿
当前假设暂无可解析参考文献
文献服务暂不可用，可先按非文献支撑流程继续
```
