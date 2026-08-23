"use client";

import { useEffect, useRef, useState } from "react";
import { useApp, type AgentKind } from "@/lib/store";
import type { AgentMessage } from "@/lib/types";
import { KevinLockup } from "@/components/Logo";
import { BandMenu } from "./BandMenu";
import { Dropdown, MenuItem } from "./primitives";

/**
 * The right rail is the conversation: the spec goes in at the top, the
 * agent's reasoning comes back underneath. No title — a text box with a Run
 * button under it says what it is — and the agent is picked from a menu
 * beneath the input, the way a model is picked under a chat box. Evidence is
 * always rendered: it lands after the result and never gates it, so there is
 * nothing to decide.
 *
 * The three message kinds the backend emits still read as three things:
 * orchestrator narration is a hairline break, a solve landing is a
 * measurement block with its verdict, a decision is a labelled statement.
 */

const LABEL = "text-[10px] font-semibold uppercase tracking-[0.14em] text-fg-faint";

/* ------------------------------------------------------------------ marks */

function AlertMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 16 16"
      width={14}
      height={14}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      <path d="M8 2.4 14.6 13.6H1.4Z" />
      <path d="M8 6.6v3" />
      <path d="M8 11.7h.01" />
    </svg>
  );
}

function Spinner({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 16 16"
      width={13}
      height={13}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      aria-hidden="true"
      className={`animate-spin ${className ?? ""}`}
    >
      <circle cx="8" cy="8" r="6" className="opacity-30" />
      <path d="M14 8a6 6 0 0 0-6-6" strokeLinecap="round" />
    </svg>
  );
}

/* ------------------------------------------------------------------ agents */

interface AgentChoice {
  id: AgentKind;
  name: string;
  /** One line: what it is and what it costs. Shown for the selected choice. */
  meta: string;
}

// Three ways to run, and the difference that matters is whose reasoning you
// get. Saved is Devin's own decisions on THIS device, recovered from a real
// session and replayed for free — the solver still re-runs every candidate, so
// the numbers are computed now, not remembered. Mock is the fallback that
// invents placements itself, and it says so: it is a stand-in, not a result.
const AGENT_CHOICES: AgentChoice[] = [
  { id: "devin", name: "Devin", meta: "Live reasoning on this device · ~2.5 min, uses quota" },
  { id: "replay", name: "Saved run", meta: "Devin's real decisions on this device, re-solved · instant, free" },
  { id: "mock", name: "Mock", meta: "Heuristic stand-in, real solves · seconds, free" },
];

const agentName = (id: AgentKind) => AGENT_CHOICES.find((a) => a.id === id)?.name ?? id;

/* ------------------------------------------------- reading the message feed */

type Line =
  | { t: "note"; text: string }
  | { t: "step"; text: string }
  | { t: "prose"; text: string }
  | { t: "decision"; label: string; body: string }
  | { t: "outcome"; label: string; body: string; state: "pass" | "warn" }
  | { t: "failure"; body: string }
  | {
      t: "result";
      head: string;
      metrics: string[];
      verdict: "pass" | "fail" | "error" | null;
      note: string;
    };

/**
 * `c002_ifa_p10__length_mm=31.9 (IFA, Wi-Fi / BT 2.4 GHz)` -> `c002 · IFA · 31.9 mm`.
 * The id encodes candidate, type, anchor and any swept parameter; the band is
 * the iteration's context and the anchor is in the table, so neither repeats
 * here.
 */
function prettyHead(raw: string): string {
  const id = raw.replace(/\s*\(.*\)\s*$/, "");
  const m = /^(c\d+)_([a-z]+)_([a-z]\d+)(?:__([a-z_]+)=([\d.]+))?$/i.exec(id);
  if (!m) return raw;
  const [, cand, type, , param, val] = m;
  const parts = [cand, type.toUpperCase()];
  if (param && val) parts.push(`${val} ${param.replace(/^length_mm$/, "mm").replace(/_mm$/, " mm")}`);
  return parts.join(" · ");
}

