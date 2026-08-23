"use client";

import { useMemo, useState } from "react";
import { rankKey, reasonFor, verdictOf } from "@/lib/evidence";
import { useApp } from "@/lib/store";
import type { Anchor, BandRequirement, Candidate, SimResult } from "@/lib/types";
import { Markdown } from "./Markdown";
import { S11Chart } from "./S11Chart";
import { BandCoverage } from "./SpectrumStrip";
import { VerdictWord } from "./Verdict";

/**
 * The evidence dock: every placement the agent simulated, ranked inside its
 * band so the winner is the first row, with the reason it won or lost spelled
 * out — and the selected one drawn as a sweep next to it.
 *
 * It renders only once there is something to compare. Before that the screen
 * belongs to the device.
 */

const COLS =
  "grid grid-cols-[10px_44px_minmax(96px,1fr)_52px_58px_34px_minmax(170px,1.7fr)] items-center gap-x-3";

interface Row {
  cand: Candidate;
  res: SimResult | undefined;
  band: BandRequirement;
  anchor: Anchor | undefined;
  chosen: boolean;
  /** First row of its band group: the winner, and the row that carries the
   *  band label. */
  first: boolean;
}

function CandidateTable() {
  const spec = useApp((s) => s.spec);
  const candidates = useApp((s) => s.candidates);
  const results = useApp((s) => s.results);
  const placements = useApp((s) => s.placements);
  const anchors = useApp((s) => s.anchors);
  const selected = useApp((s) => s.selectedCandidate);
  const select = useApp((s) => s.selectCandidate);
  const vswrMax = spec.requirements.vswr_max;

  const rows = useMemo<Row[]>(() => {
    const out: Row[] = [];
    for (const band of spec.requirements.bands) {
      const mine = candidates
        .filter((c) => c.band_id === band.id)
        .sort(
          (a, b) =>
            rankKey(results[b.candidate_id], band) - rankKey(results[a.candidate_id], band) ||
            b.prior - a.prior,
        );
      mine.forEach((cand, i) => {
        out.push({
          cand,
          res: results[cand.candidate_id],
          band,
          anchor: anchors.find((a) => a.id === cand.anchor_id),
          chosen: placements[band.id] === cand.candidate_id,
          first: i === 0,
        });
      });
    }
    return out;
  }, [spec.requirements.bands, candidates, results, anchors, placements]);

  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <div
        className={`${COLS} sticky top-0 z-10 border-b border-ink-800 bg-ink-950 px-4 py-1.5 text-[10px] uppercase tracking-[0.08em] text-fg-muted`}
      >
        <span />
        <span>Band</span>
        <span>Placement</span>
        <span className="text-right">S11 dB</span>
        <span className="text-right">f₀ GHz</span>
        <span className="text-right">η</span>
        <span>Verdict</span>
      </div>

      {rows.map((row, i) => {
        const { cand, res, band, anchor, chosen, first } = row;
        const v = verdictOf(res);
        const isSel = selected === cand.candidate_id;
        const done = res?.status === "complete";
        // A pending row says so in the verdict column and nowhere else: the
        // dashes already stand for numbers that do not exist yet.
        const pending = v === "pending";
        const reason = pending || !res ? "" : reasonFor(res, band, vswrMax);
        const strong = first || isSel;
        return (
          <button
            key={cand.candidate_id}
            type="button"
            disabled={pending}
            aria-current={isSel || undefined}
            onClick={() => select(cand.candidate_id)}
            title={`${band.name} · ${cand.antenna_type} ${cand.length_mm} mm at ${
              anchor?.label ?? cand.anchor_id
            } (${cand.position_mm.map((n) => n.toFixed(1)).join(", ")} mm)${reason ? `\n${reason}` : ""}${
              cand.rationale ? `\n${cand.rationale}` : ""
            }`}
            className={`${COLS} w-full px-4 py-1.5 text-left text-[11px] transition-colors focus-visible:[outline-offset:-2px] disabled:cursor-default disabled:opacity-80 ${
              isSel ? "" : "enabled:hover:bg-ink-900"
            } ${
              first && i > 0 ? "border-t border-ink-800" : ""
            } ${isSel ? "bg-accent/10" : ""}`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${chosen ? "bg-accent" : "bg-transparent"}`}
              aria-hidden
            />
            <span className={`truncate ${strong ? "text-fg" : "text-fg-muted"}`}>
              {first ? band.short : ""}
            </span>
            <span className={`truncate ${strong ? "text-fg" : "text-fg-muted"}`}>
              {anchor?.label ?? cand.anchor_id}
              <span className="text-fg-muted"> · {cand.antenna_type} {cand.length_mm} mm</span>
            </span>
            <span className={`text-right font-mono ${done ? "text-fg" : "text-fg-muted"}`}>
              {done && res ? res.s11_min_db.toFixed(1) : "—"}
            </span>
            <span className="text-right font-mono text-fg-muted">
              {done && res ? res.resonant_ghz.toFixed(3) : "—"}
            </span>
            <span className="text-right font-mono text-fg-muted">
              {done && res ? `${Math.round(res.efficiency * 100)}%` : "—"}
            </span>
            <span className="flex min-w-0 items-baseline gap-2">
              <VerdictWord
                v={v}
                label={pending ? (res?.status === "running" ? "Solving" : "Queued") : undefined}
              />
              <span className="truncate text-fg-muted">{reason}</span>
              {chosen && <span className="ml-auto shrink-0 text-accent">Selected</span>}
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** The agent's own report.md, once the run has written one. */
function ReportView() {
  const report = useApp((s) => s.report);
  const runId = useApp((s) => s.runId);
  if (!report) return null;
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
      <Markdown source={report} />
      <a
        href={`/api/run?runId=${runId}&artifact=report.md`}
        target="_blank"
        rel="noreferrer"
        className="mt-4 inline-flex items-center gap-1.5 text-[11px] text-accent hover:text-fg"
      >
        Open report.md
        <svg width="11" height="11" viewBox="0 0 12 12" fill="none" aria-hidden>
          <path
            d="M4.5 1.5h6v6M10.5 1.5 5 7M8 9.5v1H1.5v-9h1"
            stroke="currentColor"
            strokeWidth="1.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </a>
    </div>
  );
}

export function ResultsDock() {
  const [tab, setTab] = useState<"results" | "report">("results");
  const candidates = useApp((s) => s.candidates);
  const report = useApp((s) => s.report);
  const running = useApp((s) => s.running);

  if (!candidates.length) {
    return (
      <p className="px-4 py-3 text-[11px] text-fg-muted">
        {running
          ? "Planning placements. Candidates appear here as the agent proposes them."
          : "This run produced no candidates. The agent feed says why."}
      </p>
    );
  }

  const showing = report ? tab : "results";
  return (
    <div className="flex h-full min-h-0 flex-col">
      <BandCoverage />

      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col border-r border-ink-800">
          {report && (
            <div className="flex shrink-0 gap-4 border-b border-ink-800 px-4">
              {(["results", "report"] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTab(t)}
                  aria-current={showing === t || undefined}
                  className={`-mb-px border-b py-1.5 text-[11px] transition-colors ${
                    showing === t
                      ? "border-accent text-fg"
                      : "border-transparent text-fg-muted hover:text-fg"
                  }`}
                >
                  {t === "results" ? `Candidates (${candidates.length})` : "Report"}
                </button>
              ))}
            </div>
          )}
          {showing === "results" ? <CandidateTable /> : <ReportView />}
        </div>

        <aside className="w-[380px] shrink-0">
          <S11Chart />
        </aside>
      </div>
    </div>
  );
}
