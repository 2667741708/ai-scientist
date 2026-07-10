# Local AI Tool Capability Baseline

本文档定义 `open-coscientist/webapp` 作为本地科研 AI workbench 时应具备的工具能力边界。这里的 `Hermes/harness` 指工具运行时模式和能力设计，不表示把外部 runtime 原样搬入本项目。

## 1. Operator Harness 与 Product Agent 的边界

Codex/operator harness 可以拥有 `web search/open`、本机 shell、文件 patch、浏览器控制、图片生成等高权限工具；这些工具服务开发者维护项目。

`open-coscientist/webapp` 的 product agent 不能默认继承 operator 的全部能力。面向真实研究者时，工具必须经过：

- central `ResearchToolRegistry`
- phase policy / toolset 最小授权
- availability check
- approval card
- guardrail
- background job tracking
- `research_tool_calls` 与 `research_tool_results` provenance

尤其是 raw `bash`、PowerShell、任意 `exec`、任意文件写入和远程脚本执行，不得作为普通聊天能力直接开放。

## 2. 本地 AI 必备工具矩阵

| 能力族 | 本地 AI 是否必备 | 本项目状态 | 约束 |
| --- | --- | --- | --- |
| Web search | 必备 | `web.search_public` 已有 best-effort `bing_html` workflow | 返回 URL、snippet、retrieval metadata 和 result ref；search snippet 不是全文证据，后续仍应通过 `browser.web_extract`、PDF parser、MCP 或知识库入库 |
| Web extract | 必备 | `browser.web_extract` 已有 workflow | 只处理 public HTTP(S)，有 SSRF guardrail、快照和知识库入库 |
| Browser screenshot | 常用 | `browser.capture_screenshot` 已有 workflow | 用 Playwright 截图和 console metadata；不等价于完整 CDP 自动浏览器 |
| Literature/MCP | 必备 | `mcp.literature_review`、config-driven MCP tools | MCP 不可达时必须标注 ungrounded/limited |
| PDF/fulltext parsing | 必备 | `pdf.parse_to_knowledge_base` 已有 workflow | 解析产物、chunks、media、metadata、KB evidence chain 必须持久化 |
| Knowledge base / RAG | 必备 | `knowledge_base.rag_search`、`support_for_hypothesis` | 只把摘要和 result ref 进上下文，全文留在 SQLite/artifacts |
| Local file read | 必备 | `file.source_snapshot` 已有 workflow | 只读配置 evidence root 内文本文件，分页、hash、大小限制 |
| Local file write / patch | 必备但高风险 | product agent 暂不开放通用写文件 | 应以 artifact writer、report exporter、template writer 等专用 workflow 落地 |
| Restricted code execution | 必备 | `code.execute_analysis` 已有 workflow | 仅受限 Python，AST guard、timeout、独立 work dir |
| Raw terminal / bash / PowerShell exec | 必备给 operator，高风险 product 能力 | `terminal.command` 已有 permission-gated workflow | 允许在命令权限策略下执行；仍保留危险命令拦截、cwd 策略、timeout、脱敏、stdout/stderr artifact 和 tool result storage |
| Experiment jobs | 必备 | `experiment.background_job` 已有 workflow | 只能运行配置 experiment root 内 Python 脚本 |
| SSH / remote training | 常用 | `ssh.training_command` 已有 workflow | 仅白名单 host，approval、危险命令拦截、后台任务和日志产物 |
| Task board / scheduler | 必备 | `research_tasks`、`research_schedules` 已落地 | schedule tick 只能生成 ready task，不能绕过 approval 自动执行 |
| Delegation / subagents | 常用 | `research_delegations` 已落地 | 子 agent 不能伪造工具调用或实验结果 |
| Session search / memory | 必备 | `GET /api/session-search` 已落地 | 返回摘要和 target ref，不直接铺大型结果 |
| Secrets / credentials | 必备 | 只允许环境变量、本机配置或外部 secret store | 不得写入 AGENTS.md、docs、SQLite tool result 或前端 bundle |
| Observability | 必备 | timeline、trace、tool calls、tool results、background jobs | 所有高风险工具必须可审计、可恢复、可解释失败 |
| Vision/OCR/multimodal | 条件必备 | PDF media + Playwright 截图已有基础 | 扫描 PDF、图表、显微图、结构图需要 OCR/vision parser 或多模态模型 |

## 3. 当前注册表中的关键能力

```text
knowledge_base.rag_search
knowledge_base.support_for_hypothesis
provenance.record_run
pdf.parse_to_knowledge_base
mcp.literature_review
metadata.crossref_lookup
web.search_public                 # best-effort public search workflow
browser.web_extract
browser.capture_screenshot
file.source_snapshot
code.execute_analysis
experiment.background_job
ssh.training_command
terminal.command                  # permission-gated raw command workflow
```

`web.search_public` 和 `terminal.command` 均必须保留能力边界：前者只返回 snippets 和 source URL，不能直接作为全文证据；后者只通过命令权限策略、guardrail、artifact 和 provenance 执行，不能绕过审计。

`research-chat` 对话入口已能把自然语言请求路由为 `web.search_public`、`terminal.command`、`ssh.training_command` 确认卡。确认后必须调用对应 workflow endpoint；三台白名单训练主机优先走 `ssh.training_command`，显式任意 `ssh ...` 命令通过 `terminal.command` 执行并保留审计。

## 4. Raw Exec 原则

本地 AI 可以需要 shell，但产品 agent 不应拥有无边界 shell。允许路径只有三类：

1. Operator 在 Codex/harness 中维护项目时手动运行命令，并遵守 workspace 的 PowerShell UTF-8 约定。
2. `code.execute_analysis` 执行短小、受限、可审计的 Python 分析。
3. `experiment.background_job` 或 `ssh.training_command` 运行审批后的实验/训练任务。

terminal 工具保持 executable 时必须持续保留 denylist、cwd policy、timeout、secret redaction、destructive command blocking、approval/permission mode、stdout/stderr artifact、tool result storage 和 UI recovery state。
