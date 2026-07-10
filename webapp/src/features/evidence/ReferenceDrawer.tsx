import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { classNames, copy } from "../../lib/formatters/workbench";
import type { HypothesisCardViewModel } from "../../types/workbench";
import { SummaryList } from "../../components/surfaces/cards";
import { useDrawerEntranceMotion } from "../../lib/motion/useAnimeEntrance";
import { parseKnowledgePdf } from "../../lib/api/workbench";

function getFocusableElements(container: HTMLElement) {
  return Array.from(
    container.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((element) => !element.hasAttribute("disabled") && element.tabIndex !== -1);
}

export function ReferenceDrawer({
  hypothesis,
  onClose,
}: {
  hypothesis: HypothesisCardViewModel;
  onClose: () => void;
}) {
  const drawerBackdropRef = useRef<HTMLDivElement | null>(null);
  const drawerRef = useRef<HTMLElement | null>(null);
  const drawerCloseRef = useRef<HTMLButtonElement | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const [parsingPdfKey, setParsingPdfKey] = useState<string | null>(null);
  const [parsePdfMessage, setParsePdfMessage] = useState("");
  const [parsePdfStatus, setParsePdfStatus] = useState<"idle" | "success" | "error">("idle");
  useDrawerEntranceMotion(drawerBackdropRef);
  const isDemoGrounding = /演示|模拟|历史合成|暂无真实文献|未查询真实文献/.test(hypothesis.grounding);

  const handleParsePdf = async (candidateKey: string, pdfPath: string) => {
    setParsingPdfKey(candidateKey);
    setParsePdfStatus("idle");
    setParsePdfMessage("");
    try {
      const result = await parseKnowledgePdf({
        pdf_path: pdfPath,
        fetch_metadata: true,
        ingest_to_knowledge_base: true,
      });
      setParsePdfStatus("success");
      setParsePdfMessage(`已解析并写入知识库：${result.title}；生成 ${result.chunks_count} 个层级片段和 ${result.media_assets.length} 个媒体线索。`);
    } catch {
      setParsePdfStatus("error");
      setParsePdfMessage("PDF 暂时无法解析。请确认链接可直接访问 PDF，或在资料管理页使用本机 PDF 路径解析。");
    } finally {
      setParsingPdfKey(null);
    }
  };

  useEffect(() => {
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    drawerCloseRef.current?.focus();
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
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
  }, [onClose]);

  return (
    <div className="drawer-backdrop" onClick={onClose} role="presentation" ref={drawerBackdropRef}>
      <aside
        ref={drawerRef}
        className="reference-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="reference-drawer-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="drawer-header">
          <div>
            <span>参考文献</span>
            <h2 id="reference-drawer-title">{hypothesis.title}</h2>
            <p>{hypothesis.summary}</p>
          </div>
          <button ref={drawerCloseRef} className="drawer-close" type="button" onClick={onClose} aria-label="关闭参考文献">
            <X size={18} />
          </button>
        </header>

        <section className="reference-section">
          <h3>{copy.details.literatureGrounding}</h3>
          <div className="status-badge-row">
            {[...hypothesis.evidenceBadges, ...hypothesis.governanceBadges].map((item) => (
              <span className={classNames("status-pill", item.tone)} key={`${item.label}-${item.tone}`}>
                {item.label}
              </span>
            ))}
          </div>
          <p>{hypothesis.grounding}</p>
        </section>

        <section className="reference-section">
          <h3>{copy.details.citationMap}</h3>
          <p className="reference-range">{hypothesis.referenceRangeLabel}</p>
          <SummaryList items={hypothesis.citations} empty="当前假设暂无可解析参考文献。" />
        </section>

        <section className="reference-section">
          <h3>证据诊断</h3>
          <p className="drawer-note">“引用不一致”指 citation/source claim 与假设 claim 未对齐；“全文不足”指只有摘要、元数据或弱支撑，缺少 parsed fulltext。</p>
          <SummaryList items={hypothesis.evidenceDiagnostics} empty="当前没有显式证据诊断。" />
        </section>

        <section className="reference-section">
          <h3>PDF 解析</h3>
          {hypothesis.citationPdfCandidates.length > 0 ? (
            <div className="pdf-candidate-list">
              {hypothesis.citationPdfCandidates.map((candidate) => (
                <article className="pdf-candidate-row" key={candidate.key}>
                  <div>
                    <strong>{candidate.title}</strong>
                    <span>{candidate.supportLabel}</span>
                  </div>
                  <button
                    className={classNames("button-secondary", parsingPdfKey === candidate.key && "is-loading")}
                    type="button"
                    disabled={Boolean(parsingPdfKey)}
                    aria-busy={parsingPdfKey === candidate.key}
                    onClick={() => void handleParsePdf(candidate.key, candidate.pdfPath)}
                  >
                    {parsingPdfKey === candidate.key ? "正在解析" : "解析 PDF"}
                  </button>
                </article>
              ))}
            </div>
          ) : (
            <p className="drawer-note">当前来源没有可直接解析的 PDF 路径或链接。</p>
          )}
          {parsePdfMessage ? (
            <p className={classNames("control-feedback", parsePdfStatus === "error" ? "error" : "success")} role={parsePdfStatus === "error" ? "alert" : "status"}>
              {parsePdfMessage}
            </p>
          ) : null}
        </section>

        <section className="reference-section">
          <h3>支撑级别</h3>
          <SummaryList items={hypothesis.citationSupportItems} empty="当前来源尚未标注全文、摘要或元数据支撑级别。" />
        </section>

        <section className="reference-section">
          <h3>知识库支撑</h3>
          <SummaryList items={hypothesis.knowledgeSupportItems} empty="当前假设尚未匹配到知识库论文片段。" />
        </section>

        <section className="reference-section">
          <h3>实验数据摘要</h3>
          <SummaryList items={hypothesis.experimentSupportItems} empty="当前假设尚未匹配到论文中的实验数据摘要。" />
        </section>

        {isDemoGrounding ? (
          <p className="drawer-note">当前显示的是历史合成记录保留下来的证据占位；新的研究运行应在实时文献支撑路径下生成真实来源元数据。</p>
        ) : null}
      </aside>
    </div>
  );
}