/** `c3 (IFA, Wi-Fi 2.4): S11 -14.2 dB at 2.44 GHz, … -> PASS. notes` */
function readResult(text: string): Line {
  const i = text.indexOf(": ");
  const head = prettyHead(i > 0 ? text.slice(0, i) : text);
  const rest = i > 0 ? text.slice(i + 2) : "";
  if (!rest || /solve failed/i.test(rest)) {
    return { t: "result", head, metrics: [], verdict: "error", note: rest };
  }
  const arrow = rest.indexOf(" -> ");
  const measured = arrow > 0 ? rest.slice(0, arrow) : rest;
  const tail = arrow > 0 ? rest.slice(arrow + 4) : "";
  const verdict = /^PASS/.test(tail) ? "pass" : /^FAIL/.test(tail) ? "fail" : null;
  return {
    t: "result",
    head,
    metrics: measured.split(", ").map((s) => s.trim()).filter(Boolean),
    verdict,
    note: tail.replace(/^(PASS|FAIL)\.?/, "").trim(),
  };
}

/** Decision events arrive as `accept_bottom_edge: rationale…`. */
const DECISION = /^([A-Za-z][A-Za-z0-9_-]*(?: [A-Za-z0-9_-]+){0,2}):\s+([\s\S]+)$/;

function read(m: AgentMessage): Line {
  if (m.role === "user") return { t: "note", text: m.text };
  if (m.kind === "step") return { t: "step", text: m.text };
  if (m.kind === "result") return readResult(m.text);

  if (/^run failed:/i.test(m.text)) {
    return { t: "failure", body: m.text.replace(/^run failed:\s*/i, "") };
  }
  const hit = DECISION.exec(m.text);
  if (!hit) return { t: "prose", text: m.text };

  const label = hit[1].replace(/_/g, " ");
  const body = hit[2];
  if (/^recommendation$/i.test(label)) {
    return {
      t: "outcome",
      label: "Recommendation",
      body,
      state: /requirements met/i.test(body) ? "pass" : "warn",
    };
  }
  return { t: "decision", label: label.charAt(0).toUpperCase() + label.slice(1), body };
}

type ResultLine = Extract<Line, { t: "result" }>;
type Block = { t: "line"; key: string; line: Line } | { t: "solves"; key: string; lines: ResultLine[] };

/**
 * Consecutive solve results fold into one block. A batch of thirteen sweeps
 * is one thing the agent did, not thirteen, and the numbers live in the
 * candidate table; here they are a summary that opens on request.
 */
function toBlocks(msgs: AgentMessage[]): Block[] {
  const out: Block[] = [];
  for (const m of msgs) {
    const line = read(m);
    const last = out[out.length - 1];
    if (line.t === "result") {
      if (last?.t === "solves") last.lines.push(line);
      else out.push({ t: "solves", key: m.id, lines: [line] });
    } else {
      out.push({ t: "line", key: m.id, line });
    }
  }
  return out;
}

const s11Of = (r: ResultLine) => {
  const m = /S11\s+(-?\d+(?:\.\d+)?)\s*dB/.exec(r.metrics[0] ?? "");
  return m ? parseFloat(m[1]) : null;
};

