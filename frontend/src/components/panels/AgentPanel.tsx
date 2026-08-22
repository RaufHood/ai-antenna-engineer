"use client";

import { useEffect, useRef } from "react";
import { useApp } from "@/lib/store";

const SUGGESTIONS = [
  "Where should the antennas be placed in this phone, and what type for each band?",
  "Keep the low-band antenna away from the user's hand and re-check SAR.",
  "Which placement gives the best isolation between the 2.4 GHz and n78 antennas?",
];

export function AgentPanel() {
  const prompt = useApp((s) => s.prompt);
  const setPrompt = useApp((s) => s.setPrompt);
  const startRun = useApp((s) => s.startRun);
  const poll = useApp((s) => s.poll);
  const running = useApp((s) => s.running);
  const planning = useApp((s) => s.planning);
  const messages = useApp((s) => s.messages);
  const jobs = useApp((s) => s.jobs);
  const error = useApp((s) => s.error);
  const runId = useApp((s) => s.runId);
  const feedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!running || !runId) return;
    const t = setInterval(() => void poll(), 600);
    return () => clearInterval(t);
  }, [running, runId, poll]);

  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight });
  }, [messages.length]);

  const done = jobs.filter((j) => j.status === "complete").length;

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-2 border-b border-slate-800 px-3 py-2">
        <span className="relative flex h-2 w-2">
          <span
            className={`absolute inline-flex h-full w-full rounded-full ${
              running ? "animate-ping bg-sky-400" : "bg-slate-600"
            }`}
          />
          <span
            className={`relative inline-flex h-2 w-2 rounded-full ${
              running ? "bg-sky-500" : "bg-slate-600"
            }`}
          />
        </span>
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Design agent
        </h2>
        <span className="ml-auto font-mono text-[10px] text-slate-500">
          {runId ? `${done}/${jobs.length} sims` : "idle"}
        </span>
      </header>

      <div ref={feedRef} className="flex-1 space-y-2 overflow-y-auto p-3">
        {!messages.length && (
          <div className="space-y-2">
            <p className="text-xs leading-relaxed text-slate-500">
              Ask the agent where to place the antennas. It reads the component
              geometry and the band targets on the left, proposes candidate
              positions, runs a solver sweep per candidate, and ranks the
              results.
            </p>
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => setPrompt(s)}
                className="w-full rounded-md border border-slate-800 bg-slate-900/60 px-2.5 py-2 text-left text-[11px] text-slate-300 hover:border-sky-600 hover:text-sky-200"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {messages.map((m) => (
          <div
            key={m.id}
            className={`rounded-md px-2.5 py-2 text-[11px] leading-relaxed ${
              m.role === "user"
                ? "border border-sky-800/60 bg-sky-950/40 text-sky-100"
                : m.kind === "result"
                  ? "border-l-2 border-emerald-600/70 bg-slate-900/70 font-mono text-[10px] text-slate-300"
                  : m.kind === "step"
                    ? "border-l-2 border-slate-700 bg-slate-900/50 text-slate-400"
                    : "bg-slate-900/70 text-slate-200"
            }`}
          >
            {m.text}
          </div>
        ))}

        {planning && (
          <div className="animate-pulse text-[11px] text-slate-500">
            planning candidate placements...
          </div>
        )}
      </div>

      {!!jobs.length && (
        <div className="border-t border-slate-800 px-3 py-2">
          <div className="mb-1 flex justify-between text-[10px] text-slate-500">
            <span>Simulation queue</span>
            <span className="font-mono">
              {done}/{jobs.length}
            </span>
          </div>
          <div className="flex flex-wrap gap-1">
            {jobs.map((j) => (
              <span
                key={j.job_id}
                title={j.candidate_id}
                className={`h-1.5 w-5 rounded-sm ${
                  j.status === "complete"
                    ? "bg-emerald-500"
                    : j.status === "running"
                      ? "animate-pulse bg-sky-500"
                      : "bg-slate-700"
                }`}
              />
            ))}
          </div>
        </div>
      )}

      <div className="border-t border-slate-800 p-3">
        {error && (
          <div className="mb-2 rounded bg-red-950/60 px-2 py-1 text-[10px] text-red-300">
            {error}
          </div>
        )}
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={3}
          className="w-full resize-none rounded-md border border-slate-700 bg-slate-900 px-2.5 py-2 text-[11px] leading-relaxed text-slate-200 outline-none focus:border-sky-500"
        />
        <button
          onClick={() => void startRun()}
          disabled={running}
          className="mt-2 w-full rounded-md bg-sky-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
        >
          {running ? "Agent working..." : "Run placement study"}
        </button>
      </div>
    </div>
  );
}
