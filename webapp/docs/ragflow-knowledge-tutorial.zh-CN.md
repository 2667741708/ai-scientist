# RAGFlow 知识库嫁接教程

本文说明如何把 `D:\文件\个人知识库\RAGFlow` 的核心 RAG 能力嫁接到本项目 `open-coscientist/webapp`，并给出当前项目可直接使用的知识库教程。

## 嫁接后的能力边界

当前实现不是把 RAGFlow 的 MySQL、MinIO、Redis、Elasticsearch/Infinity、Go server、Python worker、DeepDOC 全服务栈原样塞进本项目，而是把它的核心知识库链路完整适配成 Open Coscientist Studio 内置能力：

```text
PDF/文档解析 -> RAGFlow 风格 chunk -> SQLite FTS5 索引 -> 可选 embedding -> hybrid retrieval -> 可选 reranker -> Agent/Workflow grounding
```

保留的本项目运行边界：

- 文档库仍在 `COSCIENTIST_KNOWLEDGE_BASE_DIR/knowledge.sqlite3`。
- PDF 解析仍优先使用 PyMuPDF，避免引入 DeepDOC 的重型 ONNX/PaddleOCR runtime。
- embedding/reranker 走 OpenAI-compatible HTTP endpoint，可接 4090 上的 vLLM、Xinference、TEI 包装服务或其它 provider。
- 未配置 embedding 时自动降级到 SQLite FTS5，不伪装成向量检索。
- 未配置 reranker 时自动降级到 hybrid score，不伪装成 cross-encoder 重排。

## RAGFlow 原实现链路

我阅读的关键 RAGFlow 实现路径如下。

文档解析与 chunk：

- `rag/app/naive.py`
  - `chunk(...)` 是通用文档入口，支持 PDF、DOCX、TXT、Markdown、HTML、Excel、JSON 等。
  - `parser_config` 包含 `chunk_token_num`、`delimiter`、`layout_recognize`、`overlapped_percent`、`children_delimiter`。
  - PDF 会先选 layout recognizer，再调用 parser，最后用 `naive_merge(...)` 或 `naive_merge_with_images(...)` 合并到 token budget。
- `rag/app/paper.py`
  - 面向论文 PDF 的 parser。摘要单独成 chunk，正文按标题层级推断 section，再用 `tokenize_chunks(...)`。
- `rag/svr/task_executor.py`
  - worker 入口。先 chunk，再 embedding，再写入 doc store。
  - `embedding(...)` 把标题向量和正文向量加权融合，写入 `q_{dimension}_vec` 字段。

OCR / PDF：

- `deepdoc/vision/ocr.py`
  - `OCR` 组合文本检测和文本识别模型，负责扫描件或图片文本。
- `deepdoc/vision/layout_recognizer.py`
  - layout model 给 OCR box 标注 `title`、`text`、`table`、`figure`、`caption`、`header`、`footer` 等布局类型。
- `deepdoc/parser/pdf_parser.py` 与 `rag/app/paper.py`
  - 将 OCR/layout 结果整理为可 chunk 的 sections/tables，并支持 crop 图表区域。

embedding / reranker / provider：

- `api/db/services/llm_service.py`
  - `LLMBundle.encode(...)` 是 embedding 统一边界，会处理空文本、截断、token usage。
- `api/apps/services/dataset_api_service.py`
  - dataset 检索时绑定 embedding model；如果请求提供 `rerank_id`，再绑定 rerank model。
- `internal/entity/models/*.go`
  - Go 侧实现了 OpenAI、Zhipu、Voyage、Xinference、NVIDIA 等 embedding/rerank provider。

知识库检索：

- `rag/nlp/search.py`
  - `Dealer.get_vector(...)` 将 query 编码为 `MatchDenseExpr(q_{dim}_vec, cosine)`。
  - `Dealer.search(...)` 组合全文检索 `MatchTextExpr`、向量检索 `MatchDenseExpr` 和 `FusionExpr`。
  - `Dealer.retrieval(...)` 先取候选窗口，再按 term similarity、vector similarity、rank feature 和可选 reranker 得分排序。