function SolveGroup({ lines, live }: { lines: ResultLine[]; live: boolean }) {
  const [open, setOpen] = useState(false);
  const pass = lines.filter((l) => l.verdict === "pass").length;
  const failed = lines.filter((l) => l.verdict === "error").length;
  const best = lines.map(s11Of).filter((v): v is number => v !== null).sort((a, b) => a - b)[0];
  return (
    <div className="think-in">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 rounded-md border border-ink-800 bg-ink-900 px-3 py-2 text-left text-[11px] transition hover:border-ink-700"
      >
        <span
          className={`h-1.5 w-1.5 shrink-0 rounded-full ${
            live ? "animate-pulse bg-accent" : pass > 0 ? "bg-pass" : "bg-fail"
          }`}
        />
        <span className="text-fg">
          {lines.length} solve{lines.length === 1 ? "" : "s"}
        </span>
        <span className="text-fg-muted">
          · {pass} pass
          {failed > 0 && <span className="text-fail"> · {failed} no solve</span>}
          {best !== undefined && (
            <>
              {" "}
              · best <span className="font-mono text-fg">{best.toFixed(1)} dB</span>
            </>
          )}
        </span>
        <span className={`ml-auto text-fg-faint transition-transform ${open ? "rotate-90" : ""}`}>
          <svg viewBox="0 0 16 16" width={12} height={12} fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M6 3.5 10.5 8 6 12.5" />
          </svg>
        </span>
      </button>
      {open && (
        <div className="mt-2 space-y-2.5 pl-1">
          {lines.map((l, i) => (
            <TranscriptLine key={i} line={l} />
          ))}
        </div>
      )}
    </div>
  );
}

function TranscriptLine({ line }: { line: Line }) {
  switch (line.t) {
    case "step":
      return (
        <div className="think-in pt-1">
          <div className="h-px bg-ink-800" />
          <p className="pt-2.5 text-[11px] leading-5 text-fg-muted">{line.text}</p>
        </div>
      );

    case "prose":
      return <p className="think-in text-[12.5px] leading-6 text-fg-muted">{line.text}</p>;

    case "decision":
      return (
        <div className="think-in border-l border-ink-600 pl-3">
          <p className="text-[11px] font-semibold text-fg">{line.label}</p>
          <p className="mt-1 text-[12.5px] leading-6 text-fg-muted">{line.body}</p>
        </div>
      );

    case "outcome":
      return (
        <div
          className={`think-in border-l pl-3 ${
            line.state === "pass" ? "border-pass" : "border-warn"
          }`}
        >
          <p className="text-[11px] font-semibold text-fg">{line.label}</p>
          <p className="mt-1 text-[12.5px] leading-6 text-fg">{line.body}</p>
        </div>
      );

    case "failure":
      return (
        <div className="think-in border-l border-fail pl-3">
          <p className="text-[11px] font-semibold text-fail">Run failed</p>
          <p className="mt-1 text-[12.5px] leading-6 text-fg-muted">{line.body}</p>
        </div>
      );

    case "note":
      return (
        <div className="think-in border-l border-accent-dim pl-3">
          <p className={LABEL}>You</p>
          <p className="mt-1 text-[12.5px] leading-6 text-fg">{line.text}</p>
        </div>
      );

    case "result":
      return (
        <div
          className={`think-in border-l pl-3 ${
            line.verdict === "pass"
              ? "border-pass"
              : line.verdict === "fail" || line.verdict === "error"
                ? "border-fail"
                : "border-ink-600"
          }`}
        >
          <div className="flex items-baseline gap-2">
            <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-fg">
              {line.head}
            </span>
            {line.verdict && (
              <span
                className={`shrink-0 font-mono text-[10px] tracking-[0.12em] ${
                  line.verdict === "pass" ? "text-pass" : "text-fail"
                }`}
              >
                {line.verdict === "error" ? "NO SOLVE" : line.verdict.toUpperCase()}
              </span>
            )}
          </div>
          {!!line.metrics.length && (
            <p className="mt-1 font-mono text-[11px] leading-5 text-fg-muted">
              {line.metrics.map((metric, i) => (
                <span key={metric}>
                  {i > 0 && <span className="px-1.5 text-fg-faint">·</span>}
                  {metric}
                </span>
              ))}
            </p>
          )}
          {!!line.note && (
            <p className="mt-1 text-[11px] leading-5 text-fg-muted">{line.note}</p>
          )}
        </div>
      );
  }
}

