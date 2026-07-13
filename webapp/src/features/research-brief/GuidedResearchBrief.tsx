import { CheckCircle2, Loader2, MessageSquareText, PencilLine, Send, Sparkles } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { sendResearchChatTurn } from "../../lib/api/researchChat";

type Brief = {
  question: string;
  scope: string;
  evidenceMinimum: number;
  computeBudget: string;
  experimentScale: string;
  requirements: string[];
};

type Message = { role: "user" | "assistant"; text: string };

const defaultRequirements = [
  "只使用项目论文库和可验证公开文献。",
  "每个候选假设至少关联 3 条证据。",
  "明确支持、反对和证据不足的来源。",
  "每个假设必须提供可证伪条件。",
  "不允许把摘要级内容标记为全文证据。",
  "输出最小可行实验，而不是直接训练大型模型。",
];

function draftFromConversation(messages: Message[]): Brief {
  const userText = messages.filter((message) => message.role === "user").map((message) => message.text.trim()).filter(Boolean).join("；");
  const topic = userText || "请描述你正在关注的现象、方法或研究困难";
  return {
    question: topic.endsWith("？") || topic.endsWith("?") ? topic : `${topic}，在什么条件下能够形成可验证的性能改进？`,
    scope: "围绕核心机制、适用条件、对照方法与失败边界形成可检验假设。",
    evidenceMinimum: 3,
    computeBudget: /3080|10gb/i.test(userText) ? "单张 RTX 3080 10GB" : "单张消费级 GPU；具体型号待确认",
    experimentScale: "先完成最小可行实验，再决定是否扩大训练规模。",
    requirements: [...defaultRequirements],
  };
}

