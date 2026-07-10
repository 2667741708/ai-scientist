"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  createExperimentPlan,
  getResearchAutopilot,
  listKnowledgePapers,
  pauseResearchAutopilot,
  recordExperimentFeedback,
  resumeResearchAutopilot,
  saveProjectArtifact,
  startResearchAutopilot,
} from "../lib/api/workbench";
import { formatBackendText } from "../lib/formatters/workbench";
import { useWorkbench } from "../features/runs/workbench-context";

const loopStatusLabels = {
  queued: "已排队",
  running: "推进中",
  awaiting_input: "待配置",
  awaiting_approval: "待授权",
  awaiting_human: "待判断",
  reranking: "Elo 重排中",
  paused: "已暂停",
  complete: "已完成",
  error: "需修复",
};

const loopStageLabels = {
  discover: "发现论文",
  acquire_parse: "解析入库",
  ground: "证据定位",
  generate_rank: "假设竞赛",
  plan: "实验预注册",
  execute: "受限执行",
  review: "结果解释",
  rerank: "Elo 重排",
  outcome: "研究结论",
};

const icons = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
  book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z"/>',
  spark: '<path d="m12 3-1.4 3.6A2 2 0 0 1 9.4 7.8L6 9l3.4 1.2a2 2 0 0 1 1.2 1.2L12 15l1.4-3.6a2 2 0 0 1 1.2-1.2L18 9l-3.4-1.2a2 2 0 0 1-1.2-1.2L12 3Z"/><path d="m5 15-.7 1.8a1 1 0 0 1-.6.6L2 18l1.7.6a1 1 0 0 1 .6.6L5 21l.7-1.8a1 1 0 0 1 .6-.6L8 18l-1.7-.6a1 1 0 0 1-.6-.6L5 15Z"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  chevron: '<path d="m9 18 6-6-6-6"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  more: '<circle cx="5" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1" fill="currentColor" stroke="none"/>',
  star: '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-2.9-5.6 2.9 1.1-6.2L3 9.6l6.2-.9L12 3Z"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1.1 1.1"/><path d="M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1.1-1.1"/>',
  filter: '<path d="M4 5h16M7 12h10M10 19h4"/>',
  quote: '<path d="M10 11H5a4 4 0 0 0 4 4v4H5a8 8 0 0 1 0-16h5v8ZM22 11h-5a4 4 0 0 0 4 4v4h-4a8 8 0 0 1 0-16h5v8Z"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  command: '<path d="M18 9a3 3 0 1 0 0-6 3 3 0 0 0-3 3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3V6a3 3 0 1 0-3 3h12Z"/>',
  target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 2v3M22 12h-3"/>',
  layers: '<path d="m12 2 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 17l9 5 9-5"/>',
  note: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6M8 13h8M8 17h5"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
};

function Icon({ name, size = 18, filled = false }) {
  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: icons[name] }}
    />
  );
}

const papers = [
  {
    id: 1,
    title: "Progressive Identification of True Labels for Partial-Label Learning",
    authors: "Lv et al.",
    venue: "JMLR · 2020",
    topic: "PLL",
    state: "已精读",
    progress: 100,
    starred: true,
    note: "从候选标签中逐步识别真实标签，可作为分析 source restoration 的对照路径。",
    tags: ["标签消歧", "理论基础"],
  },
  {
    id: 2,
    title: "Provably Consistent Partial-Label Learning",
    authors: "Feng et al.",
    venue: "NeurIPS · 2020",
    topic: "PLL",
    state: "有批注",
    progress: 78,
    starred: true,
    note: "风险一致性框架；需要和 SRSE 的 active-set objective 明确区分。",
    tags: ["风险一致性", "损失函数"],
  },
  {
    id: 3,
    title: "Learning from Noisy Partial Labels with a Trusted Guidance Set",
    authors: "Xu et al.",
    venue: "AAAI · 2022",
    topic: "NPLL",
    state: "阅读中",
    progress: 46,
    starred: false,
    note: "关注噪声候选集与可信监督之间的关系；可补入 related work 对照表。",
    tags: ["噪声标注", "可信样本"],
  },
  {
    id: 4,
    title: "RT-2: Vision-Language-Action Models Transfer Web Knowledge to Robotic Control",
    authors: "Brohan et al.",
    venue: "CoRL · 2023",
    topic: "VLA",
    state: "待读",
    progress: 12,
    starred: false,
    note: "动作离散化与 token 化为 NPLL × VLA 的联系提供任务接口。",
    tags: ["动作 token", "机器人"],
  },
  {
    id: 5,
    title: "OpenVLA: An Open-Source Vision-Language-Action Model",
    authors: "Kim et al.",
    venue: "CoRL · 2024",
    topic: "VLA",
    state: "待读",
    progress: 8,
    starred: true,
    note: "适合检查动作标签、轨迹噪声和错误动作候选的现实数据形态。",
    tags: ["开源模型", "动作空间"],
  },
];

const generatedHypotheses = [
  {
    id: "H1",
    title: "动作候选集中的真实必要动作假设",
    score: 86,
    text: "将一个时间步的多个可行动作视为候选标签集，其中至少一个动作能推进任务；演示噪声与遥操作冗余会引入错误候选。",
    strength: "与标准 PLL 形式最接近",
    risk: "单步动作未必存在唯一真值",
  },
  {
    id: "H2",
    title: "轨迹片段级噪声部分监督假设",
    score: 92,
    text: "把短轨迹片段而非单个动作作为监督单位，通过任务进展信号恢复可靠片段，再以一致性证据筛选可用于策略更新的 active set。",
    strength: "与 SRSE 的恢复—证据—更新结构一致",
    risk: "需要定义可计算的任务进展信号",
  },
  {
    id: "H3",
    title: "动作 token 的弱监督纠错假设",
    score: 79,
    text: "把离散动作 token 的候选分布看作部分标签，在模型自举训练前先保留来自原始示范的 source support，降低错误伪动作传播。",
    strength: "可直接落到 VLA token 训练接口",
    risk: "连续动作离散化会引入额外误差",
  },
];

