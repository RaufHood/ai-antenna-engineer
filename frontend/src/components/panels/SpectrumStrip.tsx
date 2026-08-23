"use client";

import { useApp } from "@/lib/store";
import { detuneMhz, rankKey, verdictOf } from "@/lib/evidence";
import type { SimResult } from "@/lib/types";
import { VerdictDot } from "./Verdict";

/**
 * Band coverage: the one question the candidate table cannot answer at a
 * glance — of the bands this study was asked to cover, which ones now have a
 * design that lands inside the window, and how far off the rest are.
 *
 * The old log-frequency strip is gone. It painted the requested bands as
 * coloured blocks on a 0.6-6.5 GHz axis, where an 70 MHz cellular window is
 * two pixels wide and a 40 MHz miss is invisible — decoration where the
 * detuning is the whole point. Each band now gets its own track, scaled to
 * its own window, so "in band" and "80 MHz low" look different.
 */

/** How much spectrum either side of the window a track shows, in window widths. */
const CONTEXT = 1.6;
const MAX_CONTEXT = 8;

const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi);

export function BandCoverage() {
  const spec = useApp((s) => s.spec);
  const candidates = useApp((s) => s.candidates);
  const results = useApp((s) => s.results);
  const placements = useApp((s) => s.placements);
  const selected = useApp((s) => s.selectedCandidate);
  const selectCandidate = useApp((s) => s.selectCandidate);

  const cells = spec.requirements.bands
    .filter((band) => candidates.some((c) => c.band_id === band.id))
    .map((band) => {
      const mine = candidates.filter((c) => c.band_id === band.id);
      const done = mine
        .map((c) => results[c.candidate_id])
        .filter((r): r is SimResult => r?.status === "complete");
      const chosenId = placements[band.id];
      const best =
        (chosenId && results[chosenId]?.status === "complete" ? results[chosenId] : undefined) ??
        [...done].sort((a, b) => rankKey(b, band) - rankKey(a, band))[0];
      const solving = mine.some((c) => results[c.candidate_id]?.status === "running");
      const centre = (band.f_low_ghz + band.f_high_ghz) / 2;
      const width = band.f_high_ghz - band.f_low_ghz;
      const half = Math.min(
        Math.max(width * CONTEXT, ...done.map((r) => Math.abs(r.resonant_ghz - centre) * 1.15)),
        width * MAX_CONTEXT,
      );
      const at = (f: number) => clamp(((f - (centre - half)) / (2 * half)) * 100, 0, 100);
      return {
        band,
        best,
        done,
        at,
        verdict: verdictOf(best),
        solving,
        holds: mine.some((c) => c.candidate_id === selected),
      };
    });

  if (!cells.length) return null;

  const met = cells.filter((c) => c.verdict === "pass").length;

  return (
    <section className="border-b border-ink-800 px-4 pb-2 pt-2.5" title="Each track spans its own band window. Ticks are simulated resonances; the bold tick is the best candidate.">
      <div className="mb-2 flex items-baseline gap-3">
        <h2 className="text-[11px] font-medium text-fg">
          {met} of {cells.length} bands met
        </h2>
      </div>

      <div className="flex items-stretch gap-1">
        {cells.map(({ band, best, done, at, verdict, holds, solving }) => {
          const detune = best ? detuneMhz(best, band) : 0;
          return (
            <button
              key={band.id}
              type="button"
              disabled={!best}
              aria-current={holds || undefined}
              onClick={() => {
                const chosen = placements[band.id];
                const id =
                  chosen ??
                  [...candidates.filter((c) => c.band_id === band.id)].sort(
                    (a, b) =>
                      rankKey(results[b.candidate_id], band) -
                      rankKey(results[a.candidate_id], band),
                  )[0]?.candidate_id;
                if (id) selectCandidate(id);
              }}
              title={
                best
                  ? `${band.name} · window ${band.f_low_ghz}-${band.f_high_ghz} GHz · best resonance ${best.resonant_ghz.toFixed(3)} GHz${
                      detune === 0
                        ? " (inside the window)"
                        : ` (${Math.abs(detune).toFixed(0)} MHz ${detune < 0 ? "low" : "high"})`
                    } · ${done.length} candidate${done.length === 1 ? "" : "s"} simulated`
                  : `${band.name} · no completed simulation yet`
              }
              className={`min-w-0 flex-1 rounded-sm px-2 py-1.5 text-left transition-colors disabled:cursor-default ${
                holds ? "bg-accent/10" : "enabled:hover:bg-ink-900"
              }`}
            >
              <span className="flex items-baseline gap-1.5">
                <VerdictDot v={verdict} />
                <span className={`truncate text-[11px] ${holds ? "text-fg" : "text-fg-muted"}`}>
                  {band.short}
                </span>
                <span className="ml-auto shrink-0 font-mono text-[10px] text-fg-muted">
                  {best
                    ? `${best.s11_min_db.toFixed(1)} dB`
                    : solving
                      ? "solving"
                      : "queued"}
                </span>
              </span>

              <span className="relative mt-1.5 block h-2.5">
                <span className="absolute inset-x-0 top-1/2 h-px bg-ink-700" />
                <span
                  className="absolute inset-y-0 border-x border-ink-600 bg-ink-800"
                  style={{
                    left: `${at(band.f_low_ghz)}%`,
                    width: `${Math.max(at(band.f_high_ghz) - at(band.f_low_ghz), 1)}%`,
                  }}
                />
                {done.map((r) => (
                  <span
                    key={r.candidate_id}
                    className="absolute inset-y-1 w-px bg-ink-600"
                    style={{ left: `${at(r.resonant_ghz)}%` }}
                  />
                ))}
                {best && (
                  <span
                    className={`absolute inset-y-0 w-0.5 -translate-x-px ${
                      verdict === "pass" ? "bg-pass" : "bg-fail"
                    }`}
                    style={{ left: `${at(best.resonant_ghz)}%` }}
                  />
                )}
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
