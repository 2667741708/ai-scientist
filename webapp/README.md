# Open Coscientist Studio

React + FastAPI web app for trying the `open-coscientist` workflow from a browser.

## What It Provides

- Research goal input
- Model selection for Gemini, OpenAI, Anthropic, DeepSeek, and Qwen/DashScope
- Demo mode for instant no-key exploration
- Optional live `open_coscientist.HypothesisGenerator` execution
- Workflow stage visualization
- Live timeline polling
- Ranked hypothesis inspector
- Details tabs for overview, evidence, tournament, and metrics
- Project-backed workbench snapshot with real papers, run state, and evidence boundary
- Persistent project artifacts for hypotheses, evidence links, and experiment plans
- Server-sent run events with structured recovery guidance for timeout, transport, and output-format failures
- Working navigation views:
  - Runs: configure and execute a workflow
  - Library: load goal templates and reopen recent completed runs
  - Settings: refresh provider health, switch local/live mode, clear current run

## Start The App

Use PowerShell with UTF-8 enabled:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
cd "D:\文件\揭榜挂帅\Google Co-Scientist\open-coscientist\webapp"

npm install
pip install -r backend\requirements.txt
```

Terminal 1:

```powershell
npm run api
```

Terminal 2:

```powershell
npm run dev
```

Or start both services with UTF-8 output and log files:

```powershell
.\scripts\start-studio.ps1
```

Open:

```text
http://127.0.0.1:8001
```

For a separately hosted frontend, configure the FastAPI bridge before starting it:

```powershell
$env:COSCIENTIST_ALLOWED_ORIGINS="https://your-frontend.example"
$env:COSCIENTIST_REQUIRE_AUTH="1"
```

`COSCIENTIST_ALLOWED_ORIGINS` is a comma-separated allowlist appended to the local development origins. `COSCIENTIST_REQUIRE_AUTH=1` protects API routes except registration, login, recovery, and health; production deployments must still scope run/project data to the authenticated account before exposing terminal or SSH workflows.

The main product path is backed by the FastAPI bridge rather than browser-only mock state:

- `GET /api/workbench/snapshot` returns the current run, real knowledge-base papers, project summary, artifact list, and evidence boundary.
- `GET /api/runs/{run_id}/events` streams run updates for the active workspace.
- `POST /api/projects/{project_id}/artifacts` persists a selected hypothesis or evidence link.
- `POST /api/projects/{project_id}/experiment-plans` creates and persists a structured falsifiable experiment plan.
- `GET /api/runs/{run_id}/recovery` exposes actionable recovery information when a run is incomplete or fails.

Demo mode remains a synthetic workflow for UI and interaction validation. Live mode is the path that can produce model- and literature-backed research artifacts, but its evidence quality still depends on provider readiness, literature MCP availability, and the returned source metadata.

## Local Agent Simulation

Local agent simulation is enabled by default. It behaves like a fake API-key provider named `codex-simulation`: no external LLM account is required, but the backend still returns a multi-agent-shaped run with `agent_trace`, synthetic reviews, tournament matchups, metrics, and ranked hypotheses.

This mode is intended for product walkthroughs and frontend QA. Synthetic records are marked as synthetic in the API contract and should not be treated as scientific evidence.

## Live Model Mode

To run the actual `open-coscientist` backend, disable Local agent simulation in the UI and set a provider key before starting `npm run api`.

Examples:

```powershell
$env:GEMINI_API_KEY="your-key"
```

or:

```powershell
$env:OPENAI_API_KEY="your-key"
```

or:

```powershell
$env:ANTHROPIC_API_KEY="your-key"
```

or:

```powershell
$env:DEEPSEEK_API_KEY="your-key"
```

or for Qwen through DashScope:

```powershell
$env:DASHSCOPE_API_KEY="your-key"
```

`QWEN_API_KEY` is also accepted by the FastAPI bridge and normalized to `DASHSCOPE_API_KEY` before the LiteLLM-backed workflow runs.

or for MiMo through its OpenAI-compatible endpoint:

```powershell
$env:MIMO_API_KEY="your-key"
```

MiMo models are exposed in the UI as `openai/mimo-v2.5-pro`, `openai/mimo-v2.5`, `openai/mimo-v2-pro`, and `openai/mimo-v2-flash`. The backend keeps MiMo on `MIMO_API_BASE` or the default `https://api.xiaomimimo.com/v1`; it does not reuse `OPENAI_API_KEY`.

The research chat entrypoint also uses the backend model channel for general project questions. It retrieves local knowledge-base snippets, builds the workbench prompt server-side, and then calls the selected model. By default it uses the model selected in the UI; override only this chat path with:

```powershell
$env:COSCIENTIST_RESEARCH_CHAT_MODEL="openai/mimo-v2.5"
```

Set `COSCIENTIST_RESEARCH_CHAT_LLM_ENABLED=0` to force research chat back to deterministic task routing only. Tool actions, external web search, PDF parsing, SSH, terminal commands, and live research workflow starts still require confirmation cards before execution.

The backend calls:

```python
open_coscientist.HypothesisGenerator(...)
```

and returns hypotheses, research plan, tournament matchups, and metrics to the frontend.

## Literature Review