function topicForPaper(paper) {
  const text = `${paper.title} ${paper.source} ${paper.section_types?.join(" ") ?? ""}`.toLowerCase();
  if (text.includes("vision-language") || text.includes("vla") || text.includes("robot")) return "VLA";
  if (text.includes("noisy") || text.includes("noise")) return "NPLL";
  if (text.includes("partial")) return "PLL";
  return "论文";
}

function toLatticePaper(paper, index) {
  const topic = topicForPaper(paper);
  const authors = Array.isArray(paper.authors) && paper.authors.length ? paper.authors.join(", ") : "未知作者";
  const chunks = Number(paper.chunks_count ?? 0);
  return {
    id: paper.paper_id,
    title: paper.title || "未命名论文",
    authors,
    venue: [paper.source, paper.year].filter(Boolean).join(" · ") || "已入库文献",
    topic,
    state: chunks > 0 ? "已入库" : "待解析",
    progress: Math.min(100, Math.max(8, chunks > 0 ? 70 : 12)),
    starred: index < 2,
    note: `${formatBackendText(paper.source_reliability || "来源信息有限")}；已建立 ${chunks} 个可检索片段。`,
    tags: [topic, formatBackendText(paper.source_reliability || "来源待核验")],
    url: paper.url || null,
  };
}

function titleForHypothesis(hypothesis, index) {
  const source = String(hypothesis?.text || hypothesis?.explanation || `候选假设 ${index + 1}`).trim();
  const firstSentence = source.split(/[。！？.!?]/)[0].trim();
  return firstSentence.length > 42 ? `${firstSentence.slice(0, 42)}…` : firstSentence;
}

function toLatticeHypothesis(hypothesis, index) {
  const score = Number(hypothesis?.score ?? hypothesis?.elo_rating ?? 0);
  const text = String(hypothesis?.text || hypothesis?.explanation || "暂未返回假设正文。");
  return {
    id: `H${index + 1}`,
    title: titleForHypothesis(hypothesis, index),
    score: Number.isFinite(score) && score > 0 ? Math.min(100, Math.round(score)) : 0,
    text,
    strength: hypothesis?.literature_grounding ? "已返回文献或证据说明" : "需要补充文献证据",
    risk: hypothesis?.experiment ? "已包含验证路径" : "需要补充可证伪实验",
    raw: hypothesis,
    index,
  };
}

