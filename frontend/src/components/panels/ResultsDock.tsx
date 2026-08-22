"use client";

import { useMemo, useState } from "react";
import { useApp } from "@/lib/store";
import { Markdown } from "./Markdown";
import { S11Chart } from "./S11Chart";
import { SpectrumStrip } from "./SpectrumStrip";

function Verdict({ ok }: { ok: boolean }) {
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${
        ok ? "bg-emerald-500/15 text-emerald-400" : "bg-red-500/15 text-red-400"
      }`}
    >
      {ok ? "PASS" : "FAIL"}
    </span>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center px-4 text-center text-[11px] text-slate-600">
      {children}
    </div>
  );
}

/** Every simulated candidate, chosen ones first, then by band and S11. */
function ResultsTable() {
  const candidates = useApp((s) => s.candidates);
  const results = useApp((s) => s.results);
  const placements = useApp((s) => s.placements);
  const anchors = useApp((s) => s.anchors);
  const bands = useApp((s) => s.spec.requirements.bands);
  const selected = useApp((s) => s.selectedCandidate);
  const select = useApp((s) => s.selectCandidate);

  const rows = useMemo(
    () =>
      candidates
        .map((c) => ({
          c,
          r: results[c.candidate_id],
          band: bands.find((b) => b.id === c.band_id),
          anchor: anchors.find((a) => a.id === c.anchor_id),
          chosen: Object.values(placements).includes(c.candidate_id),
        }))
        .sort(
          (a, b) =>
            Number(b.chosen) - Number(a.chosen) ||
            (a.band?.f_low_ghz ?? 0) - (b.band?.f_low_ghz ?? 0) ||
            (a.r?.s11_min_db ?? 0) - (b.r?.s11_min_db ?? 0),
        ),
    [candidates, results, placements, bands, anchors],
  );

  if (!rows.length) return <Empty>Simulated candidates appear here as the agent proposes them.</Empty>;

  const num = "px-2 py-1.5 text-right font-mono text-slate-400";
  return (
    <div className="h-full overflow-auto">
      <table className="w-full border-collapse text-[10px]">
        <thead className="sticky top-0 bg-slate-950 text-slate-500">
          <tr className="[&>th]:whitespace-nowrap [&>th]:px-2 [&>th]:py-1.5 [&>th]:text-left [&>th]:font-medium">
            <th>Band</th>
            <th>Position</th>
            <th>Type</th>
            <th className="text-right">S11 dB</th>
            <th className="text-right">f₀ GHz</th>
            <th className="text-right">BW MHz</th>
            <th className="text-right">Eff</th>
            <th className="text-right">VSWR</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ c, r, band, anchor, chosen }) => {
            const isSel = selected === c.candidate_id;
            const pending = !r || r.status === "queued" || r.status === "running";
            const failed = r?.status === "failed";
            return (
              <tr
                key={c.candidate_id}
                onClick={() => select(c.candidate_id)}
                title={`${c.position_mm.map((v) => v.toFixed(1)).join(", ")} mm${c.rationale ? ` — ${c.rationale}` : ""}`}
                className={`cursor-pointer border-t border-slate-900 transition ${
                  isSel ? "bg-sky-500/10" : "hover:bg-slate-900/70"
                } ${pending ? "opacity-50" : ""}`}
              >
                <td className="whitespace-nowrap px-2 py-1.5">
                  <span className="flex items-center gap-1.5">
                    <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: band?.color }} />
                    <span className="text-slate-300">{band?.short ?? c.band_id}</span>
                    {chosen && (
                      <span className="rounded bg-sky-500/20 px-1 text-[8px] font-bold text-sky-300">
                        CHOSEN
                      </span>
                    )}
                  </span>
                </td>
                <td className="whitespace-nowrap px-2 py-1.5 text-slate-400">
                  {anchor?.label ?? c.anchor_id}
                </td>
                <td className="whitespace-nowrap px-2 py-1.5 font-mono text-slate-400">
                  {c.antenna_type} {c.length_mm} mm
                </td>
                {pending || failed ? (
                  <td colSpan={5} className="px-2 py-1.5 font-mono text-slate-600">
                    {failed ? r.notes || "solve failed" : r?.status === "running" ? "simulating…" : "queued"}
                  </td>
                ) : (
                  <>
                    <td className={`${num} text-slate-200`}>{r.s11_min_db.toFixed(1)}</td>
                    <td className={num}>{r.resonant_ghz.toFixed(3)}</td>
                    <td className={num}>{Math.round(r.bandwidth_mhz)}</td>
                    <td className={num}>{(r.efficiency * 100).toFixed(0)}%</td>
                    <td className={num}>{r.vswr.toFixed(2)}</td>
                  </>
                )}
                <td className="px-2 py-1.5 text-right">
                  {!pending && !failed && <Verdict ok={r.meets_requirements} />}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** The agent's own report.md, once the run has finished. */
function ReportView() {
  const report = useApp((s) => s.report);
  const running = useApp((s) => s.running);
  const runId = useApp((s) => s.runId);

  if (!report) {
    return (
      <Empty>
        {running ? "The report is written when the run finishes." : "Run a placement study to get a report."}
      </Empty>
    );
  }
  return (
    <div className="h-full overflow-auto px-4 py-3">
      <Markdown source={report} />
      <a
        href={`/api/run?runId=${runId}&artifact=report.md`}
        target="_blank"
        rel="noreferrer"
        className="mt-4 inline-block text-[10px] text-sky-400 hover:text-sky-300"
      >
        open report.md ↗
      </a>
    </div>
  );
}

export function ResultsDock() {
  const [tab, setTab] = useState<"results" | "report">("results");
  const report = useApp((s) => s.report);
  const jobs = useApp((s) => s.jobs);

  return (
    <div className="flex h-full flex-col">
      <SpectrumStrip />
      <div className="flex items-center gap-1 border-b border-slate-800/80 px-3">
        {(["results", "report"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`border-b-2 px-2 py-1.5 text-[11px] font-medium capitalize transition ${
              tab === t
                ? "border-sky-500 text-sky-300"
                : "border-transparent text-slate-500 hover:text-slate-300"
            }`}
          >
            {t}
            {t === "results" && jobs.length > 0 && (
              <span className="ml-1.5 font-mono text-[9px] text-slate-500">{jobs.length}</span>
            )}
            {t === "report" && report && (
              <span className="ml-1.5 inline-block h-1.5 w-1.5 rounded-full bg-emerald-400 align-middle" />
            )}
          </button>
        ))}
      </div>

      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 border-r border-slate-800/80">
          {tab === "results" ? <ResultsTable /> : <ReportView />}
        </div>
        <div className="w-[340px] shrink-0">
          <S11Chart />
        </div>
      </div>
    </div>
  );
}
