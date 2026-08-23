"use client";

import type { Verdict } from "@/lib/evidence";

const LABEL: Record<Verdict, string> = {
  pass: "Pass",
  fail: "Fail",
  pending: "Solving",
  error: "Error",
};

const CHIP: Record<Verdict, string> = {
  pass: "border-pass/40 bg-pass/10 text-pass",
  fail: "border-fail/40 bg-fail/10 text-fail",
  pending: "border-ink-700 bg-ink-800 text-fg-muted",
  error: "border-warn/40 bg-warn/10 text-warn",
};

const DOT: Record<Verdict, string> = {
  pass: "bg-pass",
  fail: "bg-fail",
  pending: "bg-ink-600",
  error: "bg-warn",
};

/** The verdict, spelled out. Used wherever one result is being inspected. */
export function VerdictChip({ v, label }: { v: Verdict; label?: string }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-sm border px-1.5 py-px text-[10px] font-medium ${CHIP[v]}`}
    >
      {label ?? LABEL[v]}
    </span>
  );
}

/** The same verdict at list density. Never the only carrier of meaning: the
 *  reason travels next to it. */
export function VerdictDot({ v }: { v: Verdict }) {
  return (
    <span
      aria-hidden
      className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${DOT[v]} ${
        v === "pending" ? "animate-pulse" : ""
      }`}
    />
  );
}

const WORD: Record<Verdict, string> = {
  pass: "text-pass",
  fail: "text-fail",
  pending: "text-fg-muted",
  error: "text-warn",
};

/** The verdict as a word, for rows that are scanned rather than read: colour
 *  alone would put the whole judgement on hue. */
export function VerdictWord({ v, label }: { v: Verdict; label?: string }) {
  return (
    <span className={`w-11 shrink-0 text-[11px] ${WORD[v]}`}>{label ?? LABEL[v]}</span>
  );
}
