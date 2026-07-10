import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  Clock3,
  Database,
  DownloadCloud,
  ExternalLink,
  Eye,
  FileCheck2,
  FileText,
  Filter,
  Layers3,
  Library,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  UploadCloud,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { EmptyState, SkeletonState } from "../../components/feedback/states";
import { PageHeader } from "../../components/surfaces/PageHeader";
import { useWorkbench } from "../../features/runs/workbench-context";
import {
  createLiteratureLibrary,
  discoverLiteraturePapers,
  fetchRagflowKnowledgeStatus,
  fetchLiteratureCitationBibtex,
  listKnowledgePapers,
  listLiteratureLibraries,
  listPaperParseRuns,
  parseKnowledgePdf,
  reindexRagflowEmbeddings,
  searchRagEvidence,
  translateEvidenceText,
  uploadParseKnowledgePdf,
} from "../../lib/api/workbench";
import { classNames, formatBackendText } from "../../lib/formatters/workbench";
import type {
  KnowledgePaper,
  LiteratureDiscoveryCandidate,
  LiteratureDiscoveryPlanner,
  LiteratureLibrary,
  PaperParseItem,
  PaperParseRun,
  RagEvidenceResult,
  RagflowKnowledgeStatus,
} from "../../types/workbench";
import type { PdfMediaAsset, PdfRegionRiskFlag, PdfRegionRiskLevel } from "../../types/workbench";

type AssetTone = "ok" | "warning" | "neutral" | "error";
type DataAsset = {
  id: string;
  name: string;
  type: "Papers" | "Jobs" | "Provenance";
  status: string;
  tone: AssetTone;
  source: string;
  coverage: string;
  updated: string;
  detail: string;
};

type AssetFilter = DataAsset["type"] | "all";
type ParseInputMode = "upload" | "local_path";

const assetTypeLabels: Record<DataAsset["type"], string> = {
  Papers: "论文",
  Jobs: "解析任务",
  Provenance: "来源",
};

const filters: Array<{ value: AssetFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "Papers", label: assetTypeLabels.Papers },
  { value: "Jobs", label: assetTypeLabels.Jobs },
  { value: "Provenance", label: assetTypeLabels.Provenance },
];

function getFocusableElements(container: HTMLElement) {
  return Array.from(
    container.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((element) => !element.hasAttribute("disabled") && element.tabIndex !== -1);
}

function getInitialFilter(search: string): AssetFilter {
  const params = new URLSearchParams(search);
  const view = params.get("view");
  if (view === "papers") return "Papers";
  if (view === "references") return "Provenance";
  return "all";
}

function statusTone(status: PaperParseRun["status"]): AssetTone {
  if (status === "success") return "ok";
  if (status === "warning") return "warning";
  if (status === "error") return "error";
  return "neutral";
}

function statusLabel(status: PaperParseRun["status"]) {
  const labels: Record<PaperParseRun["status"], string> = {
    pending: "等待",
    running: "解析中",
    success: "已完成",
    warning: "部分完成",
    error: "失败",
  };
  return labels[status];
}

function formatTime(timestamp?: number) {
  if (!timestamp) return "未知";
  return new Date(timestamp * 1000).toLocaleString();
}

function safeFileSegment(value: string | undefined, fallback: string) {
  const cleaned = (value ?? "")
    .trim()
    .replace(/[^a-z0-9\u4e00-\u9fff]+/gi, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 72);
  return cleaned || fallback;
}

function firstYear(value?: string) {
  return value?.match(/\d{4}/)?.[0] ?? "";
}

function normalizeCandidateDoi(value?: string | null) {
  if (!value) return "";
  const decoded = decodeURIComponent(value.trim())
    .replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, "")
    .replace(/^doi:\s*/i, "");
  return decoded.match(/10\.\d{4,9}\/[-._;()/:A-Z0-9]+/i)?.[0]?.replace(/[.,;]+$/, "") ?? "";
}

function candidateDoi(candidate: LiteratureDiscoveryCandidate) {
  return (
    normalizeCandidateDoi(candidate.doi) ||
    normalizeCandidateDoi(candidate.source_id) ||
    normalizeCandidateDoi(candidate.url) ||
    normalizeCandidateDoi(candidate.pdf_url)
  );
}

function candidateCitationKey(candidate: LiteratureDiscoveryCandidate) {
  const firstAuthor = (candidate.authors ?? "")
    .split(/\s+and\s+|\s*;\s*|\s*,\s*/i)
    .map((part) => part.trim())
    .find(Boolean);
  const authorToken = safeFileSegment(firstAuthor?.split(/\s+/).at(-1), "candidate");
  const yearToken = firstYear(candidate.year) || "noyear";
  const sourceToken = safeFileSegment(candidate.arxiv_id ?? candidate.doi ?? candidate.source_id ?? candidate.title, "paper");
  return `${authorToken}${yearToken}${sourceToken}`.replace(/-/g, "");
}

function candidateCitationText(candidate: LiteratureDiscoveryCandidate) {
  const parts = [
    candidate.authors,
    firstYear(candidate.year) ? `(${firstYear(candidate.year)})` : "",
    candidate.title,
    candidate.source,
    candidate.doi ? `https://doi.org/${candidate.doi}` : "",
    candidate.arxiv_id ? `arXiv:${candidate.arxiv_id}` : "",
    candidate.url ?? candidate.pdf_url ?? "",
  ].filter(Boolean);
  return parts.join(". ");
}

function candidateCitationMetadata(candidate: LiteratureDiscoveryCandidate) {
  return {
    citation_key: candidateCitationKey(candidate),
    candidate_summary: candidateCitationText(candidate),
    title: candidate.title,
    authors: candidate.authors ?? null,
    year: firstYear(candidate.year) || candidate.year || null,
    source: candidate.source,
    source_id: candidate.source_id ?? null,
    doi: candidate.doi ?? null,
    arxiv_id: candidate.arxiv_id ?? null,
    landing_page: candidate.url ?? null,
    pdf_url: candidate.pdf_url ?? null,
    download_method: candidate.download_method,
    status: candidate.status,
    trusted_bibtex_rule: candidateDoi(candidate)
      ? "Fetch BibTeX from DOI content negotiation, Crossref, or DataCite. Do not generate BibTeX locally."
      : "No DOI detected. Open the paper or publisher page to download an official citation file.",
  };
}

