"use client";

import { useApp } from "@/lib/store";

const F_MIN = 0.6;
const F_MAX = 6.5;

function pos(f: number) {
  const t =
    (Math.log10(Math.max(f, F_MIN)) - Math.log10(F_MIN)) /
    (Math.log10(F_MAX) - Math.log10(F_MIN));
  // Rounded so the server and client render byte-identical inline styles.
  return +(Math.min(Math.max(t, 0), 1) * 100).toFixed(3);
}

const TICKS = [0.6, 0.8, 1, 1.5, 2, 3, 4, 5, 6];

/** Log-scale spectrum showing target bands and where each design resonated. */
export function SpectrumStrip() {
  const spec = useApp((s) => s.spec);
  const enabled = useApp((s) => s.enabledBands);
  const placements = useApp((s) => s.placements);
  const results = useApp((s) => s.results);
  const candidates = useApp((s) => s.candidates);
  const selectCandidate = useApp((s) => s.selectCandidate);
  const selected = useApp((s) => s.selectedCandidate);

  return (
    <div className="px-3 py-2">
      <div className="mb-1 flex items-baseline justify-between">
        <span className="text-[10px] uppercase tracking-wider text-slate-500">
          Spectrum coverage
        </span>
        <span className="font-mono text-[9px] text-slate-600">
          log scale, {F_MIN}-{F_MAX} GHz
        </span>
      </div>

      <div className="relative h-11 rounded-md border border-slate-800 bg-slate-950">
        {spec.requirements.bands
          .filter((b) => enabled.includes(b.id))
          .map((b) => {
            const left = pos(b.f_low_ghz);
            const width = Math.max(pos(b.f_high_ghz) - left, 0.6);
            return (
              <div
                key={b.id}
                title={`${b.name} ${b.f_low_ghz}-${b.f_high_ghz} GHz`}
                className="absolute top-1 h-5 rounded-sm"
                style={{
                  left: `${left}%`,
                  width: `${width}%`,
                  background: b.color,
                  opacity: 0.35,
                  border: `1px solid ${b.color}`,
                }}
              />
            );
          })}

        {Object.entries(placements).map(([bandId, candId]) => {
          const r = results[candId];
          const band = spec.requirements.bands.find((b) => b.id === bandId);
          const cand = candidates.find((c) => c.candidate_id === candId);
          if (!r || !band || !cand || r.status !== "complete") return null;
          const inBand =
            r.resonant_ghz >= band.f_low_ghz && r.resonant_ghz <= band.f_high_ghz;
          return (
            <button
              key={candId}
              onClick={() => selectCandidate(candId)}
              title={`${band.name}: resonance ${r.resonant_ghz.toFixed(2)} GHz, ${r.s11_min_db.toFixed(1)} dB`}
              className="absolute top-0 h-7 w-0.5 -translate-x-1/2"
              style={{
                left: `${pos(r.resonant_ghz)}%`,
                background: inBand ? "#ffffff" : "#ef4444",
                boxShadow:
                  selected === candId ? "0 0 6px 1px rgba(255,255,255,0.8)" : "none",
              }}
            />
          );
        })}

        <div className="absolute bottom-0 left-0 right-0 h-4">
          {TICKS.map((t) => (
            <span
              key={t}
              className="absolute -translate-x-1/2 font-mono text-[8px] text-slate-600"
              style={{ left: `${pos(t)}%` }}
            >
              {t}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