export function GuidedResearchBrief({
  disabled,
  onSubmit,
}: {
  disabled: boolean;
  onSubmit: (goal: string) => Promise<void>;
}) {
  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", text: "先不用填写完整表单。告诉我你正在研究什么、发现了什么问题，或者只有一个模糊想法也可以。" },
  ]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string>();
  const [thinking, setThinking] = useState(false);
  const [brief, setBrief] = useState<Brief | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const userTurns = useMemo(() => messages.filter((message) => message.role === "user").length, [messages]);

  const send = async (event: FormEvent) => {
    event.preventDefault();
    const text = input.trim();
    if (!text || thinking) return;
    const nextMessages: Message[] = [...messages, { role: "user", text }];
    setMessages(nextMessages);
    setInput("");
    setThinking(true);
    try {
      const response = await sendResearchChatTurn({
        session_id: sessionId,
        message: `我们只是在共同澄清一个研究主题，暂时不要启动任务或执行工具。请根据下面这条信息指出还缺少的一个最关键条件，并只问一个简短问题：${text}`,
        context: { page: "research_brief", mode: "project_help", language: "zh" },
      });
      setSessionId(response.session_id);
      setMessages([...nextMessages, { role: "assistant", text: response.assistant_message.text }]);
    } catch {
      const fallback = userTurns === 0
        ? "这个方向最希望改善什么结果？请给出一个主要指标或可观察现象。"
        : userTurns === 1
          ? "你希望在哪些数据、对象或应用场景中验证它？"
          : "有什么计算预算、证据来源或实验规模限制？";
      setMessages([...nextMessages, { role: "assistant", text: fallback }]);
    } finally {
      setThinking(false);
    }
  };

  const generateBrief = () => setBrief(draftFromConversation(messages));
  const updateRequirement = (index: number, value: string) => {
    setBrief((current) => current ? { ...current, requirements: current.requirements.map((item, itemIndex) => itemIndex === index ? value : item) } : current);
  };
  const addRequirement = () => setBrief((current) => current ? { ...current, requirements: [...current.requirements, ""] } : current);
  const submit = async () => {
    if (!brief || disabled || submitting) return;
    setSubmitting(true);
    try {
      const goal = [
        `研究问题：\n${brief.question}`,
        `研究范围：\n${brief.scope}`,
        `实验预算：\n${brief.computeBudget}`,
        `实验规模：\n${brief.experimentScale}`,
        `要求：\n${brief.requirements.filter(Boolean).map((item, index) => `${index + 1}. ${item}`).join("\n")}`,
      ].join("\n\n");
      await onSubmit(goal);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="guided-brief">
      <div className="guided-brief-heading">
        <div><span>GUIDED RESEARCH BRIEF</span><h2>和 AI 讨论，再生成研究任务</h2><p>可以从一句模糊想法开始。生成的模板只是草稿，提交前每一项都能修改。</p></div>
        <div className="guided-stage"><span className={!brief ? "active" : "done"}>1 讨论主题</span><i /><span className={brief ? "active" : ""}>2 审查模板</span><i /><span>3 确认提交</span></div>
      </div>
      <div className="guided-brief-grid">
        <div className="guided-chat">
          <div className="guided-chat-log">
            {messages.map((message, index) => <article className={message.role} key={`${message.role}-${index}`}><span>{message.role === "assistant" ? <Sparkles size={14} /> : "你"}</span><p>{message.text}</p></article>)}
            {thinking ? <article className="assistant"><span><Loader2 className="spin" size={14} /></span><p>正在整理你的研究意图…</p></article> : null}
          </div>
          <form className="guided-chat-composer" onSubmit={send}><textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder="例如：我想把含噪声部分标签学习与 VLA 的关键动作轨迹联系起来…" rows={3}/><div><small>不需要一次说完整，AI 会继续追问关键条件。</small><button className="button-secondary" disabled={!input.trim() || thinking}><Send size={14}/>发送</button></div></form>
          <button className="button-primary guided-generate" type="button" onClick={generateBrief} disabled={userTurns === 0}><Sparkles size={15}/>{brief ? "根据讨论重新生成模板" : "生成可编辑研究模板"}</button>
        </div>
        <div className={brief ? "brief-editor ready" : "brief-editor"}>
          {!brief ? <div className="brief-placeholder"><MessageSquareText size={26}/><h3>研究模板会出现在这里</h3><p>AI 会尽量补全问题、证据标准、预算和最小实验；不确定的内容会明确标记，避免替你擅自决定。</p></div> : <>
            <div className="brief-editor-title"><div><span><PencilLine size={14}/>可直接编辑</span><h3>提交前审查研究任务</h3></div><em>草稿</em></div>
            <label>研究问题<textarea value={brief.question} onChange={(event)=>setBrief({...brief,question:event.target.value})} rows={4}/></label>
            <label>研究范围<textarea value={brief.scope} onChange={(event)=>setBrief({...brief,scope:event.target.value})} rows={3}/></label>
            <div className="brief-fields"><label>最低证据数<input type="number" min={1} max={20} value={brief.evidenceMinimum} onChange={(event)=>setBrief({...brief,evidenceMinimum:Number(event.target.value)})}/></label><label>计算预算<input value={brief.computeBudget} onChange={(event)=>setBrief({...brief,computeBudget:event.target.value})}/></label></div>
            <label>实验规模<input value={brief.experimentScale} onChange={(event)=>setBrief({...brief,experimentScale:event.target.value})}/></label>
            <fieldset><legend>研究要求</legend>{brief.requirements.map((item,index)=><div key={index}><span>{index+1}</span><input value={item} onChange={(event)=>updateRequirement(index,event.target.value)}/><button type="button" onClick={()=>setBrief({...brief,requirements:brief.requirements.filter((_,i)=>i!==index)})}>×</button></div>)}<button className="button-secondary" type="button" onClick={addRequirement}>＋ 增加要求</button></fieldset>
            <div className="brief-submit"><span><CheckCircle2 size={15}/>只有确认后才创建项目并启动研究。</span><button className="button-primary" type="button" onClick={submit} disabled={disabled || submitting}>{submitting?<Loader2 className="spin" size={15}/>:<Sparkles size={15}/>}确认模板并提交</button></div>
          </>}
        </div>
      </div>
    </section>
  );
}