- `internal/engine/elasticsearch/chunk.go`、`internal/engine/infinity/chunk.go`
  - ES/Infinity 后端负责真实向量列、KNN/HNSW 和全文检索。

API / 前端 / Docker：

- `api/apps/services/dataset_api_service.py` 和 `internal/handler/dataset.go`
  - dataset、document、retrieval、embedding check、run embedding 等 API。
- `web/src/services/knowledge-service.ts`
  - 前端 knowledge/dataset API client。
- `web/src/pages/dataset/*`
  - 文件列表、配置、检索测试、知识图谱等页面。
- `docker/docker-compose.yml`、`docker/docker-compose-base.yml`
  - RAGFlow 默认依赖 MySQL、MinIO、Redis、ES/Infinity/OpenSearch，可选 DeepDOC、TEI、GPU profile。

## 本项目的嫁接实现

新增：

- `webapp/backend/ragflow_adapter.py`
  - `ragflow_merge_paragraphs(...)`：RAGFlow 风格 delimiter + token budget + overlap chunk 合并。
  - `RagflowEmbeddingClient`：OpenAI-compatible embedding client；也支持 `hash` 本地模式用于离线验证。
  - `RagflowRerankClient`：OpenAI-compatible rerank client。
  - `cosine_similarity(...)` / `normalize_cosine(...)`：SQLite JSON 向量检索的轻量实现。

修改：

- `webapp/backend/knowledge_base.py`
  - `hierarchical_chunk_paper(...)` 改为 section-preserving + RAGFlow token budget chunk。
  - 新增表 `paper_chunk_embeddings`。
  - `index_embeddings_for_paper(...)`：入库后为每个 chunk 建 embedding。
  - `reindex_embeddings(...)`：重建当前库或指定论文的向量索引。
  - `rag_search(...)`：合并 SQLite FTS5 候选、vector 候选、可选 reranker，返回 `term_similarity`、`vector_similarity`、`rerank_score`、`retrieval_method`。
  - `ragflow_status(...)`：返回 chunking、embedding、reranker、retrieval 当前状态。
- `webapp/backend/app.py`
  - `GET /api/knowledge/ragflow/status`
  - `POST /api/knowledge/ragflow/reindex`
  - `GET /api/knowledge/rag/search` 返回 `ragflow` 状态。
  - PDF parse run 新增 `ragflow_embedding_indexed` 检查项。
  - `/api/health` 返回 `ragflow_knowledge`。
- `webapp/src/pages/data/DataPage.tsx`
  - 资料页显示当前 RAGFlow 适配模式、embedding 覆盖、reranker 状态。
  - 支持“重建向量索引”。
  - 检索结果显示 retrieval method、vector score、rerank score。
- `webapp/docker-compose.ragflow-knowledge.yml`
  - 提供 FastAPI bridge + Vite 前端的知识库部署配置。

## 环境变量

最小可用，本地 hash embedding：

```powershell
$env:COSCIENTIST_RAG_EMBEDDING_PROVIDER="hash"
$env:COSCIENTIST_RAG_EMBEDDING_MODEL="hash-local"
```

接真实 embedding 服务：

```powershell
$env:COSCIENTIST_RAG_EMBEDDING_PROVIDER="openai-compatible"
$env:COSCIENTIST_RAG_EMBEDDING_MODEL="BAAI/bge-m3"
$env:COSCIENTIST_RAG_EMBEDDING_BASE_URL="http://127.0.0.1:9997/v1"
$env:COSCIENTIST_RAG_EMBEDDING_API_KEY="optional-key"
```

接真实 reranker 服务：

```powershell
$env:COSCIENTIST_RAG_RERANK_PROVIDER="openai-compatible"
$env:COSCIENTIST_RAG_RERANK_MODEL="BAAI/bge-reranker-v2-m3"
$env:COSCIENTIST_RAG_RERANK_BASE_URL="http://127.0.0.1:9998/v1"
$env:COSCIENTIST_RAG_RERANK_API_KEY="optional-key"
```

检索权重和 chunk 策略：