function Badge({ children, tone = "neutral" }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

function TopBar({ page, onOpenCommand, onMenu }) {
  const titles = {
    workspace: ["研究工作台", "把今天最重要的研究推进一小步"],
    papers: ["论文库", "阅读、连接并沉淀你的研究证据"],
    hypotheses: ["研究假设生成器", "从问题到可检验假设，再到实验入口"],
  };
  return (
    <header className="topbar">
      <button className="icon-button mobile-menu" onClick={onMenu} aria-label="打开导航">
        <Icon name="menu" />
      </button>
      <div>
        <h1>{titles[page][0]}</h1>
        <p>{titles[page][1]}</p>
      </div>
      <button className="command-button" onClick={onOpenCommand}>
        <Icon name="search" size={17} />
        <span>搜索或跳转</span>
        <kbd>⌘ K</kbd>
      </button>
      <button className="avatar" aria-label="个人设置">研</button>
    </header>
  );
}

function Sidebar({ page, setPage, open, close }) {
  const nav = [
    { id: "workspace", label: "研究工作台", icon: "grid" },
    { id: "papers", label: "论文库", icon: "book", count: 5 },
    { id: "hypotheses", label: "研究假设生成器", icon: "spark", dot: true },
  ];
  return (
    <>
      {open && <button className="nav-scrim" onClick={close} aria-label="关闭导航" />}
      <aside className={`sidebar ${open ? "sidebar-open" : ""}`}>
        <div className="brand">
          <span className="brand-mark"><i /><i /><i /></span>
          <span>Lattice</span>
          <Badge tone="soft">原型</Badge>
        </div>
        <nav className="main-nav" aria-label="主要导航">
          <p className="nav-label">研究空间</p>
          {nav.map((item) => (
            <button
              key={item.id}
              className={page === item.id ? "nav-item active" : "nav-item"}
              onClick={() => { setPage(item.id); close(); }}
            >
              <Icon name={item.icon} size={19} />
              <span>{item.label}</span>
              {item.count && <em>{item.count}</em>}
              {item.dot && <i className="nav-dot" />}
            </button>
          ))}
        </nav>
        <div className="project-switcher">
          <p className="nav-label">当前研究</p>
          <button className="project-card">
            <span className="project-icon">SR</span>
            <span>
              <strong>SRSE / NPLL</strong>
              <small>TNNLS 投稿准备</small>
            </span>
            <Icon name="more" size={17} />
          </button>
        </div>
        <div className="sidebar-footer">
          <div className="sync-line"><span className="sync-dot" />本地更改已保存</div>
          <button className="new-project"><Icon name="plus" size={17} />新建研究项目</button>
        </div>
      </aside>
    </>
  );
}

function Workspace({ completed, setCompleted, setPage, notify }) {
  const tasks = [
    { id: 0, title: "统一 novelty 表述", detail: "区分 risk-level symmetry 与 pointwise symmetric loss", tag: "论文修改" },
    { id: 1, title: "补充超参数设置", detail: "报告各数据集的 μ、ν 与 α", tag: "复现性" },
    { id: 2, title: "验证 NPLL × VLA 假设", detail: "明确动作候选集与真实动作的监督单位", tag: "新方向" },
  ];
  const doneCount = completed.filter(Boolean).length;
  return (
    <div className="workspace-layout page-enter">
      <main className="workspace-main">
        <section className="day-intro">
          <div>
            <Badge tone="green">今日焦点</Badge>
            <h2>把 SRSE 的论证链收紧，<br />再向新假设迈一步。</h2>
          </div>
          <div className="day-progress" aria-label={`今日完成 ${doneCount}/3`}>
            <span>{doneCount}<small>/ 3</small></span>
            <p>今日推进</p>
          </div>
        </section>

        <section className="focus-block">
          <div className="focus-head">
            <div className="eyebrow"><span />正在推进</div>
            <button className="plain-button"><Icon name="more" /></button>
          </div>
          <div className="focus-content">
            <div className="focus-index">01</div>
            <div>
              <h3>收敛 TNNLS 审稿意见回应</h3>
              <p>当前最关键的是准确限定创新性，并把理论约束、代码实现和实验结论对齐。</p>
              <div className="focus-meta">
                <span><Icon name="clock" size={15} /> 预计 45 分钟</span>
                <span><Icon name="note" size={15} /> 8 条意见</span>
              </div>
            </div>
            <button className="primary-button" onClick={() => notify("已进入专注模式 · 45 分钟")}>进入专注模式 <Icon name="arrow" size={17} /></button>
          </div>
          <div className="focus-footer">
            <span>建议下一步</span>
            <p>先重写 novelty 段落，再核对 Table I 与实验设置。</p>
            <button onClick={() => notify("已将建议加入今日任务")}>加入任务</button>
          </div>
        </section>

        <section className="task-section">
          <div className="section-title-row">
            <div>
              <span className="section-kicker">RESEARCH STREAM</span>
              <h3>研究推进流</h3>
            </div>
            <button className="text-button" onClick={() => notify("新任务入口已就绪")}>添加任务 <Icon name="plus" size={16} /></button>
          </div>
          <div className="task-list">
            {tasks.map((task) => (
              <article className={completed[task.id] ? "task-row task-done" : "task-row"} key={task.id}>
                <button
                  className="task-check"
                  aria-label={completed[task.id] ? "标记为未完成" : "标记为已完成"}
                  onClick={() => setCompleted((prev) => prev.map((v, i) => i === task.id ? !v : v))}
                >
                  {completed[task.id] && <Icon name="check" size={15} />}
                </button>
                <div className="task-copy">
                  <strong>{task.title}</strong>
                  <p>{task.detail}</p>
                </div>
                <Badge tone={task.id === 2 ? "violet" : "neutral"}>{task.tag}</Badge>
                <button className="row-arrow" onClick={() => task.id === 2 ? setPage("hypotheses") : notify(`已打开：${task.title}`)}><Icon name="chevron" size={18} /></button>
              </article>
            ))}
          </div>
        </section>

        <section className="continuity-card">
          <div className="continuity-icon"><Icon name="spark" size={22} /></div>
          <div>
            <span>从上次继续</span>
            <h3>NPLL 能否自然连接到 VLA 的动作学习？</h3>
            <p>你已经提出“错误或冗余动作候选”的初始联系。下一步需要确定监督单位和可证伪条件。</p>
          </div>
          <button className="secondary-button" onClick={() => setPage("hypotheses")}>继续推演 <Icon name="arrow" size={17} /></button>
        </section>
      </main>

      <aside className="context-rail">
        <section className="context-section">
          <div className="context-head"><span>当前上下文</span><Badge tone="green">已连接</Badge></div>
          <h3>SRSE 论文修改</h3>
          <p>围绕 active-set objective 与 hard latent eligibility 的表达一致性。</p>
          <div className="context-files">
            <button><Icon name="note" size={17} /><span><strong>main.tex</strong><small>主文件 · 刚刚更新</small></span></button>
            <button><Icon name="book" size={17} /><span><strong>审稿意见</strong><small>8 条待回应</small></span></button>
          </div>
        </section>
        <section className="evidence-mini">
          <div className="context-head"><span>证据线索</span><button onClick={() => setPage("papers")}>查看全部</button></div>
          <article>
            <span className="paper-number">01</span>
            <div><h4>Provably Consistent PLL</h4><p>风险一致性 · NeurIPS 2020</p></div>
          </article>
          <article>
            <span className="paper-number">02</span>
            <div><h4>Symmetric Losses</h4><p>损失对称性 · 理论对照</p></div>
          </article>
        </section>
        <section className="insight-note">
          <Icon name="quote" size={18} />
          <p>“不要把方法包装成 EM；准确表述为 hard latent-eligibility extraction followed by supervised update。”</p>
          <span>研究备忘 · 6 月 18 日</span>
        </section>
      </aside>
    </div>
  );
}

function PaperLibrary({ selectedPaper, setSelectedPaper, notify }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("全部");
  const [livePapers, setLivePapers] = useState([]);
  const [paperState, setPaperState] = useState("loading");
  const [favorites, setFavorites] = useState(() => new Set());
  useEffect(() => {
    let mounted = true;
    listKnowledgePapers()
      .then((result) => {
        if (!mounted) return;
        setLivePapers((result.papers ?? []).map(toLatticePaper));
        setPaperState("ready");
      })
      .catch(() => {
        if (!mounted) return;
        setPaperState("error");
      });
    return () => { mounted = false; };
  }, []);
  useEffect(() => {
    if (!selectedPaper && livePapers[0]) setSelectedPaper(livePapers[0].id);
  }, [livePapers, selectedPaper, setSelectedPaper]);
  const filtered = useMemo(() => livePapers.filter((paper) => {
    const textMatch = `${paper.title} ${paper.authors} ${paper.topic}`.toLowerCase().includes(query.toLowerCase());
    const filterMatch = filter === "全部" || (filter === "已收藏" ? favorites.has(paper.id) : paper.topic === filter);
    return textMatch && filterMatch;
  }), [query, filter, favorites, livePapers]);
  const active = livePapers.find((paper) => paper.id === selectedPaper) || livePapers[0];
  function toggleFavorite(id) {
    setFavorites((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }
  return (
    <div className="library-layout page-enter">
      <main className="library-main">
        <section className="library-intro">
          <div><span className="section-kicker">KNOWLEDGE BASE</span><h2>让每篇论文都进入论证链。</h2></div>
          <button className="primary-button" onClick={() => notify("论文导入入口已就绪")}><Icon name="plus" size={17} /> 导入论文</button>
        </section>
        <div className="library-toolbar">
          <label className="search-field"><Icon name="search" size={17} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索标题、作者或主题…" /></label>
          <div className="filter-tabs">
            {["全部", "NPLL", "PLL", "VLA", "已收藏"].map((item) => <button key={item} onClick={() => setFilter(item)} className={filter === item ? "active" : ""}>{item}</button>)}
          </div>
          <button className="icon-button"><Icon name="filter" size={18} /></button>
        </div>
        <div className="paper-table-head"><span>论文</span><span>主题</span><span>阅读状态</span><span>操作</span></div>
        <div className="paper-list">
          {filtered.map((paper) => (
            <article key={paper.id} className={selectedPaper === paper.id ? "paper-row selected" : "paper-row"} onClick={() => setSelectedPaper(paper.id)}>
              <div className="paper-title-cell">
                <button className={favorites.has(paper.id) ? "star-button active" : "star-button"} onClick={(e) => { e.stopPropagation(); toggleFavorite(paper.id); }} aria-label="收藏论文"><Icon name="star" size={17} filled={favorites.has(paper.id)} /></button>
                <div><h3>{paper.title}</h3><p>{paper.authors} · {paper.venue}</p></div>
              </div>
              <div><Badge tone={paper.topic === "VLA" ? "violet" : paper.topic === "NPLL" ? "green" : "neutral"}>{paper.topic}</Badge></div>
              <div className="reading-state"><span><i style={{ width: `${paper.progress}%` }} /></span><small>{paper.state}</small></div>
              <button className="row-arrow"><Icon name="chevron" size={18} /></button>
            </article>
          ))}
          {!filtered.length && <div className="empty-state"><Icon name="search" size={24} /><h3>{paperState === "loading" ? "正在读取论文库" : "没有匹配的论文"}</h3><p>{paperState === "error" ? "论文库暂时不可用，请稍后重试。" : "换一个关键词或筛选条件试试。"}</p></div>}
        </div>
      </main>
      <aside className="paper-detail">
        {active ? <>
          <div className="detail-top"><Badge tone={active.topic === "VLA" ? "violet" : "green"}>{active.topic}</Badge><button className="icon-button"><Icon name="more" /></button></div>
          <h2>{active.title}</h2>
          <p className="detail-authors">{active.authors}<br />{active.venue}</p>
          <div className="detail-actions"><button className="secondary-button" onClick={() => active.url ? window.open(active.url, "_blank", "noopener,noreferrer") : notify("当前论文没有可打开的来源链接")}><Icon name="book" size={17} /> 打开阅读</button><button className="icon-button" onClick={() => active.url ? window.open(active.url, "_blank", "noopener,noreferrer") : notify("当前论文没有可复制的来源链接")}><Icon name="link" size={17} /></button></div>
          <div className="detail-divider" />
          <section><span className="section-kicker">MY NOTE</span><p className="paper-note">{active.note}</p></section>
          <section><span className="section-kicker">RESEARCH LINKS</span><div className="tag-cloud">{active.tags.map((tag) => <span key={tag}>{tag}</span>)}</div></section>
          <section className="claim-card"><span>关联论点</span><h4>把已入库文献放进可追溯证据链</h4><p>这篇论文可作为候选假设的支撑、反例或实验设计来源。</p><button onClick={() => notify("请在假设生成器中选择候选假设后加入证据链")}>查看证据链 <Icon name="plus" size={15} /></button></section>
        </> : null}
      </aside>
    </div>
  );
}

function HypothesisLab({ notify, workbench }) {
  const { goal: question, setGoal: setQuestion, currentRun, isBusy, startRun, runBlocked } = workbench;
  const [sources, setSources] = useState(["论文库", "研究备忘"]);
  const [activeId, setActiveId] = useState("H2");
  const [saved, setSaved] = useState([]);
  const [loopState, setLoopState] = useState(currentRun?.research_loop || null);
  const [loopBusy, setLoopBusy] = useState(false);
  const [loopConfigOpen, setLoopConfigOpen] = useState(false);
  const [computeKind, setComputeKind] = useState("local_python");
  const [scriptPath, setScriptPath] = useState("");
  const [serverId, setServerId] = useState("c201-4090");
  const [remoteCommand, setRemoteCommand] = useState("");
  const [remoteWorkdir, setRemoteWorkdir] = useState("");
  const [metricPath, setMetricPath] = useState("metrics.primary");
  const [metricOperator, setMetricOperator] = useState(">=");
  const [metricThreshold, setMetricThreshold] = useState("");
  const [autoInterpret, setAutoInterpret] = useState(false);
  const [autoRerank, setAutoRerank] = useState(true);
  const toggleSource = (source) => setSources((prev) => prev.includes(source) ? prev.filter((s) => s !== source) : [...prev, source]);
  const liveHypotheses = useMemo(
    () => (currentRun?.hypotheses ?? []).map(toLatticeHypothesis),
    [currentRun],
  );
  const generated = liveHypotheses.length > 0;
  const loading = isBusy;
  const active = liveHypotheses.find((hypothesis) => hypothesis.id === activeId) || liveHypotheses[0];
  const loopNeedsConfig = ["awaiting_input", "awaiting_approval", "paused", "error"].includes(loopState?.status);
  const loopWinner = Number.isInteger(loopState?.selected_hypothesis_index)
    ? liveHypotheses[loopState.selected_hypothesis_index]
    : null;

  useEffect(() => {
    if (liveHypotheses[0] && !liveHypotheses.some((hypothesis) => hypothesis.id === activeId)) {
      setActiveId(liveHypotheses[0].id);
    }
  }, [activeId, liveHypotheses]);
  useEffect(() => {
    setLoopState(currentRun?.research_loop || null);
  }, [currentRun?.research_loop]);
  useEffect(() => {
    if (loopNeedsConfig) setLoopConfigOpen(true);
  }, [loopNeedsConfig]);
  useEffect(() => {
    if (!currentRun || !["queued", "running", "reranking"].includes(loopState?.status)) return undefined;
    let cancelled = false;
    const refresh = async () => {
      try {
        const response = await getResearchAutopilot(currentRun.run_id);
        if (!cancelled) setLoopState(response.research_loop);
      } catch {
        // Keep the last durable snapshot visible; the next interval can recover.
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 1200);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [currentRun?.run_id, loopState?.status]);

  async function generate() {
    const runId = await startRun(question);
    if (runId) notify("研究运行已启动，正在连接论文、证据与候选假设。");
    else if (runBlocked) notify("运行条件尚未就绪，请检查模型和文献服务。 ");
  }

  async function saveHypothesis(hypothesis) {
    if (!currentRun) {
      notify("请先完成一次研究运行，再保存候选假设。");
      return;
    }
    try {
      await saveProjectArtifact({
        project_id: currentRun.run_id,
        run_id: currentRun.run_id,
        artifact_type: "hypothesis",
        target_ref: { hypothesis_index: hypothesis.index, hypothesis_id: hypothesis.id },
        title: hypothesis.title,
        payload: hypothesis.raw,
      });
      setSaved((previous) => previous.includes(hypothesis.id) ? previous : [...previous, hypothesis.id]);
      notify(`已保存假设 ${hypothesis.id} 到项目。`);
    } catch {
      notify("保存失败，请稍后重试。 ");
    }
  }

  async function createExperiment() {
    if (!currentRun || !active) {
      notify("请选择已完成运行中的候选假设。 ");
      return;
    }
    try {
      await createExperimentPlan(currentRun.run_id, currentRun.run_id, active.index);
      notify("可证伪实验计划已创建并保存到项目。 ");
    } catch {
      notify("实验计划暂时无法创建，请稍后重试。 ");
    }
  }

  async function toggleResearchLoop() {
    if (!currentRun) return;
    if (loopState?.status === "complete") {
      notify("这个闭环已经完成；可从获胜结果创建下一次 continuation run。");
      return;
    }
    if (loopState && !["queued", "running"].includes(loopState.status)) {
      setLoopConfigOpen(true);
      notify(loopState.status === "awaiting_human" ? "请确认实验解释或检查不确定执行。" : "补充计算目标、指标和限定授权后即可恢复。 ");
      return;
    }
    setLoopBusy(true);
    try {
      if (["queued", "running"].includes(loopState?.status)) {
        const response = await pauseResearchAutopilot(currentRun.run_id);
        setLoopState(response.research_loop);
        notify("自动闭环已暂停；已经开始的远程命令不会被强制终止。");
      } else {
        const response = await startResearchAutopilot(currentRun.run_id, {
          mode: "guarded",
          auto_evidence: true,
          auto_plan: true,
          auto_execute: false,
          auto_interpret: false,
          auto_rerank: true,
          continue_on_limited_evidence: true,
          grants: [{ confirmed: true, scope: "mcp.literature_review", reason: "Researcher started the guarded evidence expansion loop.", max_uses: 1 }],
        });
        setLoopState(response.research_loop);
        notify("已创建可恢复的研究闭环；安全步骤会自动推进，高风险节点会等待你。 ");
      }
    } catch {
      notify("闭环状态暂时无法更新，请查看任务状态或稍后重试。 ");
    } finally {
      setLoopBusy(false);
    }
  }

  async function resumeResearchLoop() {
    if (!currentRun) return;
    const threshold = Number(metricThreshold);
    if (!metricThreshold.trim() || !Number.isFinite(threshold)) {
      notify("请填写有限数值形式的预注册阈值。 ");
      return;
    }
    if (computeKind === "local_python" && !scriptPath.trim()) {
      notify("请填写实验根目录内的 Python 脚本路径。 ");
      return;
    }
    if (computeKind === "ssh" && (!serverId.trim() || !remoteCommand.trim())) {
      notify("请选择登记服务器并填写不含密码或 token 的远程命令。 ");
      return;
    }
    const executionScope = computeKind === "ssh" ? "ssh.training_command" : "experiment.background_job";
    const compute = computeKind === "ssh"
      ? { kind: "ssh", server_id: serverId.trim(), command: remoteCommand.trim(), workdir: remoteWorkdir.trim() || undefined, timeout_seconds: 3600 }
      : { kind: "local_python", script_path: scriptPath.trim(), timeout_seconds: 300 };
    const grants = [{
      confirmed: true,
      scope: executionScope,
      server_id: computeKind === "ssh" ? serverId.trim() : undefined,
      reason: "Researcher explicitly approved this preregistered compute target in Lattice.",
      max_uses: 1,
    }];
    if (autoInterpret) grants.push({
      confirmed: true,
      scope: "experiment.feedback",
      reason: "Researcher approved deterministic adoption of the preregistered metric comparison.",
      max_uses: 1,
    });
    setLoopBusy(true);
    try {
      const response = await resumeResearchAutopilot(currentRun.run_id, {
        compute,
        evaluation: { metric_path: metricPath.trim() || "metrics.primary", operator: metricOperator, threshold },
        grants,
        continue_on_limited_evidence: true,
        auto_interpret: autoInterpret,
        auto_rerank: autoRerank,
      });
      setLoopState(response.research_loop);
      setLoopConfigOpen(false);
      notify("限定授权已记录；闭环将从持久化检查点继续。 ");
    } catch {
      notify("恢复失败：请检查脚本、服务器、命令和当前任务状态。 ");
    } finally {
      setLoopBusy(false);
    }
  }

  async function confirmExperimentVerdict(verdict) {
    if (!currentRun || loopState?.current_stage !== "review") return;
    const jobId = loopState?.execution?.job_id;
    const hypothesisIndex = loopState?.selected_hypothesis_index;
    if (!jobId || !Number.isInteger(hypothesisIndex)) {
      notify("没有找到可解释的实验执行引用。 ");
      return;
    }
    setLoopBusy(true);
    try {
      await recordExperimentFeedback(currentRun.run_id, {
        job_id: jobId,
        hypothesis_index: hypothesisIndex,
        verdict,
        rationale: `Researcher reviewed the persisted experiment result in Lattice and marked it ${verdict}.`,
        rerank: true,
        approval: { confirmed: true, scope: "experiment.feedback", reason: "Explicit researcher interpretation in Lattice." },
      });
      const response = await getResearchAutopilot(currentRun.run_id);
      setLoopState(response.research_loop);
      notify("研究者解释已写回证据包，并进入 Review / Elo 重排。 ");
    } catch {
      notify("实验解释未能写回；请检查任务是否终态以及假设绑定。 ");
    } finally {
      setLoopBusy(false);
    }
  }
  return (
    <div className="hypothesis-layout page-enter">
      <main className="hypothesis-main">
        <section className="hypothesis-hero">
          <div className="hypothesis-orbit"><span>H</span><i /><i /></div>
          <div><Badge tone="violet">假设实验室</Badge><h2>把一个模糊的联系，<br />变成可检验的研究假设。</h2><p>先保留原始问题，再用你的论文、备忘与约束条件生成候选假设。</p></div>
        </section>
        <section className="prompt-composer">
          <label htmlFor="question">研究问题</label>
          <textarea id="question" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="写下希望检验的研究问题、变量和失败条件…" />
          <div className="composer-controls">
            <div className="source-toggles">
              {["论文库", "研究备忘", "代码实现"].map((source) => <button key={source} className={sources.includes(source) ? "active" : ""} onClick={() => toggleSource(source)}><span>{sources.includes(source) && <Icon name="check" size={13} />}</span>{source}</button>)}
            </div>
            <button className="generate-button" disabled={loading || !question.trim() || runBlocked} onClick={() => void generate()}>{loading ? <><i className="spinner" />正在推演</> : <><Icon name="spark" size={17} />生成候选假设</>}</button>
          </div>
        </section>
        {!generated && !loading && (
          <section className="hypothesis-empty">
            <div className="logic-path"><span>研究问题</span><Icon name="arrow" /><span>监督单位</span><Icon name="arrow" /><span>可证伪假设</span></div>
            <p>生成后会得到候选假设、成立条件、风险与可执行的最小实验。</p>
          </section>
        )}
        {loading && <section className="thinking-state"><div><i /><i /><i /></div><h3>正在连接概念与证据…</h3><p>检查 NPLL 监督结构、VLA 动作表示和 SRSE 可靠性筛选。</p></section>}
        {generated && (
          <section className="hypothesis-results">
            <div className="section-title-row"><div><span className="section-kicker">3 CANDIDATES</span><h3>候选假设</h3></div><span className="result-note">按可检验性排序</span></div>
            <div className="hypothesis-cards">
              {liveHypotheses.map((hypothesis) => (
                <article key={hypothesis.id} className={activeId === hypothesis.id ? "hypothesis-card active" : "hypothesis-card"} onClick={() => setActiveId(hypothesis.id)}>
                  <div className="hypothesis-card-top"><span>{hypothesis.id}</span><strong>{hypothesis.score}<small>/100</small></strong></div>
                  <h3>{hypothesis.title}</h3><p>{hypothesis.text}</p>
                  <div className="hypothesis-signals"><span><i className="positive" />{hypothesis.strength}</span><span><i className="risk" />{hypothesis.risk}</span></div>
                  <button className={saved.includes(hypothesis.id) ? "save-hypothesis saved" : "save-hypothesis"} onClick={(e) => { e.stopPropagation(); void saveHypothesis(hypothesis); }}>{saved.includes(hypothesis.id) ? <><Icon name="check" size={16} />已保存</> : <>保存到项目<Icon name="plus" size={16} /></>}</button>
                </article>
              ))}
            </div>
          </section>
        )}
      </main>
      <aside className="hypothesis-rail">
        <div className="context-head"><span>检验框架</span><Badge tone={generated ? "green" : "neutral"}>{generated ? activeId : "待生成"}</Badge></div>
        {generated ? (
          <>
            <h3>{active.title}</h3>
            <div className="framework-step"><span>01</span><div><strong>候选命题</strong><p>{active.text}</p></div></div>
            <div className="framework-step"><span>02</span><div><strong>文献与证据</strong><p>{active.raw.literature_grounding || "当前输出没有足够的文献支撑；不要把它视为已证实结论。"}</p></div></div>
            <div className="framework-step"><span>03</span><div><strong>最小实验</strong><p>{active.raw.experiment || "需要生成可观测变量、对照组与最小验证路径。"}</p></div></div>
            <div className="framework-step"><span>04</span><div><strong>证伪条件</strong><p>若关键观测变量在对照条件下不优于替代解释，则应拒绝或修订该假设。</p></div></div>
            <button className="primary-button full" onClick={() => void createExperiment()}>创建最小实验 <Icon name="arrow" size={17} /></button>
            <section className="autopilot-card">
              <div className="autopilot-head"><span><Icon name="layers" size={15} />RESEARCH AUTOPILOT</span><Badge tone={loopState?.status === "complete" ? "green" : loopState?.status === "error" ? "amber" : loopState?.status ? "violet" : "neutral"}>{loopStatusLabels[loopState?.status] || "未启动"}</Badge></div>
              <p>检索与解析、证据核验、实验协议、受限计算、结果解释和 Elo 重排共用一条可恢复任务链。</p>
              {loopWinner ? <div className="autopilot-winner"><span>当前闭环对象</span><strong>{loopWinner.id} · {loopWinner.title}</strong></div> : null}
              {loopState?.stages?.length ? <div className="autopilot-stages">{loopState.stages.map((stage) => <span key={stage.id} className={`${stage.status === "complete" ? "done" : ""} ${stage.id === loopState.current_stage ? "active" : ""} ${["limited", "error", "awaiting_human", "awaiting_input", "awaiting_approval"].includes(stage.status) ? "attention" : ""}`} title={stage.summary || stage.message || stage.status}><i />{loopStageLabels[stage.id] || stage.label || stage.id}</span>)}</div> : null}
              {loopState?.current_stage ? <div className="autopilot-current"><span>{loopStageLabels[loopState.current_stage] || loopState.current_stage}</span><p>{loopState.stages?.find((stage) => stage.id === loopState.current_stage)?.summary || loopState.stages?.find((stage) => stage.id === loopState.current_stage)?.message || "正在等待持久化任务更新。"}</p></div> : null}
              {loopState?.status === "awaiting_human" && loopState?.current_stage === "review" ? (
                <div className="autopilot-review">
                  <strong>研究者解释</strong>
                  <p>{loopState?.interpretation?.rationale || "请检查指标、日志和反例，再决定实验与假设的关系。"}</p>
                  <div><button type="button" disabled={loopBusy} onClick={() => void confirmExperimentVerdict("support")}>支持</button><button type="button" disabled={loopBusy} onClick={() => void confirmExperimentVerdict("contradict")}>反驳</button><button type="button" disabled={loopBusy} onClick={() => void confirmExperimentVerdict("inconclusive")}>不足</button></div>
                </div>
              ) : null}
              {loopConfigOpen && loopState?.status !== "awaiting_human" ? (
                <div className="autopilot-config">
                  <div className="autopilot-config-head"><strong>恢复检查点</strong><button type="button" onClick={() => setLoopConfigOpen(false)}>收起</button></div>
                  <label>计算目标<select value={computeKind} onChange={(event) => setComputeKind(event.target.value)}><option value="local_python">受限本地 Python</option><option value="ssh">登记 SSH 服务器</option></select></label>
                  {computeKind === "local_python" ? <label>脚本路径<input value={scriptPath} onChange={(event) => setScriptPath(event.target.value)} placeholder="benchmark.py（相对 .experiments）" /></label> : <><label>服务器<select value={serverId} onChange={(event) => setServerId(event.target.value)}><option value="c201-4090">c201-4090</option><option value="c201-5080">c201-5080</option><option value="d437">d437</option></select></label><label>工作目录<input value={remoteWorkdir} onChange={(event) => setRemoteWorkdir(event.target.value)} placeholder="服务器已配置目录" /></label><label>远程命令<textarea value={remoteCommand} onChange={(event) => setRemoteCommand(event.target.value)} placeholder="python train.py --config experiment.yaml" /></label><small className="config-warning">不要在命令中粘贴密码、token 或 API key；凭据应预先配置在服务器。</small></>}
                  <div className="metric-grid"><label>指标路径<input value={metricPath} onChange={(event) => setMetricPath(event.target.value)} /></label><label>比较<select value={metricOperator} onChange={(event) => setMetricOperator(event.target.value)}><option>&gt;=</option><option>&gt;</option><option>&lt;=</option><option>&lt;</option><option>==</option><option>!=</option></select></label><label>阈值<input inputMode="decimal" value={metricThreshold} onChange={(event) => setMetricThreshold(event.target.value)} placeholder="0.80" /></label></div>
                  <label className="autopilot-check"><input type="checkbox" checked={autoInterpret} onChange={(event) => setAutoInterpret(event.target.checked)} /><span>指标满足预注册规则时自动写回证据</span></label>
                  <label className="autopilot-check"><input type="checkbox" checked={autoRerank} onChange={(event) => setAutoRerank(event.target.checked)} /><span>写回后自动进入 Review / Elo 重排</span></label>
                  <button className="primary-button full" type="button" disabled={loopBusy} onClick={() => void resumeResearchLoop()}>{loopBusy ? "正在恢复" : computeKind === "ssh" ? "授权此服务器并继续" : "授权此脚本并继续"}</button>
                </div>
              ) : null}
              <button className="secondary-button full" type="button" disabled={loopBusy || ["complete", "reranking", "awaiting_human"].includes(loopState?.status)} onClick={() => void toggleResearchLoop()}>{loopBusy ? "正在更新" : ["queued", "running"].includes(loopState?.status) ? "暂停自动推进" : loopState?.status === "complete" ? "闭环已完成" : loopState?.status === "reranking" ? "正在重排" : loopState?.status === "awaiting_human" ? "等待人工核验" : loopState ? "配置并恢复" : "启动受控闭环"}</button>
              <small>检索、解析和整理可按任务授权自动推进；远程执行、缺失阈值、不确定结果和命题 lineage 会停在可恢复检查点。</small>
            </section>
          </>
        ) : (
          <div className="rail-placeholder"><Icon name="target" size={25} /><h3>这里会出现检验路径</h3><p>选择一个候选假设后，系统会展开监督单位、实验变量与证伪条件。</p></div>
        )}
        <div className="rail-principle"><Icon name="layers" size={18} /><div><strong>SRSE 迁移原则</strong><p>source restoration → dual evidence → active-set update</p></div></div>
      </aside>
    </div>
  );
}

function CommandPalette({ open, close, setPage }) {
  const input = useRef(null);
  useEffect(() => { if (open) window.setTimeout(() => input.current?.focus(), 20); }, [open]);
  if (!open) return null;
  const actions = [
    ["workspace", "grid", "跳转到研究工作台", "G W"],
    ["papers", "book", "打开论文库", "G P"],
    ["hypotheses", "spark", "生成新的研究假设", "G H"],
  ];
  return (
    <div className="modal-backdrop" onMouseDown={close}>
      <div className="command-palette" onMouseDown={(e) => e.stopPropagation()}>
        <div className="command-input"><Icon name="search" /><input ref={input} placeholder="搜索论文、任务或功能…" /><button onClick={close}>ESC</button></div>
        <div className="command-group"><span>快速跳转</span>{actions.map(([id, icon, label, shortcut]) => <button key={id} onClick={() => { setPage(id); close(); }}><Icon name={icon} size={18} /><strong>{label}</strong><kbd>{shortcut}</kbd></button>)}</div>
        <div className="command-footer"><span><Icon name="command" size={14} /> 输入关键词即可开始</span><span>↑↓ 选择 · ↵ 打开</span></div>
      </div>
    </div>
  );
}

export default function Home() {
  const workbench = useWorkbench();
  const [page, setPage] = useState("workspace");
  const [completed, setCompleted] = useState([false, false, false]);
  const [selectedPaper, setSelectedPaper] = useState("");
  const [commandOpen, setCommandOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [toast, setToast] = useState("");
  useEffect(() => {
    const saved = window.localStorage.getItem("lattice-tasks");
    if (saved) setCompleted(JSON.parse(saved));
  }, []);
  useEffect(() => {
    if (!workbench.goal.trim()) {
      workbench.setGoal("如何把含噪声的部分标签学习与 VLA 的动作学习建立可检验的联系？");
    }
  }, [workbench]);
  useEffect(() => { window.localStorage.setItem("lattice-tasks", JSON.stringify(completed)); }, [completed]);
  useEffect(() => {
    const handler = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setCommandOpen(true); }
      if (event.key === "Escape") setCommandOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  function notify(message) {
    setToast(message);
    window.setTimeout(() => setToast(""), 2600);
  }
  return (
    <div className="app-shell">
      <Sidebar page={page} setPage={setPage} open={navOpen} close={() => setNavOpen(false)} />
      <div className="app-content">
        <TopBar page={page} onOpenCommand={() => setCommandOpen(true)} onMenu={() => setNavOpen(true)} />
        {page === "workspace" && <Workspace completed={completed} setCompleted={setCompleted} setPage={setPage} notify={notify} />}
        {page === "papers" && <PaperLibrary selectedPaper={selectedPaper} setSelectedPaper={setSelectedPaper} notify={notify} />}
        {page === "hypotheses" && <HypothesisLab notify={notify} workbench={workbench} />}
      </div>
      <CommandPalette open={commandOpen} close={() => setCommandOpen(false)} setPage={setPage} />
      <div className={toast ? "toast show" : "toast"}><span><Icon name="check" size={15} /></span>{toast}</div>
    </div>
  );
}