The Literature review toggle maps to `enable_literature_review_node`. It requires a literature MCP endpoint. By default the Studio probes the local endpoint and auto-starts the bundled MCP server when it is not already listening.

The default MCP endpoint is:

```text
http://localhost:8888/mcp
```

The bundled server is defined at `mcp_server/server.py`, and the tool registry that maps workflow tool IDs to MCP tool names is `src/open_coscientist/config/tools.yaml`. The default tools include arXiv search, PubMed/PMC search, best-effort Google Scholar HTML search, public URL/PDF reading, PDF link discovery, and controlled source-artifact downloads.

Auto-start can be disabled or overridden:

```powershell
$env:COSCIENTIST_MCP_AUTOSTART="0"
$env:MCP_SERVER_URL="http://localhost:8888/mcp"
```

Reference manual server command for debugging:

```powershell
cd "D:\文件\揭榜挂帅\Google Co-Scientist\open-coscientist"
python -m uvicorn mcp_server.server:app --host 127.0.0.1 --port 8888
```

arXiv, public URL/PDF reading, and source downloads need network access but no model provider key. PubMed/PMC tools use NCBI Entrez and should be configured with `ENTREZ_EMAIL`; `ENTREZ_API_KEY` is optional for higher rate limits. Google Scholar is best-effort public HTML and may return no results when blocked by CAPTCHA, login walls, paywalls, or rate limits.

## PDF Reading And Translation

The Data page provides an in-page PDF reader for discovered candidates that expose a direct PDF URL. Use `阅读 PDF` to open a bottom sheet over the current search results, keep the Data page state, and return to the candidate list without navigation. The reader also keeps `新窗口打开` and `解析到当前库` fallbacks.

PDF responsibilities are intentionally separated:

- Browser PDF reader: quick human inspection in the current page.
- Existing PyMuPDF parser: evidence extraction, metadata, chunks, media assets, and knowledge-base provenance.
- Optional BabelDOC integration: layout-preserving translated or bilingual PDF generation as a future background workflow.

BabelDOC's README describes it as a PDF scientific paper translation and bilingual comparison library. It recommends installing the CLI with:

```powershell
uv tool install --python 3.12 BabelDOC
babeldoc --help
```

The documented CLI pattern is:

```powershell
babeldoc --openai --openai-model "gpt-4o-mini" --openai-base-url "https://api.openai.com/v1" --openai-api-key "your-api-key-here" --files example.pdf
```

For this workbench, BabelDOC should be wired as an approval-backed/background translation job that writes translated PDF artifacts and metadata, not as a replacement for the evidence parser. Its own README warns that direct Python APIs should be treated as internal, so a CLI/job adapter is the safer integration boundary.

## RAGFlow-Style Knowledge Base

The local knowledge base now includes a RAGFlow-style adapter for section-preserving chunking, optional embedding indexing, hybrid retrieval, optional reranking, API status/reindex endpoints, and the Data page status/reindex UI.

Detailed Chinese tutorial:

```text
webapp/docs/ragflow-knowledge-tutorial.zh-CN.md
```

## Citation And BibTeX Retrieval

The Studio can export candidate citation metadata JSON for manual checking, but it does not synthesize BibTeX from title, author, abstract, or arXiv metadata.

Trusted BibTeX is downloaded only when an external citation service returns it directly:

- DOI content negotiation: `https://doi.org/{doi}` with `Accept: application/x-bibtex`
- Crossref transform fallback: `https://api.crossref.org/works/{doi}/transform/application/x-bibtex`
- DataCite content negotiation fallback: `https://data.datacite.org/application/x-bibtex/{doi}`
- Publisher or journal landing pages opened by the researcher through the paper page or institutional access path

If a candidate has no DOI or the trusted services do not return BibTeX, the UI shows a limited state and asks the researcher to open the paper page, DOI page, or institutional access page to download the official citation file. PubMed/NCBI citation manager exports are useful for PubMed workflows, but they are not treated as direct BibTeX unless converted by a trusted citation tool outside this UI path.

## Troubleshooting Fixes

- **API offline**: run `npm run api` or `.\scripts\start-studio.ps1`; the UI shows the backend startup command and working directory when health is available.
- **Run button spins forever**: backend runs are guarded by `COSCIENTIST_RUN_TIMEOUT_SECONDS` (default `900`), and the frontend stops polling when a run reaches `complete` or `error`.
- **Provider missing**: live mode validates the selected model's required environment variable before creating a run and returns a repair command such as `$env:GEMINI_API_KEY="your-key"`.
- **Configured but unverified**: provider health checks intentionally do not call paid model endpoints. The UI labels this as `configured_not_called`; the key is verified by the first live run.
- **No real literature**: confirm `http://127.0.0.1:8888/` returns `status: running` and `http://127.0.0.1:8787/api/health` reports `literature_mcp.available: true`. If local auto-start is disabled, start the MCP server manually with the command above.
- **Chinese path/PowerShell mojibake**: use `.\scripts\start-studio.ps1` or set `[Console]::OutputEncoding` and `$OutputEncoding` to UTF-8 before starting services.

## Build

```powershell
npm run build
```

The production bundle is emitted to `webapp\dist`.
