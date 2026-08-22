"use client";

import { useMemo, useState } from "react";
import { useApp } from "@/lib/store";
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

function ResultsTable() {
  const candidates = useApp((s) => s.candidates);
  const results = useApp((s) => s.results);
  const jobs = useApp((s) => s.jobs);
  const placements = useApp((s) => s.placements);
  const bands = useApp((s) => s.spec.requirements.bands);
  const selected = useApp((s) => s.selectedCandidate);
  const select = useApp((s) => s.selectCandidate);
  const storeAnchors = useApp((s) => s.anchors);

  const rows = useMemo(() => {
    const queued = jobs.map((j) => j.candidate_id);
    return candidates
      .filter((c) => queued.includes(c.candidate_id))
      .map((c) => ({
        c,
        r: results[c.candidate_id],
        band: bands.find((b) => b.id === c.band_id),
        anchor: storeAnchors.find((a) => a.id === c.anchor_id),
        chosen: Object.values(placements).includes(c.candidate_id),
      }))
      .sort(
        (a, b) =>
          Number(b.chosen) - Number(a.chosen) ||
          (a.band?.f_low_ghz ?? 0) - (b.band?.f_low_ghz ?? 0) ||
          (a.r?.s11_min_db ?? 0) - (b.r?.s11_min_db ?? 0),
      );
  }, [candidates, results, jobs, placements, bands, storeAnchors]);

  if (!rows.length) {
    return (
      <div className="flex h-full items-center justify-center text-[11px] text-slate-600">
        No simulations yet. Ask the agent to run a placement study.
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto">
      <table className="w-full border-collapse text-[10px]">
        <thead className="sticky top-0 bg-slate-950 text-slate-500">
          <tr className="[&>th]:px-2 [&>th]:py-1.5 [&>th]:text-left [&>th]:font-medium">
            <th>Band</th>
            <th>Position</th>
            <th>Type</th>
            <th className="text-right">S11</th>
            <th className="text-right">f res</th>
            <th className="text-right">BW</th>
            <th className="text-right">Eff</th>
            <th className="text-right">Gain</th>
            <th className="text-right">VSWR</th>
            <th className="text-right">SAR</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ c, r, band, anchor, chosen }) => {
            if (!band) return null;
            const isSel = selected === c.candidate_id;
            const pending = !r || r.status !== "complete";
            return (
              <tr
                key={c.candidate_id}
                onClick={() => select(c.candidate_id)}
                className={`cursor-pointer border-t border-slate-900 transition ${
                  isSel ? "bg-sky-500/10" : "hover:bg-slate-900/70"
                } ${pending ? "opacity-50" : ""}`}
              >
                <td className="px-2 py-1.5">
                  <span className="flex items-center gap-1.5">
                    <span
                      className="h-2 w-2 rounded-full"
                      style={{ background: band.color }}
                    />
                    <span className="text-slate-300">{band.name}</span>
                    {chosen && (
                      <span className="rounded bg-sky-500/20 px-1 text-[8px] font-bold text-sky-300">
                        CHOSEN
                      </span>
                    )}
                  </span>
                </td>
                <td className="px-2 py-1.5 text-slate-400">{anchor?.label ?? c.anchor_id}</td>
                <td className="px-2 py-1.5 font-mono text-slate-400">
                  {c.antenna_type}
                </td>
                <td className="px-2 py-1.5 text-right font-mono text-slate-200">
                  {pending ? "-" : `${r.s11_min_db.toFixed(1)} dB`}
                </td>
                <td className="px-2 py-1.5 text-right font-mono text-slate-400">
                  {pending ? "-" : `${r.resonant_ghz.toFixed(2)}`}
                </td>
                <td className="px-2 py-1.5 text-right font-mono text-slate-400">
                  {pending ? "-" : `${r.bandwidth_mhz}`}
                </td>
                <td className="px-2 py-1.5 text-right font-mono text-slate-400">
                  {pending ? "-" : `${(r.efficiency * 100).toFixed(0)}%`}
                </td>
                <td className="px-2 py-1.5 text-right font-mono text-slate-400">
                  {pending ? "-" : `${r.peak_gain_dbi.toFixed(1)}`}
                </td>
                <td className="px-2 py-1.5 text-right font-mono text-slate-400">
                  {pending ? "-" : r.vswr.toFixed(2)}
                </td>
                <td className="px-2 py-1.5 text-right font-mono text-slate-400">
                  {pending ? "-" : r.sar_w_per_kg.toFixed(2)}
                </td>
                <td className="px-2 py-1.5 text-right">
                  {pending ? (
                    <span className="text-[9px] text-sky-400">
                      {r?.status === "running" ? "running" : "queued"}
                    </span>
                  ) : (
                    <Verdict ok={r.meets_requirements} />
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ReportView() {
  const spec = useApp((s) => s.spec);
  const placements = useApp((s) => s.placements);
  const results = useApp((s) => s.results);
  const candidates = useApp((s) => s.candidates);
  const isolation = useApp((s) => s.isolation);
  const truncated = useApp((s) => s.truncated);
  const runNote = useApp((s) => s.runNote);
  const agentMode = useApp((s) => s.agentMode);

  const entries = Object.entries(placements);
  if (!entries.length) {
    return (
      <div className="flex h-full items-center justify-center text-[11px] text-slate-600">
        The engineering report appears once the study finishes.
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto px-4 py-3 text-[11px] leading-relaxed text-slate-300">
      <h3 className="mb-2 text-xs font-semibold text-slate-100">
        Antenna placement report - {spec.name}
      </h3>
      {truncated && (
        <div className="mb-3 rounded-md border border-amber-800/70 bg-amber-950/40 p-3 text-[10px] text-amber-200">
          Run ended early (wall-clock or budget barrier). Showing best-so-far.
          {runNote ? ` ${runNote}` : ""}
        </div>
      )}
      {!truncated && runNote && (
        <p className="mb-3 text-[11px] text-slate-400">{runNote}</p>
      )}
      {entries.map(([bandId, candId]) => {
        const band = spec.requirements.bands.find((b) => b.id === bandId);
        const c = candidates.find((x) => x.candidate_id === candId);
        const r = results[candId];
        if (!band || !c || !r) return null;
        return (
          <div
            key={bandId}
            className="mb-3 rounded-md border border-slate-800 bg-slate-900/50 p-3"
          >
            <div className="mb-1 flex items-center gap-2">
              <span
                className="h-2 w-2 rounded-full"
                style={{ background: band.color }}
              />
              <span className="font-semibold text-slate-100">{band.name}</span>
              <span className="font-mono text-[10px] text-slate-500">
                {band.f_low_ghz}-{band.f_high_ghz} GHz
              </span>
              <span className="ml-auto">
                <Verdict ok={r.meets_requirements} />
              </span>
            </div>
            <ul className="ml-4 list-disc space-y-0.5 text-slate-400">
              <li>
                <span className="text-slate-200">{c.antenna_type}</span> at{" "}
                <span className="font-mono">
                  [{c.position_mm.map((v) => v.toFixed(1)).join(", ")}] mm
                </span>
                , radiator {c.length_mm} mm, feed at{" "}
                <span className="font-mono">
                  [{c.feed_point_mm.map((v) => v.toFixed(1)).join(", ")}] mm
                </span>
              </li>
              <li>
                Keep-out volume {band.clearance_mm} mm radius:{" "}
                <span className="font-mono">
                  [{c.keepout_mm[0].map((v) => v.toFixed(0)).join(", ")}] to [
                  {c.keepout_mm[1].map((v) => v.toFixed(0)).join(", ")}] mm
                </span>
              </li>
              <li>
                S11 {r.s11_min_db.toFixed(1)} dB at {r.resonant_ghz.toFixed(2)} GHz,
                bandwidth {r.bandwidth_mhz} MHz, VSWR {r.vswr.toFixed(2)}
              </li>
              <li>
                Efficiency {(r.efficiency * 100).toFixed(0)}% (floor{" "}
                {(band.efficiency_min * 100).toFixed(0)}%), peak gain{" "}
                {r.peak_gain_dbi.toFixed(1)} dBi
              </li>
              <li>
                SAR {r.sar_w_per_kg.toFixed(2)} W/kg against the{" "}
                {spec.requirements.sar_limit.standard} limit of{" "}
                {spec.requirements.sar_limit.w_per_kg} W/kg over{" "}
                {spec.requirements.sar_limit.mass_g} g
              </li>
              <li className="text-slate-500">{r.notes}</li>
            </ul>
          </div>
        );
      })}

      {!!isolation.length && (
        <div className="mb-3 rounded-md border border-slate-800 bg-slate-900/50 p-3">
          <div className="mb-1 font-semibold text-slate-100">
            Inter-antenna isolation
          </div>
          <ul className="ml-4 list-disc space-y-0.5 text-slate-400">
            {isolation.map((p) => (
              <li key={`${p.a}-${p.b}`}>
                <span className="font-mono">{p.a}</span> /{" "}
                <span className="font-mono">{p.b}</span>: {p.db} dB{" "}
                {p.db <= spec.requirements.isolation_db_max ? "(ok)" : "(too coupled)"}
              </li>
            ))}
          </ul>
        </div>
      )}

      {agentMode === "local" ? (
        <div className="rounded-md border border-amber-900/50 bg-amber-950/20 p-3 text-[10px] text-amber-200/80">
          Results come from a geometry-driven heuristic model, not a full-wave
          solver. Swap the solver behind /api/run for openEMS before treating any
          of these numbers as engineering data. Hand and head detuning and real SAR
          still require measurement.
        </div>
      ) : (
        <div className="rounded-md border border-slate-800 bg-slate-900/40 p-3 text-[10px] text-slate-500">
          Isolation and keep-outs are computed in the viewer from placed
          candidates. Simulation numbers come from the backend solver.
        </div>
      )}
    </div>
  );
}

export function ResultsDock() {
  const [tab, setTab] = useState<"results" | "report">("results");
  const placements = useApp((s) => s.placements);

  return (
    <div className="flex h-full flex-col bg-slate-950">
      <SpectrumStrip />
      <div className="flex items-center gap-1 border-b border-slate-800 px-3">
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
            {t === "report" && Object.keys(placements).length > 0 && (
              <span className="ml-1.5 rounded-full bg-sky-500/20 px-1.5 text-[9px] text-sky-300">
                {Object.keys(placements).length}
              </span>
            )}
          </button>
        ))}
      </div>

      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 border-r border-slate-800">
          {tab === "results" ? <ResultsTable /> : <ReportView />}
        </div>
        <div className="w-[340px] shrink-0">
          <S11Chart />
        </div>
      </div>
    </div>
  );
}
