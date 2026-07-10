import type { ReactNode } from "react";

type MarkdownTextProps = {
  text: string;
  compact?: boolean;
};

type Block =
  | { type: "paragraph"; text: string }
  | { type: "heading"; level: 2 | 3 | 4; text: string }
  | { type: "quote"; text: string }
  | { type: "code"; text: string }
  | { type: "ul"; items: string[] }
  | { type: "ol"; items: string[] };

const inlinePattern = /(\[[^\]]+\]\((https?:\/\/[^)\s]+)\)|`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g;

function parseBlocks(text: string): Block[] {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index] ?? "";
    if (!line.trim()) {
      index += 1;
      continue;
    }

    if (line.trim().startsWith("```")) {
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !(lines[index] ?? "").trim().startsWith("```")) {
        codeLines.push(lines[index] ?? "");
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push({ type: "code", text: codeLines.join("\n") });
      continue;
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(line.trim());
    if (heading) {
      blocks.push({
        type: "heading",
        level: Math.min(Math.max(heading[1].length, 2), 4) as 2 | 3 | 4,
        text: heading[2].trim(),
      });
      index += 1;
      continue;
    }

    if (/^\s*>\s+/.test(line)) {
      const quoteLines: string[] = [];
      while (index < lines.length && /^\s*>\s+/.test(lines[index] ?? "")) {
        quoteLines.push((lines[index] ?? "").replace(/^\s*>\s+/, "").trim());
        index += 1;
      }
      blocks.push({ type: "quote", text: quoteLines.join(" ") });
      continue;
    }

    if (/^\s*[-*+]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*[-*+]\s+/.test(lines[index] ?? "")) {
        items.push((lines[index] ?? "").replace(/^\s*[-*+]\s+/, "").trim());
        index += 1;
      }
      blocks.push({ type: "ul", items });
      continue;
    }

    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*\d+[.)]\s+/.test(lines[index] ?? "")) {
        items.push((lines[index] ?? "").replace(/^\s*\d+[.)]\s+/, "").trim());
        index += 1;
      }
      blocks.push({ type: "ol", items });
      continue;
    }

    const paragraphLines: string[] = [];
    while (
      index < lines.length &&
      (lines[index] ?? "").trim() &&
      !(lines[index] ?? "").trim().startsWith("```") &&
      !/^(#{1,4})\s+/.test((lines[index] ?? "").trim()) &&
      !/^\s*>\s+/.test(lines[index] ?? "") &&
      !/^\s*[-*+]\s+/.test(lines[index] ?? "") &&
      !/^\s*\d+[.)]\s+/.test(lines[index] ?? "")
    ) {
      paragraphLines.push((lines[index] ?? "").trim());
      index += 1;
    }
    blocks.push({ type: "paragraph", text: paragraphLines.join(" ") });
  }

  return blocks;
}

function renderInline(text: string, prefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  for (const match of text.matchAll(inlinePattern)) {
    const raw = match[0];
    const start = match.index ?? 0;
    if (start > lastIndex) nodes.push(text.slice(lastIndex, start));
    const key = `${prefix}-${start}`;
    if (raw.startsWith("**") && raw.endsWith("**")) {
      nodes.push(<strong key={key}>{raw.slice(2, -2)}</strong>);
    } else if (raw.startsWith("*") && raw.endsWith("*")) {
      nodes.push(<em key={key}>{raw.slice(1, -1)}</em>);
    } else if (raw.startsWith("`") && raw.endsWith("`")) {
      nodes.push(<code key={key}>{raw.slice(1, -1)}</code>);
    } else {
      const link = /^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/.exec(raw);
      nodes.push(
        link ? (
          <a key={key} href={link[2]} target="_blank" rel="noreferrer">
            {link[1]}
          </a>
        ) : (
          raw
        ),
      );
    }
    lastIndex = start + raw.length;
  }
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex));
  return nodes;
}

export function MarkdownText({ text, compact = false }: MarkdownTextProps) {
  const blocks = parseBlocks(text);
  if (!blocks.length) return null;
  return (
    <div className={compact ? "markdown-text compact" : "markdown-text"}>
      {blocks.map((block, index) => {
        const key = `${block.type}-${index}`;
        if (block.type === "heading") {
          const HeadingTag = `h${block.level}` as "h2" | "h3" | "h4";
          return <HeadingTag key={key}>{renderInline(block.text, key)}</HeadingTag>;
        }
        if (block.type === "quote") return <blockquote key={key}>{renderInline(block.text, key)}</blockquote>;
        if (block.type === "code") return <pre key={key}>{block.text}</pre>;
        if (block.type === "ul") {
          return (
            <ul key={key}>
              {block.items.map((item, itemIndex) => (
                <li key={`${key}-${itemIndex}`}>{renderInline(item, `${key}-${itemIndex}`)}</li>
              ))}
            </ul>
          );
        }
        if (block.type === "ol") {
          return (
            <ol key={key}>
              {block.items.map((item, itemIndex) => (
                <li key={`${key}-${itemIndex}`}>{renderInline(item, `${key}-${itemIndex}`)}</li>
              ))}
            </ol>
          );
        }
        return <p key={key}>{renderInline(block.text, key)}</p>;
      })}
    </div>
  );
}