function downloadTextFile(filename: string, content: string, mimeType: string) {
  const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

function downloadCandidateCitationJson(candidate: LiteratureDiscoveryCandidate) {
  downloadTextFile(
    `${safeFileSegment(candidate.title, candidate.candidate_id)}.citation.json`,
    JSON.stringify(candidateCitationMetadata(candidate), null, 2),
    "application/json",
  );
}

function downloadCandidateBundle(
  candidates: LiteratureDiscoveryCandidate[],
  query: string,
  libraryName: string | undefined,
) {
  const prefix = safeFileSegment(`${libraryName ?? "library"}-${query}`, "literature-candidates");
  downloadTextFile(
    `${prefix}.citations.json`,
    JSON.stringify(
      {
        exported_at: new Date().toISOString(),
        query,
        library: libraryName ?? null,
        candidate_count: candidates.length,
        candidates: candidates.map(candidateCitationMetadata),
      },
      null,
      2,
    ),
    "application/json",
  );
}

function pdfReaderSrc(pdfUrl: string) {
  if (pdfUrl.includes("#")) return pdfUrl;
  return `${pdfUrl}#toolbar=1&navpanes=0`;
}

function mediaAssetsFromItem(item: PaperParseItem): PdfMediaAsset[] {
  const value = item.evidence?.metadata?.media_assets;
  return Array.isArray(value) ? (value as PdfMediaAsset[]) : [];
}

function riskLevelForItem(item: PaperParseItem): PdfRegionRiskLevel {
  if (item.status === "error") return "high";
  const mediaAssets = mediaAssetsFromItem(item);
  if (mediaAssets.some((asset) => asset.risk_level === "high")) return "high";
  if (mediaAssets.some((asset) => asset.risk_level === "review" || asset.review_required)) return "review";
  if (item.item_key === "media_region_quality_checked" && item.status === "warning") return "review";
  return "ok";
}

function riskLabel(level: PdfRegionRiskLevel) {
  if (level === "high") return "高风险";
  if (level === "review") return "需复核";
  return "可信";
}

function formatSectionType(value: string) {
  const labels: Record<string, string> = {
    abstract: "摘要",
    introduction: "引言",
    methods: "方法",
    method: "方法",
    experiments: "实验",
    experiment: "实验",
    results: "结果",
    discussion: "讨论",
    conclusion: "结论",
    references: "参考文献",
    tables: "表格",
    table: "表格",
    figures: "图",
    figure: "图",
  };
  return labels[value] ?? formatBackendText(value || "知识库片段");
}

function displayEvidenceSummary(value: string) {
  if (/已读取 PDF[:：]/.test(value)) return "PDF 已读取，详细路径见审计定位。";
  if (/全文文本已保存[:：]/.test(value)) return "全文文本已保存为解析产物。";
  if (/元数据 JSON[:：]/.test(value)) return "元数据已保存为解析产物。";
  if (/BibTeX[:：]/.test(value)) return "BibTeX 已保存为解析产物。";
  if (/论文记录已写入 SQLite[:：]/.test(value)) return "论文记录已写入知识库。";
  if (/[A-Za-z]:\\/.test(value) || value.includes(".knowledge_base")) return "解析产物已保存，详细路径见审计定位。";
  return value;
}

export function DataPage() {
  const location = useLocation();
  const { health } = useWorkbench();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState(getInitialFilter(location.search));
  const [selectedAsset, setSelectedAsset] = useState<DataAsset | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<{ run: PaperParseRun; item: PaperParseItem } | null>(null);
  const [selectedEvidenceSearch, setSelectedEvidenceSearch] = useState<{ paper: KnowledgePaper; run: PaperParseRun } | null>(null);
  const [parseRuns, setParseRuns] = useState<PaperParseRun[]>([]);
  const [papers, setPapers] = useState<KnowledgePaper[]>([]);
  const [libraries, setLibraries] = useState<LiteratureLibrary[]>([]);
  const [selectedLibraryId, setSelectedLibraryId] = useState("");
  const [newLibraryName, setNewLibraryName] = useState("");
  const [libraryCreateStatus, setLibraryCreateStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [dataStatus, setDataStatus] = useState<"idle" | "loading" | "error">("idle");
  const [inputMode, setInputMode] = useState<ParseInputMode>("upload");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [pdfPath, setPdfPath] = useState("");
  const [parseStatus, setParseStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [parseMessage, setParseMessage] = useState("");
  const [activeParseRun, setActiveParseRun] = useState<PaperParseRun | null>(null);
  const [ragflowStatus, setRagflowStatus] = useState<RagflowKnowledgeStatus | null>(null);
  const [reindexStatus, setReindexStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [reindexMessage, setReindexMessage] = useState("");
  const [ragQuery, setRagQuery] = useState("");
  const [ragStatus, setRagStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [ragResults, setRagResults] = useState<RagEvidenceResult[]>([]);
  const [discoveryQuery, setDiscoveryQuery] = useState("");
  const [discoverySource, setDiscoverySource] = useState<"auto" | "all" | "arxiv" | "pubmed" | "scholar">("auto");
  const [discoveryAutoIngest, setDiscoveryAutoIngest] = useState(false);
  const [discoveryStatus, setDiscoveryStatus] = useState<"idle" | "loading" | "success" | "limited" | "error">("idle");
  const [discoveryMessage, setDiscoveryMessage] = useState("");
  const [discoveryCandidates, setDiscoveryCandidates] = useState<LiteratureDiscoveryCandidate[]>([]);
  const [discoveryPlanner, setDiscoveryPlanner] = useState<LiteratureDiscoveryPlanner | null>(null);
  const [discoverySourceStatuses, setDiscoverySourceStatuses] = useState<
    Array<{ call_id?: string; tool_id: string; display_name: string; status: string; message: string; query?: string; rationale?: string }>
  >([]);
  const [expandedAbstractIds, setExpandedAbstractIds] = useState<Set<string>>(() => new Set());
  const [abstractTranslations, setAbstractTranslations] = useState<Record<string, string>>({});
  const [abstractTranslationLoadingId, setAbstractTranslationLoadingId] = useState<string | null>(null);
  const [abstractTranslationErrorId, setAbstractTranslationErrorId] = useState<string | null>(null);
  const [candidateParseId, setCandidateParseId] = useState<string | null>(null);
  const [citationFetchId, setCitationFetchId] = useState<string | null>(null);
  const [citationStatus, setCitationStatus] = useState<"idle" | "loading" | "success" | "warning" | "error">("idle");
  const [citationMessage, setCitationMessage] = useState("");
  const [selectedPdfReader, setSelectedPdfReader] = useState<LiteratureDiscoveryCandidate | null>(null);
  const pdfPathRef = useRef<HTMLInputElement | null>(null);
  const uploadRef = useRef<HTMLInputElement | null>(null);
  const paperLibraryRef = useRef<HTMLElement | null>(null);
  const drawerRef = useRef<HTMLElement | null>(null);
  const drawerCloseRef = useRef<HTMLButtonElement | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const literatureReady = Boolean(health?.literature_mcp?.available);
  const activeLibrary = libraries.find((library) => library.library_id === selectedLibraryId) ?? libraries[0] ?? null;
  const activeLibraryId = activeLibrary?.library_id ?? selectedLibraryId;

  const refreshData = useCallback(async () => {
    setDataStatus("loading");
    try {
      const libraryResult = await listLiteratureLibraries();
      const nextLibraryId = selectedLibraryId || libraryResult.default_library_id || libraryResult.libraries[0]?.library_id || "";
      setLibraries(libraryResult.libraries);
      if (!selectedLibraryId && nextLibraryId) {
        setSelectedLibraryId(nextLibraryId);
      }
      const scopedLibraryId = nextLibraryId || undefined;
      const [parseRunResult, paperResult, ragflowResult] = await Promise.all([
        listPaperParseRuns({ library_id: scopedLibraryId }),
        listKnowledgePapers({ library_id: scopedLibraryId }),
        fetchRagflowKnowledgeStatus(),
      ]);
      setParseRuns(parseRunResult.parse_runs);
      setPapers(paperResult.papers);
      setRagflowStatus(ragflowResult);
      setActiveParseRun((current) => {
        if (current) {
          return parseRunResult.parse_runs.find((run) => run.parse_run_id === current.parse_run_id) ?? parseRunResult.parse_runs[0] ?? null;
        }
        return parseRunResult.parse_runs[0] ?? null;
      });
      setDataStatus("idle");
    } catch {
      setDataStatus("error");
    }
  }, [selectedLibraryId]);

  useEffect(() => {
    void refreshData();
  }, [refreshData]);

  useEffect(() => {
    setRagResults([]);
    setRagStatus("idle");
    setDiscoveryCandidates([]);
    setDiscoverySourceStatuses([]);
    setDiscoveryStatus("idle");
    setDiscoveryMessage("");
    setCitationFetchId(null);
    setCitationStatus("idle");
    setCitationMessage("");
    setReindexStatus("idle");
    setReindexMessage("");
    setSelectedEvidenceSearch(null);
    setSelectedPdfReader(null);
  }, [selectedLibraryId]);

  useEffect(() => {
    if (!activeLibraryId) return;
    window.localStorage.setItem("coscientist.activeLibraryId", activeLibraryId);
    window.localStorage.setItem("coscientist.activeLibraryName", activeLibrary?.name ?? activeLibraryId);
  }, [activeLibrary?.name, activeLibraryId]);

  useEffect(() => {
    if (!selectedAsset && !selectedEvidence && !selectedEvidenceSearch && !selectedPdfReader) return;
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    drawerCloseRef.current?.focus();
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setSelectedAsset(null);
        setSelectedEvidence(null);
        setSelectedEvidenceSearch(null);
        setSelectedPdfReader(null);
        return;
      }
      if (event.key !== "Tab" || !drawerRef.current) return;
      const focusable = getFocusableElements(drawerRef.current);
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      previousFocusRef.current?.focus();
    };
  }, [selectedAsset, selectedEvidence, selectedEvidenceSearch, selectedPdfReader]);

  const handleParseSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setParseStatus("loading");
    setParseMessage("");
    try {
      const result =
        inputMode === "upload"
          ? await uploadParseKnowledgePdf(uploadFile as File, activeLibraryId)
          : await parseKnowledgePdf({
              pdf_path: pdfPath,
              fetch_metadata: true,
              ingest_to_knowledge_base: true,
              library_id: activeLibraryId,
            });
      const run: PaperParseRun = {
        parse_run_id: result.parse_run_id,
        paper_id: result.paper_id,
        library_id: result.library_id,
        title: result.title,
        status: result.status,
        input_kind: inputMode,
        input_path: inputMode === "upload" ? uploadFile?.name ?? "uploaded.pdf" : pdfPath,
        pdf_path: inputMode === "local_path" ? pdfPath : undefined,
        solve_dir: result.solve_dir,
        page_count: result.page_count,
        chunks_count: result.chunks_count,
        experimental_chunks_count: result.experimental_chunks_count,
        knowledge_base_ingested: result.knowledge_base_ingested,
        rag_search_ready: result.rag_search_ready,
        items: result.items,
      };
      setActiveParseRun(run);
      setParseStatus("success");
      setParseMessage(`已完成解析：${result.title}，生成 ${result.chunks_count} 个知识库片段。`);
      setUploadFile(null);
      await refreshData();
    } catch {
      setParseStatus("error");
      setParseMessage("论文暂时未能解析入库，请检查 PDF、路径权限或后端依赖后重试。");
    }
  };

  const handleRagSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!ragQuery.trim()) return;
    setRagStatus("loading");
    try {
      const scopedRun = selectedEvidenceSearch?.run ?? activeParseRun;
      const result = await searchRagEvidence({
        q: ragQuery,
        paper_id: scopedRun?.paper_id ?? undefined,
        library_id: activeLibraryId,
        limit: 8,
      });
      setRagResults(result.results);
      setRagStatus("success");
    } catch {
      setRagResults([]);
      setRagStatus("error");
    }
  };

  const handleReindexRagflow = async () => {
    if (!activeLibraryId) return;
    setReindexStatus("loading");
    setReindexMessage("");
    try {
      const result = await reindexRagflowEmbeddings({ library_id: activeLibraryId });
      setRagflowStatus(result.ragflow);
      setReindexStatus(result.status === "complete" ? "success" : "error");
      setReindexMessage(`已处理 ${result.paper_count} 篇论文；当前向量索引 ${result.ragflow.embedding.indexed_chunks}/${result.ragflow.embedding.total_chunks} 个 chunk。`);
      await refreshData();
    } catch {
      setReindexStatus("error");
      setReindexMessage("向量索引暂时无法重建，请检查 embedding provider 环境变量或模型服务。");
    }
  };

  const handleCreateLibrary = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!newLibraryName.trim()) return;
    setLibraryCreateStatus("loading");
    try {
      const result = await createLiteratureLibrary({ name: newLibraryName.trim() });
      setLibraries((current) => [...current, result.library]);
      setSelectedLibraryId(result.library.library_id);
      setNewLibraryName("");
      setLibraryCreateStatus("success");
      await refreshData();
    } catch {
      setLibraryCreateStatus("error");
    }
  };

  const handleOpenLibrary = (libraryId: string) => {
    setSelectedLibraryId(libraryId);
    setFilter("Papers");
    window.setTimeout(() => {
      paperLibraryRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 80);
  };

  const assetFromPaper = (paper: KnowledgePaper): DataAsset => ({
    id: paper.paper_id,
    name: paper.title,
    type: "Papers",
    status: paper.chunks_count > 0 ? "可用于证据检索" : "缺少片段",
    tone: paper.chunks_count > 0 ? "ok" : "warning",
    source: formatBackendText(paper.source_reliability),
    coverage: `${paper.chunks_count} 个片段 / ${paper.experimental_chunks_count} 个实验线索`,
    updated: formatTime(paper.created_at),
    detail: [
      `论文已写入「${activeLibrary?.name ?? "当前文献库"}」。`,
      paper.authors?.length ? `作者：${paper.authors.join(", ")}` : "",
      paper.year ? `年份：${paper.year}` : "",
      paper.doi ? `DOI：${paper.doi}` : "",
      paper.url ? `URL：${paper.url}` : "",
      "后续候选假设可以通过知识库检索复用该论文证据。",
    ].filter(Boolean).join("\n"),
  });

  const handleDiscoverLiterature = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!discoveryQuery.trim() || !activeLibraryId) return;
    setDiscoveryStatus("loading");
    setDiscoveryMessage("");
    setDiscoveryCandidates([]);
    setDiscoveryPlanner(null);
    setDiscoverySourceStatuses([]);
    setExpandedAbstractIds(new Set());
    setAbstractTranslations({});
    setAbstractTranslationLoadingId(null);
    setAbstractTranslationErrorId(null);
    setCitationFetchId(null);
    setCitationStatus("idle");
    setCitationMessage("");
    try {
      const result = await discoverLiteraturePapers({
        query: discoveryQuery.trim(),
        library_id: activeLibraryId,
        preferred_source: discoverySource,
        max_results: 12,
        planning_mode: discoverySource === "auto" ? "llm" : "rules",
        auto_discover_pdf_links: true,
        auto_ingest_pdfs: discoveryAutoIngest,
        auto_ingest_limit: discoveryAutoIngest ? 12 : 0,
        approval: {
          confirmed: true,
          scope: "mcp.literature_review",
          reason: discoveryAutoIngest
            ? `研究员请求为文献库 ${activeLibrary?.name ?? activeLibraryId} 搜索可下载论文，并自动解析可信公开 PDF`
            : `研究员请求为文献库 ${activeLibrary?.name ?? activeLibraryId} 搜索可下载论文，先展示候选再人工选择入库`,
        },
      });
      setDiscoveryCandidates(result.candidates);
      setDiscoveryPlanner(result.planner ?? null);
      setDiscoverySourceStatuses(result.source_statuses ?? []);
      setDiscoveryMessage(result.message);
      setDiscoveryStatus(result.status === "ready" ? "success" : "limited");
    } catch {
      setDiscoveryCandidates([]);
      setDiscoveryPlanner(null);
      setDiscoverySourceStatuses([]);
      setDiscoveryMessage("文献搜索暂时未完成，请检查外部文献服务状态，或改用 PDF 上传/URL 解析。");
      setDiscoveryStatus("error");
    }
  };

  const toggleCandidateAbstract = (candidateId: string) => {
    setExpandedAbstractIds((existing) => {
      const next = new Set(existing);
      if (next.has(candidateId)) {
        next.delete(candidateId);
      } else {
        next.add(candidateId);
      }
      return next;
    });
  };

  const handleTranslateCandidateAbstract = async (candidate: LiteratureDiscoveryCandidate) => {
    if (!candidate.abstract) return;
    setAbstractTranslationErrorId(null);
    setAbstractTranslationLoadingId(candidate.candidate_id);
    try {
      const result = await translateEvidenceText({
        model_name: "openai/mimo-v2.5",
        text: candidate.abstract,
        target_language: "zh-Hans",
        provider: "auto",
      });
      setAbstractTranslations((existing) => ({
        ...existing,
        [candidate.candidate_id]: result.translation,
      }));
      setExpandedAbstractIds((existing) => {
        const next = new Set(existing);
        next.add(candidate.candidate_id);
        return next;
      });
    } catch {
      setAbstractTranslationErrorId(candidate.candidate_id);
    } finally {
      setAbstractTranslationLoadingId(null);
    }
  };

  const fetchTrustedBibtex = async (candidate: LiteratureDiscoveryCandidate) => {
    return fetchLiteratureCitationBibtex({
      title: candidate.title,
      source: candidate.source,
      source_id: candidate.source_id,
      doi: candidateDoi(candidate) || candidate.doi,
      arxiv_id: candidate.arxiv_id,
      url: candidate.url,
      pdf_url: candidate.pdf_url,
      approval: {
        confirmed: true,
        scope: "citation.metadata",
        reason: `研究员请求下载可信 BibTeX：${candidate.title}`,
      },
    });
  };

  const handleDownloadTrustedBibtex = async (candidate: LiteratureDiscoveryCandidate) => {
    if (!candidateDoi(candidate)) {
      setCitationStatus("warning");
      setCitationMessage("当前候选没有 DOI，系统不会自行生成 BibTeX；请打开论文页或机构访问入口下载官方引用文件。");
      return;
    }
    setCitationFetchId(candidate.candidate_id);
    setCitationStatus("loading");
    setCitationMessage("正在通过 DOI/Crossref/DataCite 获取可信 BibTeX。");
    try {
      const result = await fetchTrustedBibtex(candidate);
      if (result.status === "ready" && result.bibtex) {
        downloadTextFile(`${safeFileSegment(candidate.title, candidate.candidate_id)}.bib`, result.bibtex, "application/x-bibtex");
        setCitationStatus("success");
        setCitationMessage(`已下载可信 BibTeX：${result.source}。`);
      } else {
        setCitationStatus("warning");
        setCitationMessage(result.message);
      }
    } catch {
      setCitationStatus("error");
      setCitationMessage("可信 BibTeX 获取失败，请打开论文页或 DOI 页面手动下载官方引用文件。");
    } finally {
      setCitationFetchId(null);
    }
  };

  const handleDownloadTrustedBibtexBundle = async () => {
    const candidatesWithDoi = discoveryCandidates.filter((candidate) => candidateDoi(candidate));
    if (candidatesWithDoi.length === 0) {
      setCitationStatus("warning");
      setCitationMessage("当前候选列表没有 DOI，不能规则化获取可信 BibTeX；请使用机构访问或论文页下载官方引用文件。");
      return;
    }
    setCitationFetchId("bundle");
    setCitationStatus("loading");
    setCitationMessage(`正在获取 ${candidatesWithDoi.length} 条 DOI 候选的可信 BibTeX。`);
    try {
      const entries: string[] = [];
      for (const candidate of candidatesWithDoi) {
        const result = await fetchTrustedBibtex(candidate);
        if (result.status === "ready" && result.bibtex) {
          entries.push(result.bibtex.trim());
        }
      }
      if (entries.length > 0) {
        const prefix = safeFileSegment(`${activeLibrary?.name ?? "library"}-${discoveryQuery}`, "trusted-bibtex");
        downloadTextFile(`${prefix}.bib`, `${entries.join("\n\n")}\n`, "application/x-bibtex");
        setCitationStatus("success");
        setCitationMessage(`已下载 ${entries.length} 条可信 BibTeX；未返回的条目需到论文页或期刊页人工获取。`);
      } else {
        setCitationStatus("warning");
        setCitationMessage("这些 DOI 暂未通过 DOI/Crossref/DataCite 返回 BibTeX，请到期刊页或机构访问入口下载官方引用文件。");
      }
    } catch {
      setCitationStatus("error");
      setCitationMessage("可信 BibTeX 合集获取失败，请稍后重试或逐篇打开 DOI/期刊页核查。");
    } finally {
      setCitationFetchId(null);
    }
  };

  const handleParseCandidate = async (candidate: LiteratureDiscoveryCandidate) => {
    if (!candidate.pdf_url || !activeLibraryId) return;
    setCandidateParseId(candidate.candidate_id);
    setParseStatus("loading");
    setParseMessage("");
    try {
      const result = await parseKnowledgePdf({
        pdf_path: candidate.pdf_url,
        fetch_metadata: true,
        ingest_to_knowledge_base: true,
        library_id: activeLibraryId,
      });
      setParseStatus("success");
      setParseMessage(`已下载并解析到「${activeLibrary?.name ?? "当前文献库"}」：${result.title}`);
      setActiveParseRun({
        parse_run_id: result.parse_run_id,
        paper_id: result.paper_id,
        library_id: result.library_id,
        title: result.title,
        status: result.status,
        input_kind: "local_path",
        input_path: candidate.pdf_url,
        pdf_path: candidate.pdf_url,
        solve_dir: result.solve_dir,
        page_count: result.page_count,
        chunks_count: result.chunks_count,
        experimental_chunks_count: result.experimental_chunks_count,
        knowledge_base_ingested: result.knowledge_base_ingested,
        rag_search_ready: result.rag_search_ready,
        items: result.items,
      });
      await refreshData();
    } catch {
      setParseStatus("error");
      setParseMessage("候选论文暂时无法下载解析，请检查 PDF 地址是否可直接访问，或手动上传 PDF。");
    } finally {
      setCandidateParseId(null);
    }
  };

  const assets = useMemo<DataAsset[]>(() => {
    const paperAssets = papers.map(assetFromPaper);
    const jobAssets = parseRuns.map((run) => ({
      id: run.parse_run_id,
      name: run.title,
      type: "Jobs" as const,
      status: statusLabel(run.status),
      tone: statusTone(run.status),
      source: run.input_kind === "upload" ? "浏览器上传" : "本机路径",
      coverage: `${run.chunks_count} 个片段 / ${run.experimental_chunks_count} 个实验线索`,
      updated: formatTime(run.updated_at),
      detail: `解析任务${run.rag_search_ready ? "已进入可检索证据状态" : "尚未形成可检索证据"}。`,
    }));
    return [
      {
        id: "literature-service",
        name: "文献支撑服务",
        type: "Provenance",
        status: literatureReady ? "可用于研究" : "需要检查",
        tone: literatureReady ? "ok" : "warning",
        source: "运行准备",
        coverage: literatureReady ? "可附加外部来源证据" : "不可静默降级",
        updated: "实时检查",
        detail: "文献服务是实时科研路径的硬前提。论文解析入库提供本地证据，外部来源检索仍由文献支撑服务负责。",
      },
      ...jobAssets,
      ...paperAssets,
    ];
  }, [activeLibrary?.name, literatureReady, papers, parseRuns]);

  const filteredAssets = assets.filter((asset) => {
    const filterMatch = filter === "all" || asset.type === filter;
    const normalized = query.trim().toLowerCase();
    const queryMatch =
      normalized.length === 0 ||
      `${asset.name} ${asset.type} ${asset.status} ${asset.source}`.toLowerCase().includes(normalized);
    return filterMatch && queryMatch;
  });

  const parseButtonDisabled =
    parseStatus === "loading" ||
    !activeLibraryId ||
    (inputMode === "upload" && !uploadFile) ||
    (inputMode === "local_path" && !pdfPath.trim().toLowerCase().endsWith(".pdf"));

  return (
    <div className="page-stack">
      <PageHeader
        kicker="资料管理"
        title="资料库"
        actions={
          <div className="page-header-actions">
            <Link className="button-secondary" to="/workspace">
              进入工作区
            </Link>
            <button className="button-primary" type="button" onClick={() => uploadRef.current?.click()}>
              补充论文
            </button>
            <button className="button-secondary" type="button" onClick={() => void refreshData()}>
              刷新状态
            </button>
          </div>
        }
      />

      <section className="surface-card literature-library-workbench">
        <div className="section-heading">
          <div>
            <h2>文献库</h2>
            <p>为不同研究方向建立独立文献库，上传或发现论文后写入对应证据库。</p>
          </div>
          <span className={classNames("status-pill", literatureReady ? "ok" : "warning")}>
            {literatureReady ? "外部文献服务可用" : "外部文献服务受限"}
          </span>
        </div>

        <div className="literature-library-grid">
          <aside className="library-rail" aria-label="文献库列表">
            <div className="library-list">
              {libraries.map((library) => (
                <button
                  className={classNames("library-option", activeLibraryId === library.library_id && "selected")}
                  key={library.library_id}
                  type="button"
                  onClick={() => handleOpenLibrary(library.library_id)}
                  aria-pressed={activeLibraryId === library.library_id}
                >
                  <BookOpen size={16} />
                  <span>
                    <strong>{library.name}</strong>
                    <small>
                      {library.paper_count} 篇论文 · {library.chunk_count} 个片段
                    </small>
                  </span>
                </button>
              ))}
            </div>
            <form className="library-create-form" onSubmit={(event) => void handleCreateLibrary(event)}>
              <label className="field-stack" htmlFor="library-name">
                <span>新文献库名称</span>
                <input
                  id="library-name"
                  type="text"
                  value={newLibraryName}
                  maxLength={120}
                  onChange={(event) => setNewLibraryName(event.target.value)}
                  placeholder="例如：VLA 入门"
                />
              </label>
              <button
                className={classNames("button-secondary", libraryCreateStatus === "loading" && "is-loading")}
                type="submit"
                disabled={libraryCreateStatus === "loading" || !newLibraryName.trim()}
                aria-busy={libraryCreateStatus === "loading"}
              >
                <Plus size={15} />
                创建文献库
              </button>
              {libraryCreateStatus === "error" ? (
                <span className="control-feedback error" role="alert">文献库未能创建，请换一个名称后重试。</span>
              ) : null}
            </form>
          </aside>

          <div className="library-main-stack">
            <section className="library-paper-panel" ref={paperLibraryRef} aria-label="当前文献库论文">
              <div className="section-heading compact">
                <div>
                  <h3>{activeLibrary ? `当前文献库：${activeLibrary.name}` : "当前文献库"}</h3>
                  <p>点击文献库后，论文会在这里展开；选择论文可查看详情或作为证据检索范围。</p>
                </div>
                <span className="status-pill neutral">{papers.length} 篇论文</span>
              </div>
              {dataStatus === "loading" ? (
                <SkeletonState title="正在读取当前文献库论文" rows={3} />
              ) : papers.length > 0 ? (
                <div className="library-paper-list" role="list">
                  {papers.map((paper) => {
                    const linkedRun =
                      parseRuns.find((run) => run.paper_id === paper.paper_id) ??
                      parseRuns.find((run) => run.title === paper.title) ??
                      null;
                    return (
                      <article className="library-paper-row" key={paper.paper_id} role="listitem">
                        <div className="library-paper-copy">
                          <span className="paper-row-icon">
                            <BookOpen size={16} />
                          </span>
                          <div>
                            <strong>{paper.title}</strong>
                            <small>
                              {paper.authors?.length ? `${paper.authors.slice(0, 3).join(", ")} · ` : ""}
                              {paper.year ? `${paper.year} · ` : ""}
                              {formatBackendText(paper.source_reliability)}
                            </small>
                          </div>
                        </div>
                        <div className="library-paper-stats" aria-label="论文入库统计">
                          <span>{paper.chunks_count} 个片段</span>
                          <span>{paper.experimental_chunks_count} 个实验线索</span>
                        </div>
                        <div className="library-paper-actions">
                          <button className="button-secondary" type="button" onClick={() => setSelectedAsset(assetFromPaper(paper))}>
                            <Eye size={15} />
                            查看详情
                          </button>
                          <button
                            className="button-secondary"
                            type="button"
                            disabled={!linkedRun}
                            onClick={() => {
                              if (!linkedRun) return;
                              setActiveParseRun(linkedRun);
                              setRagQuery(paper.title);
                              setRagResults([]);
                              setRagStatus("idle");
                              setSelectedEvidenceSearch({ paper, run: linkedRun });
                            }}
                          >
                            <Search size={15} />
                            检索证据
                          </button>
                          {paper.url ? (
                            <a className="button-secondary" href={paper.url} target="_blank" rel="noreferrer">
                              <ExternalLink size={15} />
                              打开原文
                            </a>
                          ) : null}
                        </div>
                      </article>
                    );
                  })}
                </div>
              ) : (
                <EmptyState
                  title="当前文献库还没有论文"
                  description="可以上传 PDF、输入本机 PDF 路径，或在下方搜索公开文献并解析到当前库。"
                />
              )}
            </section>

          <div className="paper-discovery-panel">
            <div className="section-heading compact">
              <div>
                <h3>{activeLibrary ? `文献发现：${activeLibrary.name}` : "文献发现"}</h3>
                <p>直接检索公开文献源，确认 PDF 地址后解析到当前文献库；后续假设生成会优先复用这些入库证据。</p>
              </div>
            </div>
            <form className="paper-discovery-form" onSubmit={(event) => void handleDiscoverLiterature(event)}>
              <label className="command-input" htmlFor="literature-discovery-query">
                <Search size={16} />
                <input
                  id="literature-discovery-query"
                  type="search"
                  value={discoveryQuery}
                  onChange={(event) => setDiscoveryQuery(event.target.value)}
                  placeholder="搜索论文主题，例如：vision language action model survey"
                />
              </label>
              <div className="segmented-control compact" role="tablist" aria-label="文献搜索来源">
                {[
                  { value: "auto", label: "AI 自动" },
                  { value: "all", label: "全部" },
                  { value: "arxiv", label: "arXiv" },
                  { value: "pubmed", label: "PubMed" },
                  { value: "scholar", label: "Scholar" },
                ].map((item) => (
                  <button
                    className={classNames(discoverySource === item.value && "selected")}
                    key={item.value}
                    type="button"
                    role="tab"
                    aria-selected={discoverySource === item.value}
                    onClick={() => setDiscoverySource(item.value as typeof discoverySource)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              <label className="discovery-option-toggle">
                <input
                  type="checkbox"
                  checked={discoveryAutoIngest}
                  onChange={(event) => setDiscoveryAutoIngest(event.target.checked)}
                />
                <span>搜索后自动解析可下载 PDF 到当前资料库</span>
              </label>
              <button
                className={classNames("button-primary", discoveryStatus === "loading" && "is-loading")}
                type="submit"
                disabled={discoveryStatus === "loading" || !discoveryQuery.trim() || !activeLibraryId}
                aria-busy={discoveryStatus === "loading"}
              >
                <Sparkles size={15} />
                搜索文献
              </button>
            </form>
            {discoveryMessage ? (
              <article
                className={classNames(
                  "status-banner",
                  discoveryStatus === "error" ? "error" : discoveryStatus === "limited" ? "warning" : "ok",
                )}
                role={discoveryStatus === "error" ? "alert" : "status"}
              >
                {discoveryMessage}
              </article>
            ) : null}
            {discoveryPlanner ? (
              <article className="status-banner neutral literature-planner-summary" role="status">
                <strong>
                  {discoveryPlanner.mode === "llm" ? "模型已分析检索意图" : "规则检索计划"}
                  {discoveryPlanner.model_name ? ` · ${discoveryPlanner.model_name}` : ""}
                </strong>
                {discoveryPlanner.intent_summary ? <span>{discoveryPlanner.intent_summary}</span> : null}
                {discoveryPlanner.reason ? <span>{discoveryPlanner.reason}</span> : null}
                {discoveryPlanner.tool_queries?.length ? (
                  <div className="chat-source-status-row" aria-label="模型生成的检索式">
                    {discoveryPlanner.tool_queries.map((item) => (
                      <small key={`${item.tool_id}-${item.query}`} title={item.rationale}>
                        {formatBackendText(item.tool_id)} · {item.query}
                      </small>
                    ))}
                  </div>
                ) : null}
              </article>
            ) : null}
            {discoverySourceStatuses.length ? (
              <div className="chat-source-status-row" aria-label="文献搜索来源状态">
                {discoverySourceStatuses.map((source) => (
                  <small key={source.call_id ?? source.tool_id} title={[source.message, source.query, source.rationale].filter(Boolean).join(" · ")}>
                    {source.display_name} · {formatBackendText(source.status)}
                    {source.query ? ` · ${source.query}` : ""}
                  </small>
                ))}
              </div>
            ) : null}
            {discoveryStatus === "loading" ? <SkeletonState title="正在检索可下载论文" rows={3} /> : null}
            {discoveryCandidates.length > 0 ? (
              <div className="literature-candidate-list">
                <article className="status-banner neutral" role="status">
                  如果候选不能直接解析，请打开论文页面，通过学校或机构账号完成授权下载 PDF，然后回到当前文献库上传解析。
                </article>
                <article className="citation-download-panel" aria-labelledby="candidate-citation-downloads">
                  <div>
                    <h4 id="candidate-citation-downloads">引用核查</h4>
                    <p>可信 BibTeX 只从 DOI、Crossref 或 DataCite 获取；候选元数据用于核对 DOI、arXiv、来源页和 PDF 地址。</p>
                  </div>
                  <div className="candidate-action-row">
                    <button
                      className={classNames("button-secondary", citationFetchId === "bundle" && "is-loading")}
                      type="button"
                      disabled={citationFetchId !== null}
                      aria-busy={citationFetchId === "bundle"}
                      onClick={() => void handleDownloadTrustedBibtexBundle()}
                    >
                      <FileText size={15} />
                      获取可信 .bib 合集
                    </button>
                    <button
                      className="button-secondary"
                      type="button"
                      onClick={() => downloadCandidateBundle(discoveryCandidates, discoveryQuery, activeLibrary?.name)}
                    >
                      <DownloadCloud size={15} />
                      下载候选元数据
                    </button>
                  </div>
                </article>
                {citationMessage ? (
                  <article
                    className={classNames(
                      "status-banner",
                      citationStatus === "error" ? "error" : citationStatus === "warning" ? "warning" : citationStatus === "success" ? "ok" : "neutral",
                    )}
                    role={citationStatus === "error" ? "alert" : "status"}
                  >
                    {citationMessage}
                  </article>
                ) : null}
                {discoveryCandidates.map((candidate) => (
                  <article className="literature-candidate-card" key={candidate.candidate_id}>
                    <header>
                      <div>
                        <strong>{candidate.title}</strong>
                        <span>
                          {candidate.source}
                          {candidate.year ? ` · ${candidate.year}` : ""}
                        </span>
                      </div>
                      <span className={classNames("status-pill", candidate.can_parse_pdf ? "ok" : "warning")}>
                        {candidate.can_parse_pdf ? "可解析 PDF" : "需补 PDF"}
                      </span>
                    </header>
                    {candidate.abstract ? (
                      <div className="candidate-abstract-actions">
                        <button className="button-secondary" type="button" onClick={() => toggleCandidateAbstract(candidate.candidate_id)}>
                          {expandedAbstractIds.has(candidate.candidate_id) ? "收起摘要" : "展开摘要"}
                        </button>
                        <button
                          className={classNames("button-secondary", abstractTranslationLoadingId === candidate.candidate_id && "is-loading")}
                          type="button"
                          disabled={abstractTranslationLoadingId !== null}
                          aria-busy={abstractTranslationLoadingId === candidate.candidate_id}
                          onClick={() =>
                            abstractTranslations[candidate.candidate_id]
                              ? toggleCandidateAbstract(candidate.candidate_id)
                              : void handleTranslateCandidateAbstract(candidate)
                          }
                        >
                          {abstractTranslationLoadingId === candidate.candidate_id
                            ? "翻译中"
                            : abstractTranslations[candidate.candidate_id]
                              ? "查看译文"
                              : "翻译摘要"}
                        </button>
                      </div>
                    ) : null}
                    {candidate.abstract && expandedAbstractIds.has(candidate.candidate_id) ? <p>{candidate.abstract}</p> : null}
                    {abstractTranslations[candidate.candidate_id] && expandedAbstractIds.has(candidate.candidate_id) ? (
                      <p className="candidate-translated-abstract">{abstractTranslations[candidate.candidate_id]}</p>
                    ) : null}
                    {abstractTranslationErrorId === candidate.candidate_id ? (
                      <article className="status-banner warning" role="status">
                        摘要翻译暂时不可用，请检查翻译服务或模型凭据。
                      </article>
                    ) : null}
                    {candidate.discovery_query ? (
                      <small className="candidate-discovery-query">检索式：{candidate.discovery_query}</small>
                    ) : null}
                    {candidate.auto_ingest ? (
                      <article
                        className={classNames(
                          "status-banner",
                          candidate.auto_ingest.status === "ingested"
                            ? "ok"
                            : candidate.auto_ingest.status === "failed"
                              ? "warning"
                              : "neutral",
                        )}
                        role="status"
                      >
                        {candidate.auto_ingest.status === "ingested"
                          ? `已自动解析入库${candidate.auto_ingest.chunks_count ? ` · ${candidate.auto_ingest.chunks_count} 个片段` : ""}`
                          : candidate.auto_ingest.status === "failed"
                            ? `自动解析失败：${candidate.auto_ingest.message ?? "请手动打开 PDF 后重试"}`
                            : "自动解析状态待确认"}
                      </article>
                    ) : null}
                    <footer>
                      <span>{candidate.download_method}</span>
                      <div className="candidate-action-row">
                        {candidate.pdf_url ? (
                          <>
                            <button className="button-secondary" type="button" onClick={() => setSelectedPdfReader(candidate)}>
                              <Eye size={15} />
                              阅读 PDF
                            </button>
                            <a className="button-secondary" href={candidate.pdf_url} target="_blank" rel="noreferrer">
                              <ExternalLink size={15} />
                              打开 PDF
                            </a>
                          </>
                        ) : candidate.url ? (
                          <a className="button-secondary" href={candidate.url} target="_blank" rel="noreferrer">
                            <ExternalLink size={15} />
                            机构访问
                          </a>
                        ) : null}
                        <button
                          className={classNames("button-secondary", citationFetchId === candidate.candidate_id && "is-loading")}
                          type="button"
                          disabled={!candidateDoi(candidate) || citationFetchId !== null}
                          aria-busy={citationFetchId === candidate.candidate_id}
                          title={candidateDoi(candidate) ? "通过 DOI/Crossref/DataCite 获取可信 BibTeX" : "没有 DOI，不能规则化获取可信 BibTeX"}
                          onClick={() => void handleDownloadTrustedBibtex(candidate)}
                        >
                          <FileText size={15} />
                          {citationFetchId === candidate.candidate_id ? "获取中" : candidateDoi(candidate) ? "可信 BibTeX" : "无 DOI/BibTeX"}
                        </button>
                        <button className="button-secondary" type="button" onClick={() => downloadCandidateCitationJson(candidate)}>
                          <DownloadCloud size={15} />
                          候选元数据
                        </button>
                        <button
                          className={classNames("button-secondary", candidateParseId === candidate.candidate_id && "is-loading")}
                          type="button"
                          disabled={!candidate.can_parse_pdf || candidateParseId === candidate.candidate_id}
                          aria-busy={candidateParseId === candidate.candidate_id}
                          onClick={() => void handleParseCandidate(candidate)}
                        >
                          <DownloadCloud size={15} />
                          {candidateParseId === candidate.candidate_id ? "解析中" : "加入资料库"}
                        </button>
                      </div>
                    </footer>
                    <details className="expert-summary">
                      <summary>查看地址、标识与下载方式</summary>
                      <dl className="evidence-detail-list">
                        <div>
                          <dt>Citation key</dt>
                          <dd>{candidateCitationKey(candidate)}</dd>
                        </div>
                        <div>
                          <dt>候选元数据摘要</dt>
                          <dd>{candidateCitationText(candidate)}</dd>
                        </div>
                        {candidate.doi ? (
                          <div>
                            <dt>DOI</dt>
                            <dd>{candidate.doi}</dd>
                          </div>
                        ) : null}
                        {candidate.arxiv_id ? (
                          <div>
                            <dt>arXiv</dt>
                            <dd>{candidate.arxiv_id}</dd>
                          </div>
                        ) : null}
                        {candidate.pdf_url ? (
                          <div>
                            <dt>PDF 地址</dt>
                            <dd>{candidate.pdf_url}</dd>
                          </div>
                        ) : null}
                        {candidate.url ? (
                          <div>
                            <dt>论文页面</dt>
                            <dd>{candidate.url}</dd>
                          </div>
                        ) : null}
                      </dl>
                    </details>
                  </article>
                ))}
              </div>
            ) : discoveryStatus === "limited" ? (
              <EmptyState title="暂未发现可下载候选" description="可以换用更具体的关键词，或直接上传 PDF 到当前文献库。" />
            ) : null}
          </div>
          </div>
        </div>
      </section>

      <section className="surface-card parse-workbench">
        <div className="section-heading">
          <div>
            <h2>论文入库</h2>
            <p>{activeLibrary ? `当前写入：${activeLibrary.name}` : "解析后的论文会写入默认文献库。"}</p>
          </div>
        </div>
        {ragflowStatus ? (
          <article className="status-banner neutral" role="status">
            <div>
              <strong>RAGFlow 适配检索：{formatBackendText(ragflowStatus.mode)}</strong>
              <p>
                Chunk {ragflowStatus.chunking.chunk_token_num} tokens · 向量 {ragflowStatus.embedding.indexed_chunks}/{ragflowStatus.embedding.total_chunks}
                {ragflowStatus.embedding.enabled ? ` · ${ragflowStatus.embedding.provider}` : " · embedding 未启用"}
                {ragflowStatus.reranker.enabled ? ` · reranker ${ragflowStatus.reranker.provider}` : " · reranker 未启用"}
              </p>
            </div>
            <button
              className={classNames("button-secondary", reindexStatus === "loading" && "is-loading")}
              type="button"
              disabled={reindexStatus === "loading" || !activeLibraryId}
              aria-busy={reindexStatus === "loading"}
              onClick={() => void handleReindexRagflow()}
            >
              <RefreshCw size={15} />
              {reindexStatus === "loading" ? "重建中" : "重建向量索引"}
            </button>
          </article>
        ) : null}
        {reindexMessage ? (
          <p className={classNames("control-feedback", reindexStatus === "error" ? "error" : "success")} role={reindexStatus === "error" ? "alert" : "status"}>
            {reindexMessage}
          </p>
        ) : null}
        <form className="parse-control-grid" onSubmit={(event) => void handleParseSubmit(event)}>
          <div className="segmented-control" role="tablist" aria-label="论文输入方式">
            <button
              className={classNames(inputMode === "upload" && "selected")}
              type="button"
              role="tab"
              aria-selected={inputMode === "upload"}
              onClick={() => setInputMode("upload")}
            >
              <UploadCloud size={14} />
              上传 PDF
            </button>
            <button
              className={classNames(inputMode === "local_path" && "selected")}
              type="button"
              role="tab"
              aria-selected={inputMode === "local_path"}
              onClick={() => setInputMode("local_path")}
            >
              <FileText size={14} />
              本机路径
            </button>
          </div>

          {inputMode === "upload" ? (
            <label className="field-stack" htmlFor="pdf-upload" key="pdf-upload-field">
              <span>PDF 文件</span>
              <input
                key="pdf-upload-input"
                ref={uploadRef}
                id="pdf-upload"
                type="file"
                accept="application/pdf,.pdf"
                onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
              />
              <span className="control-hint">{uploadFile ? uploadFile.name : "选择本机 PDF，后端会保存到知识库上传目录。"}</span>
            </label>
          ) : (
            <label className="field-stack" htmlFor="pdf-path" key="pdf-path-field">
              <span>PDF 文件路径</span>
              <input
                key="pdf-path-input"
                ref={pdfPathRef}
                id="pdf-path"
                type="text"
                value={pdfPath}
                maxLength={1200}
                onChange={(event) => setPdfPath(event.target.value)}
                placeholder="D:\\论文\\paper.pdf"
                required
              />
              <span className="control-hint">用于服务器可访问的 PDF 文件路径。</span>
            </label>
          )}

          <div className="parse-action-row">
            <button
              className={classNames("button-primary", parseStatus === "loading" && "is-loading")}
              type="submit"
              disabled={parseButtonDisabled}
              aria-busy={parseStatus === "loading"}
            >
              {parseStatus === "loading" ? "正在解析入库" : "解析并写入知识库"}
            </button>
            {parseMessage ? (
              <span className={classNames("control-feedback", parseStatus === "error" ? "error" : "success")} role={parseStatus === "error" ? "alert" : "status"}>
                {parseMessage}
              </span>
            ) : null}
          </div>
        </form>

        {parseStatus === "loading" ? <SkeletonState title="论文解析进行中" rows={5} /> : null}
        {activeParseRun ? (
          <>
            <ParseRunChecklist run={activeParseRun} onOpenItem={(item) => setSelectedEvidence({ run: activeParseRun, item })} />
            <RagEvidenceSearch
              query={ragQuery}
              status={ragStatus}
              results={ragResults}
              activeRun={activeParseRun}
              onQueryChange={setRagQuery}
              onSubmit={handleRagSearch}
            />
          </>
        ) : (
          <EmptyState
            title="还没有论文解析记录"
            description="上传 PDF 或输入后端可访问路径后，系统会逐项记录解析证据并写入知识库。"
          />
        )}
      </section>

      <section className="data-toolbar">
        <label className="command-input" htmlFor="data-search">
          <Search size={18} />
          <input
            id="data-search"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索论文、解析任务或来源状态"
          />
        </label>
        <div className="segmented-control" role="tablist" aria-label="数据资产类型">
          {filters.map((item) => (
            <button
              className={classNames(filter === item.value && "selected")}
              key={item.value}
              type="button"
              role="tab"
              aria-selected={filter === item.value}
              onClick={() => setFilter(item.value)}
            >
              {item.value === "all" ? <Filter size={14} /> : null}
              {item.label}
            </button>
          ))}
        </div>
      </section>

      <section className="data-summary-grid" aria-label="数据准备摘要">
        <DataMetric icon={Library} label="文献库" value={String(libraries.length)} />
        <DataMetric icon={BookOpen} label="当前库论文" value={String(papers.length)} />
        <DataMetric icon={RefreshCw} label="解析任务" value={String(parseRuns.length)} />
        <DataMetric icon={Layers3} label="知识库片段" value={String(papers.reduce((total, paper) => total + paper.chunks_count, 0))} />
        <DataMetric
          icon={FileCheck2}
          label="实验线索"
          value={String(papers.reduce((total, paper) => total + paper.experimental_chunks_count, 0))}
        />
      </section>

      {dataStatus === "loading" ? <SkeletonState title="正在读取数据资产" rows={4} /> : null}
      {dataStatus === "error" ? (
        <EmptyState title="数据资产暂时不可用" description="请确认数据服务正在运行，然后刷新状态。" />
      ) : null}
      {filteredAssets.length > 0 ? (
        <section className="asset-table-card" aria-label="数据资产列表">
          <div className="asset-table-header">
            <span>资产</span>
            <span>类型</span>
            <span>状态</span>
            <span>覆盖</span>
            <span>更新</span>
          </div>
          {filteredAssets.map((asset) => (
            <button className="asset-row" type="button" key={asset.id} onClick={() => setSelectedAsset(asset)}>
              <span>
                <Database size={16} />
                <strong>{asset.name}</strong>
              </span>
              <span>{assetTypeLabels[asset.type]}</span>
              <span className={classNames("status-pill", asset.tone)}>{asset.status}</span>
              <span>{asset.coverage}</span>
              <span>{asset.updated}</span>
            </button>
          ))}
        </section>
      ) : dataStatus !== "loading" ? (
        <EmptyState title="没有匹配的数据资产" description="调整搜索词或资产类型后再查看。" />
      ) : null}

      {selectedEvidenceSearch ? (
        <div
          className="drawer-backdrop"
          role="presentation"
          onClick={() => setSelectedEvidenceSearch(null)}
        >
          <aside
            ref={drawerRef}
            className="reference-drawer asset-drawer evidence-search-drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="evidence-search-drawer-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="drawer-header">
              <div>
                <span>知识库证据检索</span>
                <h2 id="evidence-search-drawer-title">{selectedEvidenceSearch.paper.title}</h2>
                <p>
                  {selectedEvidenceSearch.paper.chunks_count} 个片段 · {selectedEvidenceSearch.paper.experimental_chunks_count} 个实验线索 ·{" "}
                  {formatBackendText(selectedEvidenceSearch.paper.source_reliability)}
                </p>
              </div>
              <button
                className="drawer-close"
                type="button"
                aria-label="关闭证据检索面板"
                onClick={() => setSelectedEvidenceSearch(null)}
                ref={drawerCloseRef}
              >
                <X size={18} />
              </button>
            </div>
            <div className="asset-detail-stack">
              <article className="status-banner neutral" role="status">
                这里会限定在当前论文解析片段中检索证据。输入假设、术语或实验线索后，结果会显示章节路径、support level 和 source reliability。
              </article>
              <RagEvidenceSearch
                query={ragQuery}
                status={ragStatus}
                results={ragResults}
                activeRun={selectedEvidenceSearch.run}
                onQueryChange={setRagQuery}
                onSubmit={handleRagSearch}
              />
            </div>
          </aside>
        </div>
      ) : null}

      {selectedAsset || selectedEvidence ? (
        <div
          className="drawer-backdrop"
          role="presentation"
          onClick={() => {
            setSelectedAsset(null);
            setSelectedEvidence(null);
          }}
        >
          <aside
            ref={drawerRef}
            className="reference-drawer asset-drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="asset-drawer-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="drawer-header">
              <div>
                <span>{selectedEvidence ? "解析证据" : selectedAsset ? assetTypeLabels[selectedAsset.type] : ""}</span>
                <h2 id="asset-drawer-title">{selectedEvidence ? selectedEvidence.item.label : selectedAsset?.name}</h2>
              </div>
              <button
                className="drawer-close"
                type="button"
                aria-label="关闭数据资产详情"
                onClick={() => {
                  setSelectedAsset(null);
                  setSelectedEvidence(null);
                }}
                ref={drawerCloseRef}
              >
                <X size={18} />
              </button>
            </div>
            {selectedEvidence ? (
              <EvidenceDetail run={selectedEvidence.run} item={selectedEvidence.item} />
            ) : selectedAsset ? (
              <div className="asset-detail-stack">
                <p>{selectedAsset.detail}</p>
                <article className={classNames("status-banner", selectedAsset.tone)} role={selectedAsset.tone === "error" ? "alert" : "status"}>
                  {selectedAsset.status} · {selectedAsset.coverage}
                </article>
                <Link className="button-secondary" to="/data">
                  返回数据列表
                </Link>
              </div>
            ) : null}
          </aside>
        </div>
      ) : null}

      {selectedPdfReader?.pdf_url ? (
        <div className="drawer-backdrop pdf-reader-backdrop" role="presentation" onClick={() => setSelectedPdfReader(null)}>
          <aside
            ref={drawerRef}
            className="pdf-reader-sheet"
            role="dialog"
            aria-modal="true"
            aria-labelledby="pdf-reader-title"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="pdf-reader-header">
              <div>
                <span>PDF 阅读</span>
                <h2 id="pdf-reader-title">{selectedPdfReader.title}</h2>
                <p>
                  {selectedPdfReader.source}
                  {selectedPdfReader.year ? ` · ${selectedPdfReader.year}` : ""}
                </p>
              </div>
              <div className="pdf-reader-actions">
                <a className="button-secondary" href={selectedPdfReader.pdf_url} target="_blank" rel="noreferrer">
                  <ExternalLink size={15} />
                  新窗口打开
                </a>
                <button
                  className={classNames("button-secondary", candidateParseId === selectedPdfReader.candidate_id && "is-loading")}
                  type="button"
                  disabled={candidateParseId === selectedPdfReader.candidate_id}
                  aria-busy={candidateParseId === selectedPdfReader.candidate_id}
                  onClick={() => void handleParseCandidate(selectedPdfReader)}
                >
                  <DownloadCloud size={15} />
                  {candidateParseId === selectedPdfReader.candidate_id ? "解析中" : "加入资料库"}
                </button>
                <button
                  className="drawer-close"
                  type="button"
                  aria-label="关闭 PDF 阅读器"
                  onClick={() => setSelectedPdfReader(null)}
                  ref={drawerCloseRef}
                >
                  <X size={18} />
                </button>
              </div>
            </header>
            <div className="pdf-reader-frame-shell">
              <iframe src={pdfReaderSrc(selectedPdfReader.pdf_url)} title={`阅读 PDF：${selectedPdfReader.title}`} />
            </div>
            <footer className="pdf-reader-footer">
              <article className="status-banner neutral" role="status">
                当前使用浏览器原生 PDF 阅读，便于快速回到候选列表。项目已有 PyMuPDF 解析器负责证据抽取；BabelDOC 适合作为后端长任务生成版式保留的翻译 PDF，不能替代知识库证据链。
              </article>
            </footer>
          </aside>
        </div>
      ) : null}
    </div>
  );
}

function ParseRunChecklist({
  run,
  onOpenItem,
}: {
  run: PaperParseRun;
  onOpenItem: (item: PaperParseItem) => void;
}) {
  return (
    <section className="parse-run-card" aria-label="论文解析项状态">
      <div className="parse-run-header">
        <div>
          <span className={classNames("status-pill", statusTone(run.status))}>{statusLabel(run.status)}</span>
          <h3>{run.title}</h3>
        </div>
        <div className="parse-run-stats">
          <span>{run.page_count ?? 0} 页</span>
          <span>{run.chunks_count} 个知识库片段</span>
          <span>{run.experimental_chunks_count} 个实验线索</span>
        </div>
      </div>
      <div className="parse-item-list">
        {run.items.map((item) => (
          <button className="parse-item-row" type="button" key={item.item_key} onClick={() => onOpenItem(item)}>
            <span className={classNames("quality-lamp", riskLevelForItem(item))} aria-label={riskLabel(riskLevelForItem(item))} />
            <span className={classNames("parse-item-status", item.status)}>
              {item.status === "success" ? <CheckCircle2 size={16} /> : null}
              {item.status === "warning" ? <AlertTriangle size={16} /> : null}
              {item.status === "error" ? <AlertTriangle size={16} /> : null}
              {item.status === "running" ? <Loader2 size={16} className="spin" /> : null}
              {item.status === "pending" ? <Clock3 size={16} /> : null}
            </span>
            <span>
              <strong>{item.label}</strong>
              <small>{displayEvidenceSummary(item.evidence_summary)}</small>
            </span>
            <Eye size={16} />
          </button>
        ))}
      </div>
    </section>
  );
}

function RagEvidenceSearch({
  query,
  status,
  results,
  activeRun,
  onQueryChange,
  onSubmit,
}: {
  query: string;
  status: "idle" | "loading" | "success" | "error";
  results: RagEvidenceResult[];
  activeRun: PaperParseRun;
  onQueryChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const disabled = status === "loading" || !query.trim();
  return (
    <section className="rag-evidence-panel" aria-label="知识库证据检索">
      <div className="section-heading compact">
        <div>
          <h3>知识库证据检索</h3>
          <p>{activeRun.rag_search_ready ? "从当前论文片段中验证可调用证据。" : "当前解析任务尚未进入可检索状态。"}</p>
        </div>
      </div>
      <form className="rag-search-row" onSubmit={onSubmit}>
        <label className="command-input" htmlFor="rag-evidence-query">
          <Search size={16} />
          <input
            id="rag-evidence-query"
            type="search"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="输入要验证的假设、术语或实验线索"
          />
        </label>
        <button className={classNames("button-secondary", status === "loading" && "is-loading")} type="submit" disabled={disabled} aria-busy={status === "loading"}>
          {status === "loading" ? "检索中" : "检索证据"}
        </button>
      </form>
      {status === "error" ? <article className="status-banner error" role="alert">知识库证据暂时不可检索，请确认知识库服务可用。</article> : null}
      {status === "success" && results.length === 0 ? (
        <article className="status-banner warning" role="status">当前论文知识库中没有匹配证据，建议换用更具体的术语或检查解析覆盖。</article>
      ) : null}
      {results.length > 0 ? (
        <div className="rag-result-list">
          {results.map((result, index) => (
            <article className="rag-result-card" key={`${result.title}-${result.section_type}-${index}`}>
              <div>
                <strong>{result.title}</strong>
                <span>{formatSectionType(result.section_type)}</span>
              </div>
              <p>{result.text_preview}</p>
              <footer>
                <span>{formatBackendText(result.support_level)}</span>
                <span>{formatBackendText(result.source_reliability)}</span>
                {result.retrieval_method ? <span>{formatBackendText(result.retrieval_method)}</span> : null}
                {typeof result.vector_similarity === "number" ? <span>向量 {result.vector_similarity.toFixed(2)}</span> : null}
                {typeof result.rerank_score === "number" ? <span>重排 {result.rerank_score.toFixed(2)}</span> : null}
                {result.evidence_id ? <span>已记录证据</span> : null}
              </footer>
              {result.section_path?.length ? (
                <details className="expert-summary">
                  <summary>查看定位信息</summary>
                  <dl className="evidence-detail-list">
                    <div>
                      <dt>章节路径</dt>
                      <dd>{result.section_path.join(" / ")}</dd>
                    </div>
                  </dl>
                </details>
              ) : null}
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function EvidenceDetail({ run, item }: { run: PaperParseRun; item: PaperParseItem }) {
  const evidence = item.evidence;
  const mediaAssets = mediaAssetsFromItem(item);
  const riskLevel = riskLevelForItem(item);
  return (
    <div className="asset-detail-stack">
      <article
        className={classNames("status-banner", item.status === "error" ? "error" : item.status === "warning" ? "warning" : "ok")}
        role={item.status === "error" ? "alert" : "status"}
      >
        <span className={classNames("quality-lamp", riskLevel)} />
        {item.evidence_summary}
      </article>
      <dl className="evidence-detail-list">
        <div>
          <dt>证据类型</dt>
          <dd>{item.evidence_type}</dd>
        </div>
        <div>
          <dt>完成时间</dt>
          <dd>{formatTime(item.completed_at ?? undefined)}</dd>
        </div>
        {evidence?.section_path?.length ? (
          <div>
            <dt>章节路径</dt>
            <dd>{evidence.section_path.join(" / ")}</dd>
          </div>
        ) : null}
      </dl>
      {evidence?.text_preview ? (
        <article className="evidence-preview">
          <strong>文本证据</strong>
          <p>{evidence.text_preview}</p>
        </article>
      ) : null}
      {evidence?.media_preview ? (
        <article className="evidence-preview">
          <strong>媒介证据</strong>
          <p>{evidence.media_preview}</p>
        </article>
      ) : null}
      <details className="expert-summary">
        <summary>查看审计定位</summary>
        <dl className="evidence-detail-list">
          <div>
            <dt>解析任务</dt>
            <dd>{run.parse_run_id}</dd>
          </div>
          {evidence?.file_path ? (
            <div>
              <dt>文件路径</dt>
              <dd>{evidence.file_path}</dd>
            </div>
          ) : null}
          {evidence?.chunk_id ? (
            <div>
              <dt>片段编号</dt>
              <dd>{evidence.chunk_id}</dd>
            </div>
          ) : null}
        </dl>
      </details>
      {mediaAssets.length > 0 ? (
        <article className="evidence-preview">
          <strong>区域质量</strong>
          <div className="media-risk-list">
            {mediaAssets.map((asset, index) => (
              <div className="media-risk-item" key={asset.asset_id ?? `${asset.path}-${index}`}>
                <span className={classNames("quality-lamp", asset.risk_level ?? "ok")} />
                <div>
                  <strong>
                    {asset.kind} · p{asset.page} · {riskLabel(asset.risk_level ?? "ok")}
                  </strong>
                  <p>
                    {asset.width ?? 0}x{asset.height ?? 0}px · {asset.file_size_bytes ?? 0} bytes · confidence{" "}
                    {asset.confidence ?? 1}
                  </p>
                  {asset.risk_flags?.length ? (
                    <ul>
                      {asset.risk_flags.map((flag: PdfRegionRiskFlag) => (
                        <li key={`${asset.asset_id}-${flag.code}`}>
                          {flag.message}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
          <button className="button-secondary" type="button" disabled>
            人工/多模态复核
          </button>
        </article>
      ) : null}
      {item.error_message ? <article className="status-banner error" role="alert">该解析项未完成，请重新解析或检查 PDF 是否可读取。</article> : null}
    </div>
  );
}

function DataMetric({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Database;
  label: string;
  value: string;
}) {
  return (
    <article className="data-metric">
      <Icon size={18} />
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}