/* -------------------------------------------------------------- agent menu */

function ArrowUp() {
  return (
    <svg viewBox="0 0 16 16" width={13} height={13} fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M8 12.5v-9" />
      <path d="M4.5 7 8 3.5 11.5 7" />
    </svg>
  );
}

/** Who runs the study. The menu carries each choice's trade-off, so it is
 *  read at the moment of choosing. */
function AgentMenu({
  value,
  onChange,
  disabled,
}: {
  value: AgentKind;
  onChange: (id: AgentKind) => void;
  disabled: boolean;
}) {
  const current = AGENT_CHOICES.find((a) => a.id === value) ?? AGENT_CHOICES[0];
  return (
    <Dropdown ariaLabel="Agent that runs the study" label={current.name} title={current.meta} disabled={disabled}>
      {(close) =>
        AGENT_CHOICES.map((c) => (
          <MenuItem
            key={c.id}
            on={c.id === value}
            onClick={() => {
              onChange(c.id);
              close();
            }}
            name={c.name}
            meta={c.meta}
          />
        ))
      }
    </Dropdown>
  );
}

/* -------------------------------------------------------------- the panel */

function elapsedLabel(seconds: number) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function AgentPanel() {
  const prompt = useApp((s) => s.prompt);
  const setPrompt = useApp((s) => s.setPrompt);
  const startRun = useApp((s) => s.startRun);
  const poll = useApp((s) => s.poll);
  const running = useApp((s) => s.running);
  const planning = useApp((s) => s.planning);
  const messages = useApp((s) => s.messages);
  const error = useApp((s) => s.error);
  const runId = useApp((s) => s.runId);
  const agent = useApp((s) => s.agent);
  const setAgent = useApp((s) => s.setAgent);
  const agentFellBack = useApp((s) => s.agentFellBack);
  const tapeOtherDevice = useApp((s) => s.tapeOtherDevice);
  const sendNote = useApp((s) => s.sendNote);
  const enabledBands = useApp((s) => s.enabledBands);
  const jobs = useApp((s) => s.jobs);
  const engine = useApp((s) => s.engine);
  const reset = useApp((s) => s.reset);

  const [note, setNote] = useState("");
  const [editingSpec, setEditingSpec] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const feedRef = useRef<HTMLDivElement>(null);

  // The study finishing is not the end of the run: the evidence renders after
  // run_finished, so `running` goes false while artifacts are still landing.
  // Keep polling — more slowly — until the media stage is done too.
  const stage = useApp((s) => s.stage);
  const rendering = stage === "media";
  useEffect(() => {
    if (!runId || (!running && !rendering)) return;
    const t = setInterval(() => void poll(), running ? 600 : 2000);
    return () => clearInterval(t);
  }, [running, rendering, runId, poll]);

  // Devin runs for minutes: a clock is the difference between "working" and
  // "stuck". It freezes where the run ended.
  useEffect(() => {
    if (!running) return;
    const t0 = Date.now();
    setElapsed(0);
    const t = setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 1000);
    return () => clearInterval(t);
  }, [running, runId]);

  useEffect(() => {
    // Only chase the transcript once there is one; the spec editor shares
    // this scroller and must not be pushed off the top on mount.
    if (!messages.length) return;
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length]);

  // The spec is echoed into the feed as message u0; it already has a home at
  // the top of the rail.
  const transcript = messages.filter((m) => m.id !== "u0");
  const blocks = toBlocks(transcript);
  const started = !!runId || messages.length > 0;
  const specOpen = !started || editingSpec;
  const canRun = !running && !!prompt.trim() && enabledBands.length > 0;

  const blocker = !prompt.trim()
    ? "Write the spec first."
    : !enabledBands.length
      ? "Pick a band first."
      : null;

  const run = () => {
    if (!canRun) return;
    setEditingSpec(false);
    void startRun();
  };

  const status = running ? (planning ? "Planning" : "Simulating") : rendering ? "Rendering" : "Finished";
  const solved = jobs.filter((j) => j.status === "complete").length;
  const failed = jobs.filter((j) => j.status === "failed").length;

  return (
    <div className="flex h-full flex-col bg-ink-950">
      {/* The mark, where a sidebar keeps it. Spacing sets it apart from the
          conversation; no rule needed. */}
      <div className="shrink-0 px-5 pb-2 pt-4">
        <KevinLockup height={18} className="text-fg" />
      </div>

      {/* The spec, once a run owns the rail: the run's status, then what was
          asked, still legible but no longer the thing you are looking at. */}
      {started && !editingSpec && (
        <div className="shrink-0 border-b border-ink-800 px-5 py-3.5">
          <div className="flex items-center gap-2">
            {(running || rendering) && (
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
            )}
            <span className="text-[11px] text-fg-muted">
              {agentName(agent)} · {status}
            </span>
            {elapsed > 0 && (
              <span className="font-mono text-[11px] text-fg-muted">{elapsedLabel(elapsed)}</span>
            )}
            {jobs.length > 0 && (
              <span
                className="font-mono text-[11px] text-fg-muted"
                title={engine ? `Solver: ${engine}` : undefined}
              >
                · {solved}/{jobs.length} solved
                {failed > 0 && <span className="text-fail"> · {failed} failed</span>}
              </span>
            )}
            <span className="ml-auto flex items-center gap-3">
              {!running && (
                <button
                  type="button"
                  onClick={() => setEditingSpec(true)}
                  className="text-[11px] text-accent transition hover:brightness-110"
                >
                  Edit spec
                </button>
              )}
              <button
                type="button"
                onClick={reset}
                title={
                  running
                    ? "Clears this run from the workspace. The solve keeps running on the backend."
                    : "Clears this run's candidates, results and report."
                }
                className="text-[11px] text-fg-muted transition hover:text-fg"
              >
                Clear
              </button>
            </span>
          </div>
          <p className="mt-1.5 line-clamp-2 text-[12.5px] leading-5 text-fg">{prompt}</p>
        </div>
      )}

      {tapeOtherDevice && (
        // A recording's solves are re-run live against this device; its
        // commentary describes the phone it was captured on. Say so.
        <div className="shrink-0 px-5 pt-3">
          <div className="flex gap-2.5 rounded-md border border-ink-700 bg-ink-900 px-3 py-2.5">
            <AlertMark className="mt-px shrink-0 text-fg-faint" />
            <p className="min-w-0 text-[11px] leading-5 text-fg-muted">
              Recorded on a different device. The solves below are live for this one; the
              commentary is the recording&apos;s.
            </p>
          </div>
        </div>
      )}

      {agentFellBack && (
        // The orchestrator restarts a dead agent channel on the heuristic so a
        // demo always ends with a result. A run that looks like Devin's but
        // isn't is worse than no run at all, so this stays loud.
        <div className="shrink-0 px-5 pt-3">
          <div className="flex gap-2.5 rounded-md border border-warn/45 bg-warn/10 px-3 py-2.5">
            <AlertMark className="mt-px shrink-0 text-warn" />
            <p className="min-w-0 text-[11px] leading-5 text-fg">
              <span className="font-semibold text-warn">Devin did not run.</span> The heuristic
              finished this study; the solves are real, the reasoning is not Devin&apos;s. The API
              error is in the transcript.
            </p>
          </div>
        </div>
      )}

      {error && (
        <div className="shrink-0 px-5 pt-3">
          <div className="flex gap-2.5 rounded-md border border-fail/45 bg-fail/10 px-3 py-2.5">
            <AlertMark className="mt-px shrink-0 text-fail" />
            <p className="min-w-0 text-[11px] leading-5 text-fg">{error}</p>
          </div>
        </div>
      )}

      <div ref={feedRef} className="min-h-0 flex-1 overflow-y-auto">
        {specOpen && (
          <div className={`px-5 pb-5 pt-5 ${started ? "border-b border-ink-800" : ""}`}>
            {/* The box resizes as a whole, so the grip sits at its corner
                beside Run rather than in the middle above it. */}
            <div className="flex min-h-[11rem] resize-y flex-col overflow-hidden rounded-lg border border-ink-700 bg-ink-900 transition focus-within:border-ink-600">
              <textarea
                id="antenna-spec"
                aria-label="Antenna spec"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) run();
                }}
                spellCheck={false}
                placeholder="2.4 GHz Wi-Fi antenna on the bottom edge. 6 mm clear of the battery, VSWR under 2 in band, efficiency above 55%."
                className="block min-h-0 w-full flex-1 resize-none bg-transparent px-3.5 py-3 text-[13px] leading-6 text-fg outline-none placeholder:text-fg-faint focus-visible:outline-none"
              />
              <div className="flex shrink-0 items-center gap-2 px-2 pb-2">
                <AgentMenu value={agent} onChange={setAgent} disabled={running} />
                <BandMenu disabled={running} />
                {started && (
                  <button
                    type="button"
                    onClick={() => setEditingSpec(false)}
                    className="text-[11px] text-fg-muted transition hover:text-fg"
                  >
                    Cancel
                  </button>
                )}
                <button
                  type="button"
                  onClick={run}
                  disabled={!canRun}
                  title="Run the placement study (Cmd + Enter)"
                  className="ml-auto flex items-center gap-1.5 rounded-full bg-fg py-1 pl-3 pr-2 text-[12px] font-medium text-ink-950 transition hover:bg-white active:bg-fg disabled:cursor-not-allowed disabled:bg-ink-800 disabled:text-fg-faint"
                >
                  {running ? (
                    <>
                      Running
                      <Spinner />
                    </>
                  ) : (
                    <>
                      Run
                      <ArrowUp />
                    </>
                  )}
                </button>
              </div>
            </div>
            {!running && blocker && (
              <p className="mt-2 text-[11px] leading-5 text-warn">{blocker}</p>
            )}
          </div>
        )}

        {started && (
          <div className="space-y-3.5 px-5 pb-12 pt-5">
            {blocks.map((b, i) =>
              b.t === "solves" ? (
                <SolveGroup key={b.key} lines={b.lines} live={running && i === blocks.length - 1} />
              ) : (
                <TranscriptLine key={b.key} line={b.line} />
              ),
            )}
            {planning && (
              <div className="think-in flex items-center gap-2 pt-1">
                <Spinner className="text-accent" />
                <span className="text-[11px] text-fg-muted">Planning placements…</span>
              </div>
            )}
            {!transcript.length && !planning && (
              <p className="text-[11px] leading-5 text-fg-muted">Waiting for the agent.</p>
            )}
          </div>
        )}
      </div>

      {running && (
        <form
          className="shrink-0 border-t border-ink-800 px-5 py-3"
          onSubmit={(e) => {
            e.preventDefault();
            const t = note.trim();
            if (!t) return;
            setNote("");
            void sendNote(t);
          }}
        >
          <div className="flex gap-2">
            <input
              id="agent-note"
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              aria-label="Note to the agent"
              title="Lands with the agent's next iteration; it does not restart the run."
              placeholder="Note to the agent…"
              className="min-w-0 flex-1 rounded-md border border-ink-700 bg-ink-900 px-3 py-2 text-[12.5px] text-fg outline-none transition placeholder:text-fg-faint focus:border-ink-600 focus-visible:outline-none"
            />
            <button
              type="submit"
              disabled={!note.trim()}
              className="shrink-0 rounded-md border border-ink-700 px-3 text-[12px] text-fg transition hover:border-accent disabled:cursor-not-allowed disabled:border-ink-800 disabled:text-fg-muted"
            >
              Send
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
