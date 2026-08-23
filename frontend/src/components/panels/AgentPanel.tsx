"use client";

import { useEffect, useRef, useState } from "react";
import { useApp, type AgentKind } from "@/lib/store";
import type { AgentMessage } from "@/lib/types";

/**
 * The right rail is the agent's work: the spec the engineer writes, who runs
 * it, and everything the run says back.
 *
 * Three things carry the design here.
 *
 * 1. The prompt is the spec, so it is the first thing in the rail and the
 *    biggest input in the app. Once a run starts it collapses to a recap —
 *    the transcript is what matters then — and comes back on "Edit spec".
 * 2. The reasoning is ambient. Prose sits at --fg-muted (7.5:1 on the ground:
 *    recessive, never unreadable), 12px on a 24px rhythm, fading in with
 *    .think-in as each line lands. Measurements are the only monospace.
 * 3. The three message kinds the backend emits read as three different
 *    things: orchestrator narration is a hairline break in the timeline, a
 *    solve landing is a measurement block with its verdict, and a decision is
 *    a labelled statement in full text colour. Nothing else is emphasised.
 */

const LABEL = "text-[10px] font-semibold uppercase tracking-[0.14em] text-fg-muted";

/* ------------------------------------------------------------------ marks */
/* Drawn, single 1.5 stroke. No glyph icons anywhere in this panel. */

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
  /** The trade-off, stated where the choice is made. */
  blurb: string;
  /** Time and cost, aligned across the three so they compare at a glance. */
  meta: string;
}

