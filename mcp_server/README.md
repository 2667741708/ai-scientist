# Open Coscientist MCP Server

MCP (Model Context Protocol) server providing real literature search tools for Open Coscientist hypothesis generation.

## Features

Provides biomedical, preprint, broad academic search, and public content-reading tools:

- **check_pubmed_available**: Test if PubMed service is accessible
- **pubmed_search_with_fulltext**: Search PubMed, download fulltext from PMC, and extract clean text for LLM analysis
- **search_arxiv**: Search public arXiv Atom API with an arxiv.org HTML fallback for AI/ML, CS, math, physics, and preprint-heavy domains
- **search_google_scholar**: Best-effort public Google Scholar HTML search returning titles, snippets, citation counts, landing pages, and visible PDF links
- **read_pdf**: Fetch and extract text from public PDF URLs
- **read_url**: Fetch readable public HTML content and route PDF URLs to `read_pdf`
- **find_pdf_links**: Discover public PDF links from article landing pages
- **generate_queries_hypotheses**: Deterministic local query generation for literature workflows before an LLM query-generation call succeeds
- **download_arxiv_source**: Download and safely extract arXiv e-print/LaTeX source bundles
- **download_github_repository**: Download and safely extract public GitHub repository archives
- **find_github_repository_links**: Discover GitHub repository links from article, arXiv, OpenReview, or project pages
- **read_downloaded_source_file**: Read text-like files from the controlled MCP source cache for LaTeX/code analysis

Google Scholar does not provide an official unauthenticated public API. This server uses public HTML on a best-effort basis and does not bypass CAPTCHA, login walls, paywalls, or rate limits. For production-scale Scholar coverage, wire a licensed Scholar proxy/search API behind the same MCP tool contract.

## Quick Start (Docker)

**Prerequisites:**
- Docker and Docker Compose installed
- NCBI Entrez email (free, required for PubMed API), Entres API key recommended (free)

**Setup:**

```bash
# 1. copy environment template
cp .env.example .env

# 2. edit .env and add required keys:
    ENTREZ_EMAIL=your_email@example.com

# 3. start server from parent dir
cd ..        # to open-coscientist root folder
docker compose up -d

# 4. verify server is running
curl http://localhost:8888
```

MCP endpoints will be available at `http://localhost:8888/mcp`

On Windows/PowerShell, use UTF-8 before launching or probing the service:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false);
python -m uvicorn mcp_server.server:app --host 127.0.0.1 --port 8888
```

## Alternative: Local Development Setup

**Prerequisites:**
- Python >=3.12
- Pip or UV package manager

```bash
# 1. create virtual environment (Python 3.12+)
python3.12 -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# 2. install dependencies
pip install -e .

# 3. configure environment
cp .env.example .env
# edit .env and add ENTREZ_EMAIL and API keys

# Root dir, to find mcp_server package
cd ..

# 4. run server
uvicorn mcp_server.server:app --host 0.0.0.0 --port 8888

# or with auto-reload for development:
uvicorn mcp_server.server:app --host 0.0.0.0 --port 8888 --reload
```

## Configuration

### Required Environment Variables

```bash
# required for PubMed access
ENTREZ_EMAIL=your_email@example.com
# higher rate limits (optional)
ENTREZ_API_KEY=your_ncbi_api_key  # get at https://www.ncbi.nlm.nih.gov/account/
# then https://account.ncbi.nlm.nih.gov/settings/ -> API Key Management
```

### Optional Environment Variables

```bash
# server port (default: 8888)
COSCIENTIST_MCP_PORT=8888

# paper cache directory (default: ./paper_cache)
COSCIENTIST_LIT_REVIEW_DIR=./paper_cache
```

## Usage with Open Coscientist

The webapp FastAPI bridge auto-starts this bundled local MCP server by default when `MCP_SERVER_URL` points to `http://localhost:8888/mcp` or `http://127.0.0.1:8888/mcp`. Set `COSCIENTIST_MCP_AUTOSTART=0` to disable that behavior.

When using the Python library without the webapp bridge, start this MCP server yourself or point the client at an already-running remote endpoint.

Configure the MCP URL (optional, defaults to `http://localhost:8888/mcp`):

```bash
export MCP_SERVER_URL="http://localhost:8888/mcp"
```

The library will:
1. Check if MCP server is available
2. Use configured PubMed/PMC, arXiv, and Google Scholar search sources for literature review
3. Extract public PDF/HTML content and analyze it with LLM agents
4. Generate and validate hypotheses based on literature

The default `src/open_coscientist/config/tools.yaml` literature workflow is multi-source:

- `pubmed_fulltext`: biomedical and PMC fulltext
- `arxiv_search`: open preprints, with direct PDF URLs
- `google_scholar_search`: broad public academic discovery, with visible PDF link capture

Search failures from one source are returned as warnings or empty results so the literature phase can continue with the remaining sources.

Source artifact downloads are cached under `COSCIENTIST_SOURCE_CACHE_DIR` when set, otherwise under `COSCIENTIST_LIT_REVIEW_DIR` or `./cache/literature_sources`. Archive extraction blocks path traversal and skips symlinks/special files. Use `read_downloaded_source_file` to inspect `.tex`, `.bib`, README, config, and code files returned in the manifest.

## Architecture

```
mcp_server/
├── server.py                    # FastMCP server
├── config.py                    # Configuration
├── text_extraction.py           # PMC HTML to markdown
└── tools/
    └── lit_review/
        ├── academic_search.py              # arXiv, Google Scholar, PDF/HTML readers
        ├── source_artifacts.py             # arXiv source and GitHub repository downloads
        ├── search_pubmed.py                # PubMed metadata and availability
        └── pubmed_search_with_fulltext.py  # PubMed search + PMC fulltext
```

## Docker Details

**Environment:**
- Set required keys via `.env` file or docker compose environment

**Commands:**
```bash
# build image
docker compose build

# start in background
docker compose up -d

# view logs
docker compose logs -f

# stop server
docker compose down

# rebuild after code changes
docker compose up -d --build
```

## Support

For issues or questions:
- GitHub: https://github.com/jataware/open-coscientist
- Documentation: See main [README](../README.md)
