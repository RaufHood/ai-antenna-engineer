"use client";

import { useEffect, useRef, useState } from "react";
import { KevinMark } from "@/components/Logo";
import { useApp } from "@/lib/store";
import { SectionTitle } from "./SpecPanel";

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
  const agent = useApp((s) => s.agent);
  const setAgent = useApp((s) => s.setAgent);
  const agentFellBack = useApp((s) => s.agentFellBack);
  const sendNote = useApp((s) => s.sendNote);
  const [note, setNote] = useState("");
  const feedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!running || !runId) return;
    const t = setInterval(() => void poll(), 600);
    return () => clearInterval(t);
  }, [running, runId, poll]);

  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight });
  }, [messages.length]);

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-3 border-b border-slate-800/80 px-4 py-3">
        <SectionTitle>Agent</SectionTitle>
        <div className="ml-auto flex rounded-md border border-slate-800 p-0.5">
          {(["mock", "replay", "devin"] as const).map((a) => (
            <button
              key={a}
              disabled={running}
              onClick={() => setAgent(a)}
              title={
                a === "devin"
                  ? "Devin, live via the API — costs quota, ~2.5 min"
                  : a === "replay"
                    ? "A recorded live Devin run, played back instantly and free"
                    : "The backend's offline heuristic — fast, but not the agent's reasoning"
              }
              className={`rounded px-2 py-0.5 text-[10px] transition disabled:cursor-not-allowed ${
                agent === a ? "bg-slate-800 text-slate-100" : "text-slate-500 hover:text-slate-300"
              }`}
            >
              {a === "mock" ? "Mock" : a === "replay" ? "Replay" : "Devin"}
            </button>
          ))}
        </div>
      </header>

      {agentFellBack && (
        // The orchestrator restarts a dead agent channel on the built-in
        // heuristic so a demo always ends with a result. Saying so is the
        // whole point: these numbers are not the real agent's work, and a
        // run that looks like Devin's but isn't is worse than no run.
        <div className="mx-4 mt-3 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2">
          <p className="text-[11px] font-medium text-amber-300">
            Devin did not run — heuristic agent finished this
          </p>
          <p className="mt-0.5 text-[10px] leading-relaxed text-amber-200/70">
            The Devin channel failed before the first simulation, so the
            built-in heuristic completed the run. The simulations below are
            real; the reasoning that chose them is not Devin&apos;s. Check the
            feed for the API error.
          </p>
        </div>
      )}

      <div ref={feedRef} className="flex-1 space-y-1.5 overflow-y-auto px-4 py-3">
        {!messages.length && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <KevinMark size={56} className="text-slate-700" />
            <p className="max-w-[240px] text-[11px] leading-relaxed text-slate-500">
              Kevin reads the device geometry and the band targets, proposes
              antenna placements, simulates each one and iterates until the
              design holds up.
            </p>
          </div>
        )}

        {messages.map((m) => (
          <div
            key={m.id}
            className={`rounded-md px-2.5 py-2 text-[11px] leading-relaxed ${
              m.role === "user"
                ? "border border-sky-800/50 bg-sky-950/30 text-sky-100"
                : m.kind === "result"
                  ? "border-l-2 border-emerald-600/60 bg-slate-900/50 font-mono text-[10px] text-slate-400"
                  : m.kind === "step"
                    ? "text-slate-500"
                    : "bg-slate-900/70 text-slate-200"
            }`}
          >
            {m.text}
          </div>
        ))}

        {planning && (
          <div className="animate-pulse text-[11px] text-slate-500">
            planning candidate placements…
          </div>
        )}
      </div>

      {!!jobs.length && (
        <div className="border-t border-slate-800/80 px-4 py-2">
          <div className="flex flex-wrap gap-1">
            {jobs.map((j) => (
              <span
                key={j.job_id}
                title={j.candidate_id}
                className={`h-1.5 w-5 rounded-sm ${
                  j.status === "complete"
                    ? "bg-emerald-500"
                    : j.status === "failed"
                      ? "bg-red-500"
                      : j.status === "running"
                        ? "animate-pulse bg-sky-500"
                        : "bg-slate-800"
                }`}
              />
            ))}
          </div>
        </div>
      )}

      <div className="border-t border-slate-800/80 p-4">
        {error && (
          <div className="mb-2 rounded-md border border-red-900/60 bg-red-950/40 px-2.5 py-2 text-[10px] leading-relaxed text-red-300">
            {error}
          </div>
        )}
        {running && runId ? (
          <form
            className="flex gap-1.5"
            onSubmit={(e) => {
              e.preventDefault();
              const t = note.trim();
              if (!t) return;
              setNote("");
              void sendNote(t);
            }}
          >
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Note to the agent mid-run, e.g. prefer the bottom edge"
              className="min-w-0 flex-1 rounded-md border border-slate-800 bg-slate-900 px-2.5 py-2 text-[11px] text-slate-200 outline-none focus:border-sky-500"
            />
            <button
              type="submit"
              className="rounded-md border border-slate-800 px-3 text-[11px] text-slate-300 transition hover:border-sky-500"
            >
              Send
            </button>
          </form>
        ) : (
          <>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={3}
              className="w-full resize-none rounded-md border border-slate-800 bg-slate-900 px-2.5 py-2 text-[11px] leading-relaxed text-slate-200 outline-none focus:border-sky-500"
            />
            <button
              onClick={() => void startRun()}
              className="mt-2 w-full rounded-md bg-sky-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-sky-500"
            >
              Run placement study
            </button>
          </>
        )}
      </div>
    </div>
  );
}
