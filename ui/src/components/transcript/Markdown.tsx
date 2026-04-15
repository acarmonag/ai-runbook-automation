/**
 * Lightweight markdown renderer — no external dependencies.
 * Handles: headings, bold, italic, inline code, fenced code blocks,
 *          bullets, numbered lists, hr, paragraphs.
 */

import React from "react";

// ── Inline styling (bold, italic, inline code) ────────────────────────────────

function renderInline(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const re = /(\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`)/g;
  let last = 0;
  let m: RegExpExecArray | null;

  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    if (m[2]) parts.push(<strong key={m.index} className="font-semibold text-zinc-200">{m[2]}</strong>);
    else if (m[3]) parts.push(<em key={m.index} className="italic text-zinc-300">{m[3]}</em>);
    else if (m[4]) parts.push(<code key={m.index} className="rounded bg-zinc-800 px-1 py-0.5 font-mono text-[0.75em] text-violet-300">{m[4]}</code>);
    last = m.index + m[0].length;
  }

  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

// ── Block-level parsing ───────────────────────────────────────────────────────

interface MarkdownProps {
  text: string;
  className?: string;
}

export function Markdown({ text, className = "" }: MarkdownProps) {
  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block  ```[lang]  ...  ```
    if (/^```/.test(line)) {
      const lang = line.slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) {
        codeLines.push(lines[i]);
        i++;
      }
      i++; // consume closing ```

      // plaintext/text fences are just prose — render as paragraphs
      // JSON-only code block → render as a compact key-value card
      const isJsonBlock = lang === "json" || lang === "JSON";
      if (isJsonBlock) {
        const raw = codeLines.join("\n").trim();
        let parsed: Record<string, unknown> | null = null;
        try { parsed = JSON.parse(raw) as Record<string, unknown>; } catch { /* not valid JSON */ }
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
          const entries = Object.entries(parsed).filter(([, v]) => v !== null && v !== undefined);
          elements.push(
            <div key={key++} className="rounded border border-zinc-700/40 bg-zinc-800/50 overflow-hidden my-1.5">
              <div className="px-3 py-1 border-b border-zinc-700/40 bg-zinc-800/30">
                <span className="text-[10px] font-medium uppercase tracking-wide text-zinc-500">Suggested action</span>
              </div>
              <div className="px-3 py-2 space-y-0.5">
                {entries.map(([k, v]) => (
                  <div key={k} className="flex gap-2 text-[11px]">
                    <span className="shrink-0 font-mono text-zinc-500 w-20 truncate">{k}</span>
                    <span className="text-zinc-300 font-mono truncate">{String(v)}</span>
                  </div>
                ))}
              </div>
            </div>
          );
          continue;
        }
      }

      const isPlaintext = /^(plaintext|plain|text)$/i.test(lang) || lang === "";
      if (isPlaintext) {
        const content = codeLines.join("\n").trim();
        if (content) {
          content.split("\n").forEach((l, idx) => {
            if (l.trim()) {
              elements.push(
                <p key={`${key++}-${idx}`} className="text-sm text-zinc-300 leading-relaxed">
                  {renderInline(l)}
                </p>
              );
            }
          });
        }
        continue;
      }

      const isShell = /^(bash|sh|shell|zsh|cmd)$/i.test(lang);
      elements.push(
        <div key={key++} className="rounded border border-zinc-700/50 bg-zinc-900 overflow-hidden my-1.5">
          <div className="px-3 py-1 flex items-center justify-between border-b border-zinc-700/50 bg-zinc-800/50">
            <span className="text-[10px] font-mono text-zinc-500">{lang}</span>
            {isShell && (
              <span className="text-[10px] text-amber-600/70 italic">not executed — use tools</span>
            )}
          </div>
          <pre className="px-3 py-2 overflow-x-auto font-mono text-[11px] text-zinc-300 leading-relaxed">
            {codeLines.join("\n")}
          </pre>
        </div>
      );
      continue;
    }

    // Horizontal rule
    if (/^---+\s*$/.test(line)) {
      elements.push(<hr key={key++} className="my-3 border-zinc-700/60" />);
      i++;
      continue;
    }

    // Headings
    const h3 = line.match(/^###\s+(.*)/);
    if (h3) {
      elements.push(
        <h3 key={key++} className="mt-3 mb-1 text-xs font-bold uppercase tracking-wide text-zinc-400">
          {renderInline(h3[1])}
        </h3>
      );
      i++;
      continue;
    }
    const h2 = line.match(/^##\s+(.*)/);
    if (h2) {
      elements.push(
        <h2 key={key++} className="mt-3 mb-1 text-sm font-semibold text-zinc-300">
          {renderInline(h2[1])}
        </h2>
      );
      i++;
      continue;
    }
    const h1 = line.match(/^#\s+(.*)/);
    if (h1) {
      elements.push(
        <h1 key={key++} className="mt-3 mb-1 text-sm font-bold text-zinc-200">
          {renderInline(h1[1])}
        </h1>
      );
      i++;
      continue;
    }

    // Bullet list — collect consecutive items
    if (/^[-*]\s+/.test(line)) {
      const items: React.ReactNode[] = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i])) {
        const itemText = lines[i].replace(/^[-*]\s+/, "");
        items.push(
          <li key={i} className="flex gap-2 text-sm text-zinc-400">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-zinc-600" />
            <span>{renderInline(itemText)}</span>
          </li>
        );
        i++;
      }
      elements.push(<ul key={key++} className="my-1.5 space-y-0.5">{items}</ul>);
      continue;
    }

    // Numbered list
    if (/^\d+\.\s+/.test(line)) {
      const items: React.ReactNode[] = [];
      let n = 1;
      while (i < lines.length && /^\d+\.\s+/.test(lines[i])) {
        const itemText = lines[i].replace(/^\d+\.\s+/, "");
        items.push(
          <li key={i} className="flex gap-2 text-sm text-zinc-400">
            <span className="shrink-0 w-4 text-right text-zinc-600">{n++}.</span>
            <span>{renderInline(itemText)}</span>
          </li>
        );
        i++;
      }
      elements.push(<ol key={key++} className="my-1.5 space-y-0.5">{items}</ol>);
      continue;
    }

    // Blank line — skip
    if (line.trim() === "") {
      i++;
      continue;
    }

    // Paragraph
    elements.push(
      <p key={key++} className="text-sm text-zinc-300 leading-relaxed">
        {renderInline(line)}
      </p>
    );
    i++;
  }

  return <div className={`space-y-1 ${className}`}>{elements}</div>;
}
