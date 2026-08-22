"use client";

import { Fragment, type ReactNode } from "react";

/** `**bold**`, `` `code` `` and `_em_` inside one line. */
function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|_[^_]+_)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const t = m[0];
    if (t.startsWith("**")) out.push(<strong key={k++} className="text-slate-100">{t.slice(2, -2)}</strong>);
    else if (t.startsWith("`")) out.push(<code key={k++} className="rounded bg-slate-800/80 px-1 font-mono text-[10px] text-slate-200">{t.slice(1, -1)}</code>);
    else out.push(<em key={k++} className="text-slate-500">{t.slice(1, -1)}</em>);
    last = m.index + t.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

/**
 * Just enough Markdown for the backend's report.md: ATX headings, bullet
 * lists, pipe tables, paragraphs. Anything else renders as a paragraph.
 */
export function Markdown({ source }: { source: string }) {
  const lines = source.replace(/\r/g, "").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let k = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    const h = /^(#{1,6})\s+(.*)$/.exec(line);
    if (h) {
      const level = h[1].length;
      const cls =
        level === 1
          ? "mt-1 text-sm font-semibold text-slate-100"
          : level === 2
            ? "mt-4 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400"
            : "mt-3 text-xs font-semibold text-slate-200";
      blocks.push(<div key={k++} className={cls}>{inline(h[2])}</div>);
      i++;
      continue;
    }
    if (/^\s*[-*]\s+/.test(line) || /^\s*\d+\.\s+/.test(line)) {
      const ordered = /^\s*\d+\./.test(line);
      const items: string[] = [];
      while (i < lines.length && (/^\s*[-*]\s+/.test(lines[i]) || /^\s*\d+\.\s+/.test(lines[i]))) {
        items.push(lines[i].replace(/^\s*([-*]|\d+\.)\s+/, ""));
        i++;
      }
      const Tag = ordered ? "ol" : "ul";
      blocks.push(
        <Tag key={k++} className={`ml-4 space-y-0.5 ${ordered ? "list-decimal" : "list-disc"} text-slate-300`}>
          {items.map((it, j) => <li key={j}>{inline(it)}</li>)}
        </Tag>,
      );
      continue;
    }
    if (line.trim().startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        const cells = lines[i].trim().slice(1, -1).split("|").map((c) => c.trim());
        if (!cells.every((c) => /^:?-+:?$/.test(c))) rows.push(cells);
        i++;
      }
      const [head, ...body] = rows;
      blocks.push(
        <div key={k++} className="my-1.5 overflow-x-auto">
          <table className="w-full border-collapse text-[10.5px]">
            <thead>
              <tr>
                {head.map((c, j) => (
                  <th key={j} className="border-b border-slate-800 px-2 py-1 text-left font-medium text-slate-500">{inline(c)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {body.map((r, ri) => (
                <tr key={ri} className="border-b border-slate-900">
                  {r.map((c, j) => (
                    <td key={j} className={`px-2 py-1 ${j === 0 ? "text-slate-400" : "font-mono text-slate-200"}`}>{inline(c)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    // paragraph: consecutive non-empty, non-block lines
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|\s*[-*]\s|\s*\d+\.\s|\s*\|)/.test(lines[i])) {
      para.push(lines[i]);
      i++;
    }
    blocks.push(<p key={k++} className="text-slate-300">{inline(para.join(" "))}</p>);
  }

  return <div className="space-y-1.5 text-[11px] leading-relaxed">{blocks.map((b, j) => <Fragment key={j}>{b}</Fragment>)}</div>;
}