const AGENT_CHOICES: AgentChoice[] = [
  {
    id: "mock",
    name: "Mock",
    blurb: "Heuristic placement, real PyNEC solves. No agent reasoning in the transcript.",
    meta: "seconds · free",
  },
  {
    id: "replay",
    name: "Replay",
    blurb: "A recorded live Devin run, played back — the real agent's reasoning, no quota.",
    meta: "instant · free",
  },
  {
    id: "devin",
    name: "Devin",
    blurb: "The live agent, reasoning on this device now. Metered, and slow enough to watch.",
    meta: "~2.5 min · uses quota",
  },
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

/** `c3 (IFA, Wi-Fi 2.4): S11 -14.2 dB at 2.44 GHz, … -> PASS. notes` */
function readResult(text: string): Line {
  const i = text.indexOf(": ");
  const head = i > 0 ? text.slice(0, i) : text;
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

function TranscriptLine({ line }: { line: Line }) {
  switch (line.t) {
    case "step":
      // Orchestrator narration: a break in the timeline, not something to read
      // twice. The rule does the separating; the words stay small.
      return (
        <div className="think-in pt-1">
          <div className="h-px bg-ink-800" />
          <p className="pt-2 text-[11px] leading-5 text-fg-muted">{line.text}</p>
        </div>
      );

    case "prose":
      return <p className="think-in text-[12px] leading-6 text-fg-muted">{line.text}</p>;

    case "decision":
      return (
        <div className="think-in border-l border-ink-600 pl-3">
          <p className="text-[11px] font-semibold text-fg">{line.label}</p>
          <p className="mt-1 text-[12px] leading-6 text-fg-muted">{line.body}</p>
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
          <p className="mt-1 text-[12px] leading-6 text-fg">{line.body}</p>
        </div>
      );

    case "failure":
      return (
        <div className="think-in border-l border-fail pl-3">
          <p className="text-[11px] font-semibold text-fail">Run failed</p>
          <p className="mt-1 text-[12px] leading-6 text-fg-muted">{line.body}</p>
        </div>
      );

    case "note":
      return (
        <div className="think-in border-l border-accent-dim pl-3">
          <p className={LABEL}>Your note</p>
          <p className="mt-1 text-[12px] leading-6 text-fg">{line.text}</p>
        </div>
      );

    case "result":
      // A solve landing. Monospace because every token is a measurement.
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
  const wantMedia = useApp((s) => s.wantMedia);
  const setWantMedia = useApp((s) => s.setWantMedia);
  const poll = useApp((s) => s.poll);
  const running = useApp((s) => s.running);
  const planning = useApp((s) => s.planning);
  const messages = useApp((s) => s.messages);
  const jobs = useApp((s) => s.jobs);
  const error = useApp((s) => s.error);
  const runId = useApp((s) => s.runId);
  const agent = useApp((s) => s.agent);
  const setAgent = useApp((s) => s.setAgent);
  const agentFellBack = useApp((s) => s.agentFellBack);
  const tapeOtherDevice = useApp((s) => s.tapeOtherDevice);
  const sendNote = useApp((s) => s.sendNote);
  const enabledBands = useApp((s) => s.enabledBands);
  const bands = useApp((s) => s.spec.requirements.bands);

  const [note, setNote] = useState("");
  const [editingSpec, setEditingSpec] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const feedRef = useRef<HTMLDivElement>(null);

  // The study finishing is not the end of the run: the evidence renders after
  // run_finished so it can never gate the result, which means `running` goes
  // false while artifacts are still landing. Keep polling — more slowly — until
  // the media stage is done too, or the gallery stays empty forever.
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
    // Only chase the transcript once there is one. The spec editor lives in
    // this same scroller, so an unguarded scroll-to-bottom on mount pushes the
    // primary input — the thing the engineer is meant to type into first —
    // off the top of the panel.
    if (!messages.length) return;
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length]);

  // The spec is echoed into the feed as message u0; it already has a home at
  // the top of the rail, so it does not open the transcript as well.
  const transcript = messages.filter((m) => m.id !== "u0");
  const started = !!runId || messages.length > 0;
  const specOpen = !started || editingSpec;
  const bandShorts = bands.filter((b) => enabledBands.includes(b.id)).map((b) => b.short);
  const canRun = !running && !!prompt.trim() && bandShorts.length > 0;
  const solved = jobs.filter((j) => j.status === "complete").length;
  const failedJobs = jobs.filter((j) => j.status === "failed").length;

  // Disabled controls have to say why, and name the way out.
  const blocker = !prompt.trim()
    ? "Write the spec first — one line naming the band and the limits is enough."
    : !bandShorts.length
      ? "Enable a band in the device panel — the study has nothing to solve for."
      : null;

  const run = () => {
    if (!canRun) return;
    setEditingSpec(false);
    void startRun();
  };

  return (
    <div className="flex h-full flex-col bg-ink-950">
      <header className="flex h-11 shrink-0 items-center gap-3 border-b border-ink-800 px-4">
        <h2 className={LABEL}>Agent</h2>
        {started && (
          <div className="ml-auto flex items-center gap-2">
            {running && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />}
            <span className="text-[11px] text-fg-muted">
              {running ? (planning ? "Planning" : "Simulating") : "Finished"}
            </span>
            {elapsed > 0 && (
              <span className="font-mono text-[11px] text-fg-muted">{elapsedLabel(elapsed)}</span>
            )}
          </div>
        )}
      </header>

      {/* The spec, once a run owns the rail: still legible, no longer the
          thing you are looking at. */}
      {started && !editingSpec && (
        <div className="shrink-0 border-b border-ink-800 px-4 py-3">
          <div className="flex items-baseline gap-3">
            <h3 className={LABEL}>Spec</h3>
            <span className="ml-auto text-[11px] text-fg-muted">{agentName(agent)}</span>
            {!running && (
              <button
                type="button"
                onClick={() => setEditingSpec(true)}
                className="text-[11px] text-accent transition hover:brightness-110"
              >
                Edit spec
              </button>
            )}
          </div>
          <p className="mt-1.5 line-clamp-2 text-[12px] leading-5 text-fg-muted">{prompt}</p>
        </div>
      )}

      {tapeOtherDevice && (
        // A recording is worth replaying — it is a real Devin run at no cost —
        // but its prose describes the phone it was recorded against. The
        // solves are re-run live; the commentary is not. Label it.
        <div className="shrink-0 px-4 pt-3">
          <div className="flex gap-2.5 rounded-md border border-ink-600 bg-ink-850 px-3 py-2.5">
            <AlertMark className="mt-px shrink-0 text-fg-faint" />
            <div className="min-w-0">
              <p className="text-[11px] font-semibold text-fg-muted">
                Recorded transcript — from a run on a different device
              </p>
              <p className="mt-1 text-[11px] leading-5 text-fg-faint">
                Every result below is a live PyNEC solve against the device you have
                loaded. The commentary is the recording&apos;s, and it reasons about the
                phone it was captured on, so its anchor names and clearances are that
                run&apos;s, not this one&apos;s.
              </p>
            </div>
          </div>
        </div>
      )}

      {agentFellBack && (
        // The orchestrator restarts a dead agent channel on the built-in
        // heuristic so a demo always ends with a result. Saying so is the
        // whole point: a run that looks like Devin's but isn't is worse than
        // no run at all.
        <div className="shrink-0 px-4 pt-3">
          <div className="flex gap-2.5 rounded-md border border-warn/45 bg-warn/10 px-3 py-2.5">
            <AlertMark className="mt-px shrink-0 text-warn" />
            <div className="min-w-0">
              <p className="text-[11px] font-semibold text-warn">
                Devin did not run — the heuristic finished this study
              </p>
              <p className="mt-1 text-[11px] leading-5 text-fg-muted">
                The Devin channel failed before the first solve, so the built-in heuristic
                proposed the placements below. The simulations are real PyNEC solves; the
                reasoning that chose them is not Devin&apos;s. The API error is in the
                transcript.
              </p>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="shrink-0 px-4 pt-3">
          <div className="flex gap-2.5 rounded-md border border-fail/45 bg-fail/10 px-3 py-2.5">
            <AlertMark className="mt-px shrink-0 text-fail" />
            <p className="min-w-0 text-[11px] leading-5 text-fg">{error}</p>
          </div>
        </div>
      )}

      <div ref={feedRef} className="min-h-0 flex-1 overflow-y-auto">
        {specOpen && (
          <div className="border-b border-ink-800 px-4 pb-4 pt-4">
            <label htmlFor="antenna-spec" className={LABEL}>
              Antenna spec
            </label>
            <textarea
              id="antenna-spec"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) run();
              }}
              spellCheck={false}
              placeholder={
                "2.4 GHz Wi-Fi antenna on the bottom edge. 6 mm clear of the battery, VSWR under 2 in band, efficiency above 55%."
              }
              className="mt-2 min-h-[7.5rem] w-full resize-y rounded-md border border-ink-700 bg-ink-900 px-3 py-2.5 text-[12px] leading-6 text-fg outline-none transition placeholder:text-fg-muted focus:border-accent"
            />
            <p className="mt-2 text-[11px] leading-5 text-fg-muted">
              Solved as wire antennas — monopole or IFA over the chassis ground plane — so a
              candidate comes back in under a second. State the target, the clearance and the
              limits; a spec, not an essay.
            </p>

            <h3 className={`mt-5 ${LABEL}`}>Run with</h3>
            <div
              role="radiogroup"
              aria-label="Agent that runs the study"
              className="mt-2 divide-y divide-ink-800 overflow-hidden rounded-md border border-ink-800"
            >
              {AGENT_CHOICES.map((choice) => {
                const on = agent === choice.id;
                return (
                  <button
                    key={choice.id}
                    type="button"
                    role="radio"
                    aria-checked={on}
                    disabled={running}
                    onClick={() => setAgent(choice.id)}
                    className={`flex w-full gap-2.5 px-3 py-2.5 text-left transition disabled:cursor-not-allowed ${
                      on ? "bg-ink-850" : "hover:bg-ink-900"
                    }`}
                  >
                    <span
                      className={`mt-0.5 flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border ${
                        on ? "border-accent" : "border-ink-600"
                      }`}
                    >
                      {on && <span className="h-1.5 w-1.5 rounded-full bg-accent" />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-baseline gap-2">
                        <span className="text-[12px] font-medium text-fg">{choice.name}</span>
                        <span className="ml-auto shrink-0 font-mono text-[10px] text-fg-muted">
                          {choice.meta}
                        </span>
                      </span>
                      <span className="mt-0.5 block text-[11px] leading-5 text-fg-muted">
                        {choice.blurb}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
            {agent === "devin" && (
              <p className="mt-2 text-[11px] leading-5 text-fg-muted">
                A live run spends a run of quota and holds this rail for about two and a half
                minutes. Replay plays back the same agent&apos;s reasoning, instantly and free.
              </p>
            )}

            {!!bandShorts.length && (
              <p className="mt-4 text-[11px] leading-5 text-fg-muted">
                Studying <span className="font-mono text-fg">{bandShorts.join(" · ")}</span> — the
                bands enabled on the device.
              </p>
            )}

            {/* The study answers "where"; this decides whether it also draws
                the answer. Kept beside the spec because it is part of what you
                are asking for, and it costs seconds the run has already spent
                by the time it matters. */}
            <label
              className={`mt-4 flex cursor-pointer gap-2.5 rounded-md border px-3 py-2.5 transition ${
                wantMedia ? "border-ink-600 bg-ink-850" : "border-ink-800 hover:bg-ink-900"
              }`}
            >
              <input
                type="checkbox"
                checked={wantMedia}
                disabled={running}
                onChange={(e) => setWantMedia(e.target.checked)}
                className="peer sr-only"
              />
              <span
                aria-hidden
                className={`mt-px flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-[3px] border transition peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-accent ${
                  wantMedia ? "border-accent bg-accent" : "border-ink-600"
                }`}
              >
                {wantMedia && (
                  <svg viewBox="0 0 10 10" className="h-2.5 w-2.5 text-ink-950" fill="none" stroke="currentColor" strokeWidth="1.8">
                    <path d="M1.5 5.2l2.2 2.2L8.5 2.6" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </span>
              <span className="min-w-0">
                <span className="text-[12px] font-medium text-fg">Render evidence</span>
                <span className="mt-0.5 block text-[11px] leading-5 text-fg-muted">
                  Draw a placement map for each band, the winner inside the mesh, its response,
                  and the field leaving it — for this device, after the study concludes.
                </span>
              </span>
            </label>

            <div className="mt-3 flex items-center gap-3">
              <button
                type="button"
                onClick={run}
                disabled={!canRun}
                title="Run the placement study (Cmd + Enter)"
                className="flex flex-1 items-center justify-center gap-2 rounded-md bg-accent px-3 py-2.5 text-[12px] font-semibold text-ink-950 transition hover:brightness-110 active:brightness-95 disabled:cursor-not-allowed disabled:bg-ink-800 disabled:text-fg-muted"
              >
                {running ? (
                  <>
                    <Spinner />
                    Running
                  </>
                ) : (
                  `Run study · ${agentName(agent)}`
                )}
              </button>
              {started && (
                <button
                  type="button"
                  onClick={() => setEditingSpec(false)}
                  className="shrink-0 text-[11px] text-fg-muted transition hover:text-fg"
                >
                  Cancel
                </button>
              )}
            </div>
            {!running && blocker && (
              <p className="mt-2 text-[11px] leading-5 text-warn">{blocker}</p>
            )}
          </div>
        )}

        {!started ? (
          <div className="px-4 py-6">
            <h3 className="text-[12px] font-semibold text-fg">What happens when you run</h3>
            <ol className="mt-3 space-y-3">
              {[
                "Kevin reads the loaded device — board, battery, keep-outs — and proposes a placement for every enabled band.",
                "PyNEC solves each candidate against the chassis and returns S11, bandwidth, efficiency and VSWR.",
                "Candidates that miss the spec are re-tuned and re-solved until they hold, and the winning placement lands in the viewport with its report.",
              ].map((text, i) => (
                <li key={i} className="flex gap-3">
                  <span className="w-3 shrink-0 font-mono text-[11px] leading-6 text-fg-muted">
                    {i + 1}
                  </span>
                  <p className="text-[12px] leading-6 text-fg-muted">{text}</p>
                </li>
              ))}
            </ol>
            <p className="mt-4 text-[11px] leading-5 text-fg-muted">
              The agent&apos;s reasoning appears here as it happens; the numbers go to Results.
            </p>
          </div>
        ) : (
          <div className="space-y-3 px-4 py-4">
            {transcript.map((m) => (
              <TranscriptLine key={m.id} line={read(m)} />
            ))}
            {planning && (
              <div className="think-in flex items-center gap-2 pt-1">
                <Spinner className="text-accent" />
                <span className="text-[11px] text-fg-muted">Planning candidate placements…</span>
              </div>
            )}
            {!transcript.length && !planning && (
              <p className="text-[11px] leading-5 text-fg-muted">
                Waiting for the agent&apos;s first message.
              </p>
            )}
          </div>
        )}
      </div>

      {!!jobs.length && (
        <div className="shrink-0 border-t border-ink-800 px-4 py-2.5">
          <div className="flex items-baseline justify-between">
            <span className="text-[11px] text-fg-muted">Solves</span>
            <span className="font-mono text-[11px] text-fg-muted">
              {solved}/{jobs.length}
              {failedJobs > 0 && <span className="text-fail"> · {failedJobs} failed</span>}
            </span>
          </div>
          <div className="mt-1.5 flex gap-px" aria-hidden="true">
            {jobs.map((j) => (
              <span
                key={j.job_id}
                title={`${j.candidate_id} — ${j.status}`}
                className={`h-1 flex-1 rounded-[1px] ${
                  j.status === "complete"
                    ? "bg-accent-dim"
                    : j.status === "failed"
                      ? "bg-fail"
                      : j.status === "running"
                        ? "animate-pulse bg-accent"
                        : "bg-ink-700"
                }`}
              />
            ))}
          </div>
        </div>
      )}

      {running && (
        <form
          className="shrink-0 border-t border-ink-800 px-4 py-3"
          onSubmit={(e) => {
            e.preventDefault();
            const t = note.trim();
            if (!t) return;
            setNote("");
            void sendNote(t);
          }}
        >
          <label htmlFor="agent-note" className={LABEL}>
            Note to the agent
          </label>
          <div className="mt-2 flex gap-2">
            <input
              id="agent-note"
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. prefer the bottom edge, the top is crowded"
              className="min-w-0 flex-1 rounded-md border border-ink-700 bg-ink-900 px-2.5 py-2 text-[12px] text-fg outline-none transition placeholder:text-fg-muted focus:border-accent"
            />
            <button
              type="submit"
              disabled={!note.trim()}
              className="shrink-0 rounded-md border border-ink-700 px-3 text-[12px] text-fg transition hover:border-accent disabled:cursor-not-allowed disabled:border-ink-800 disabled:text-fg-muted"
            >
              Send
            </button>
          </div>
          <p className="mt-1.5 text-[11px] leading-5 text-fg-muted">
            Lands with the agent&apos;s next iteration; it does not restart the run.
          </p>
        </form>
      )}
    </div>
  );
}