```powershell
$env:COSCIENTIST_RAG_CHUNK_TOKEN_NUM="512"
$env:COSCIENTIST_RAG_CHUNK_DELIMITER="`n!?。；！？"
$env:COSCIENTIST_RAG_CHUNK_OVERLAP_PERCENT="0"
$env:COSCIENTIST_RAG_VECTOR_WEIGHT="0.3"
$env:COSCIENTIST_RAG_SIMILARITY_THRESHOLD="0.05"
$env:COSCIENTIST_RAG_CANDIDATE_MULTIPLIER="8"
```

## 本地使用教程

启动后端和前端：

```powershell
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
cd "D:\文件\揭榜挂帅\Google Co-Scientist\open-coscientist\webapp"
npm install
pip install -r backend\requirements.txt
$env:COSCIENTIST_RAG_EMBEDDING_PROVIDER="hash"
$env:COSCIENTIST_RAG_EMBEDDING_MODEL="hash-local"
npm run api
```

另开一个 PowerShell：

```powershell
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
cd "D:\文件\揭榜挂帅\Google Co-Scientist\open-coscientist\webapp"
npm run dev
```

打开：

```text
http://127.0.0.1:8001
```

使用步骤：

1. 进入“资料/文献库”页面。
2. 选择或创建文献库。
3. 上传 PDF，或输入后端可访问的 PDF 路径。
4. 点击“解析并写入知识库”。
5. 在解析 checklist 中确认：
   - `全文文本已抽取`
   - `层级片段已生成`
   - `RAG 索引入库`
   - `RAGFlow 向量索引`
6. 在“知识库证据检索”输入研究假设或术语。
7. 结果卡片会显示全文/向量/重排命中情况。
8. 如果切换 embedding model，点击“重建向量索引”。

API 验证：

```powershell
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
Invoke-RestMethod http://127.0.0.1:8787/api/knowledge/ragflow/status
```

重建索引：

```powershell
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8787/api/knowledge/ragflow/reindex `
  -ContentType "application/json" `
  -Body '{"library_id":"library_default"}'
```

检索：

```powershell
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
Invoke-RestMethod "http://127.0.0.1:8787/api/knowledge/rag/search?q=baseline%20accuracy%20experiment&limit=5"
```

## Docker 部署

本地或服务器运行：

```powershell
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
cd "D:\文件\揭榜挂帅\Google Co-Scientist\open-coscientist\webapp"
docker compose -f docker-compose.ragflow-knowledge.yml up -d
```

默认端口：

- 前端：`8001`
- FastAPI：`8787`

如果在 4090 服务器上运行，并希望浏览器从你的工作站访问，需要把 `VITE_API_BASE` 设置成服务器地址：

```bash
export VITE_API_BASE="http://<4090服务器IP>:8787"
export COSCIENTIST_RAG_EMBEDDING_PROVIDER="openai-compatible"
export COSCIENTIST_RAG_EMBEDDING_MODEL="BAAI/bge-m3"
export COSCIENTIST_RAG_EMBEDDING_BASE_URL="http://127.0.0.1:9997/v1"
docker compose -f docker-compose.ragflow-knowledge.yml up -d
```

## Agent / Workflow 使用方式

知识库能力已经进入现有研究 workflow：

- `knowledge_base.support_for_hypothesis(...)` 会通过 `search_chunks(...)` 调用 RAGFlow-style retrieval。
- `record_research_run(...)` 会持久化 hypothesis 到 chunk/evidence 的链接。
- 前端假设详情、Reference drawer、项目 AI 都能读取 `knowledge_base_support`。
- 如果 `memory_scope="library"`，运行时 memory context 会检索当前文献库 evidence。

建议主路径：

```text
上传/解析 PDF -> 重建向量索引 -> 运行假设生成 -> 检查 knowledge_base_support -> 询问项目 AI 解释证据 -> 生成可证伪实验
```

注意：

- demo mode 仍是 synthetic，只能验证 UI 和流程。
- 没有 embedding 时，系统会明确显示 `sqlite_fts`。
- 没有 reranker 时，不会显示 `rerank_score`。
- 真实科学证据必须来自解析后的 fulltext、PDF、网页或 MCP 文献服务，不应把模型 latent knowledge 当成证据。
