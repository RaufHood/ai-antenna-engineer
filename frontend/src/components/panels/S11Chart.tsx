"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import {
  BW_LEVEL_DB,
  bandwidthSpan,
  niceTicks,
  verdictOf,
} from "@/lib/evidence";
import { useApp } from "@/lib/store";
import type { BandRequirement, SimResult } from "@/lib/types";
import { VerdictChip } from "./Verdict";

/**
 * Reflection against frequency for the candidate under inspection — the piece
 * of evidence the whole loop exists to produce.
 *
 * Drawn by hand rather than by a chart library so every mark is deliberate and
 * every colour is a token: the target band window, the S11 the design has to
 * stay under, where it actually resonates, and how much usable bandwidth that
 * leaves. The accent draws the selected trace and nothing else; pass/fail
 * colour states the verdict; the material colours belong to the device.
 */

const PAD = { top: 16, right: 14, bottom: 30, left: 44 };

function Quiet({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center px-6 text-center text-[11px] leading-relaxed text-fg-muted">
      <p className="max-w-[26ch]">{children}</p>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="truncate text-[9px] uppercase tracking-[0.1em] text-fg-muted">{label}</dt>
      <dd className="truncate font-mono text-[11px] text-fg">{value}</dd>
    </div>
  );
}

function useSize<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setSize((s) =>
        Math.abs(s.w - width) < 0.5 && Math.abs(s.h - height) < 0.5
          ? s
          : { w: width, h: height },
      );
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return { ref, ...size };
}

function Plot({
  res,
  band,
  others,
}: {
  res: SimResult;
  band: BandRequirement;
  others: SimResult[];
}) {
  const { ref, w, h } = useSize<HTMLDivElement>();
  const clip = `s11-clip-${useId().replace(/:/g, "")}`;

  const g = useMemo(() => {
    const plotW = w - PAD.left - PAD.right;
    const plotH = h - PAD.top - PAD.bottom;
    if (plotW < 60 || plotH < 50) return null;

    const curves = [res, ...others].map((r) => r.s11_curve).filter((c) => c.length > 1);
    if (!curves.length) return null;
    const fAll = curves.flat().map((p) => p.f_ghz);
    let x0 = Math.min(band.f_low_ghz, ...fAll);
    let x1 = Math.max(band.f_high_ghz, ...fAll);
    const padX = Math.max((x1 - x0) * 0.04, 1e-4);
    x0 -= padX;
    x1 += padX;

    const dbMin = Math.min(
      ...curves.flat().map((p) => p.s11_db),
      band.s11_db_max,
      BW_LEVEL_DB,
    );
    const y0 = Math.max(-60, Math.min(-15, Math.floor((dbMin - 2) / 5) * 5));

    const X = (f: number) => PAD.left + ((f - x0) / (x1 - x0)) * plotW;
    const Y = (db: number) => PAD.top + ((0 - db) / (0 - y0)) * plotH;
    const path = (c: SimResult["s11_curve"]) =>
      c.map((p, i) => `${i ? "L" : "M"}${X(p.f_ghz).toFixed(1)},${Y(p.s11_db).toFixed(1)}`).join("");

    const dbStep = y0 <= -40 ? 10 : 5;
    const yTicks: number[] = [];
    for (let v = 0; v >= y0; v -= dbStep) yTicks.push(v);

    return {
      plotW,
      plotH,
      X,
      Y,
      y0,
      path,
      xTicks: niceTicks(x0, x1, Math.max(2, Math.floor(plotW / 78))),
      yTicks,
      decimals: x1 - x0 < 1 ? 2 : 1,
      span: bandwidthSpan(res.s11_curve),
    };
  }, [w, h, res, others, band]);

  return (
    <div ref={ref} className="relative min-h-0 flex-1">
      {g && (
        <svg width={w} height={h} className="absolute inset-0" role="img"
          aria-label={`S11 against frequency. Resonance ${res.resonant_ghz.toFixed(3)} gigahertz at ${res.s11_min_db.toFixed(1)} decibels, target ${band.s11_db_max} decibels across ${band.f_low_ghz} to ${band.f_high_ghz} gigahertz.`}
        >
          <defs>
            <clipPath id={clip}>
              <rect x={PAD.left} y={PAD.top} width={g.plotW} height={g.plotH} />
            </clipPath>
          </defs>

          {/* The band the design has to work in. */}
          <rect
            x={g.X(band.f_low_ghz)}
            y={PAD.top}
            width={Math.max(g.X(band.f_high_ghz) - g.X(band.f_low_ghz), 1)}
            height={g.plotH}
            className="fill-ink-800"
          />
          {[band.f_low_ghz, band.f_high_ghz].map((f) => (
            <line
              key={f}
              x1={g.X(f)}
              x2={g.X(f)}
              y1={PAD.top}
              y2={PAD.top + g.plotH}
              className="stroke-ink-600"
              strokeWidth={1}
              shapeRendering="crispEdges"
            />
          ))}
          {g.X(band.f_high_ghz) - g.X(band.f_low_ghz) > 56 && (
            <text
              x={(g.X(band.f_low_ghz) + g.X(band.f_high_ghz)) / 2}
              y={PAD.top + 10}
              textAnchor="middle"
              className="fill-fg-muted text-[9px] uppercase tracking-[0.08em]"
            >
              target band
            </text>
          )}

          {/* Grid + axes. */}
          {g.yTicks.map((db) => (
            <line
              key={db}
              x1={PAD.left}
              x2={PAD.left + g.plotW}
              y1={g.Y(db)}
              y2={g.Y(db)}
              className="stroke-ink-800"
              strokeWidth={1}
              shapeRendering="crispEdges"
            />
          ))}
          {g.xTicks.map((f) => (
            <g key={f}>
              <line
                x1={g.X(f)}
                x2={g.X(f)}
                y1={PAD.top + g.plotH}
                y2={PAD.top + g.plotH + 3}
                className="stroke-ink-600"
                strokeWidth={1}
                shapeRendering="crispEdges"
              />
              <text
                x={g.X(f)}
                y={PAD.top + g.plotH + 14}
                textAnchor="middle"
                className="fill-fg-muted font-mono text-[10px]"
              >
                {f.toFixed(g.decimals)}
              </text>
            </g>
          ))}
          {g.yTicks.map((db) => (
            <text
              key={db}
              x={PAD.left - 6}
              y={g.Y(db) + 3.5}
              textAnchor="end"
              className="fill-fg-muted font-mono text-[10px]"
            >
              {db}
            </text>
          ))}
          <line
            x1={PAD.left}
            x2={PAD.left + g.plotW}
            y1={PAD.top + g.plotH}
            y2={PAD.top + g.plotH}
            className="stroke-ink-600"
            strokeWidth={1}
            shapeRendering="crispEdges"
          />
          <text
            x={PAD.left + g.plotW / 2}
            y={h - 4}
            textAnchor="middle"
            className="fill-fg-muted text-[10px]"
          >
            Frequency (GHz)
          </text>
          <text
            x={-(PAD.top + g.plotH / 2)}
            y={11}
            transform="rotate(-90)"
            textAnchor="middle"
            className="fill-fg-muted text-[10px]"
          >
            S11 (dB)
          </text>

          <g clipPath={`url(#${clip})`}>
            {/* The other candidates simulated for this band, for scale. */}
            {others.map((o, i) => (
              <path
                key={`${o.candidate_id}-${i}`}
                d={g.path(o.s11_curve)}
                fill="none"
                className="stroke-ink-600"
                strokeWidth={1}
                strokeLinejoin="round"
              />
            ))}

            {/* The limit this design has to stay under. */}
            <line
              x1={PAD.left}
              x2={PAD.left + g.plotW}
              y1={g.Y(band.s11_db_max)}
              y2={g.Y(band.s11_db_max)}
              className="stroke-warn"
              strokeWidth={1}
              strokeDasharray="3 3"
            />

            {/* Usable bandwidth: where the sweep stays under -6 dB. */}
            {g.span && (
              <g className="stroke-fg-muted" strokeWidth={1}>
                <line
                  x1={g.X(g.span.lo)}
                  x2={g.X(g.span.hi)}
                  y1={g.Y(BW_LEVEL_DB)}
                  y2={g.Y(BW_LEVEL_DB)}
                />
                {[g.span.lo, g.span.hi].map((f) => (
                  <line
                    key={f}
                    x1={g.X(f)}
                    x2={g.X(f)}
                    y1={g.Y(BW_LEVEL_DB) - 4}
                    y2={g.Y(BW_LEVEL_DB) + 4}
                  />
                ))}
              </g>
            )}

            <path
              d={g.path(res.s11_curve)}
              fill="none"
              className="stroke-accent"
              strokeWidth={1.6}
              strokeLinejoin="round"
              strokeLinecap="round"
            />

            {/* Resonance. */}
            <line
              x1={g.X(res.resonant_ghz)}
              x2={g.X(res.resonant_ghz)}
              y1={g.Y(res.s11_min_db)}
              y2={PAD.top + g.plotH}
              className="stroke-accent-dim"
              strokeWidth={1}
              strokeDasharray="2 3"
            />
            <circle
              cx={g.X(res.resonant_ghz)}
              cy={g.Y(res.s11_min_db)}
              r={2.5}
              className="fill-accent"
            />
          </g>

          <text
            x={PAD.left + 4}
            y={g.Y(band.s11_db_max) - 4}
            className="fill-warn font-mono text-[10px]"
          >
            target {band.s11_db_max} dB
          </text>
          {g.span && (
            <text
              x={(g.X(g.span.lo) + g.X(g.span.hi)) / 2}
              y={g.Y(BW_LEVEL_DB) - 7}
              textAnchor="middle"
              className="fill-fg-muted font-mono text-[10px]"
            >
              {Math.round(res.bandwidth_mhz)} MHz at {BW_LEVEL_DB} dB
            </text>
          )}
          <text
            x={g.X(res.resonant_ghz) + 5}
            y={g.Y(res.s11_min_db) - 6}
            textAnchor={g.X(res.resonant_ghz) > PAD.left + g.plotW - 40 ? "end" : "start"}
            className="fill-accent font-mono text-[10px]"
          >
            f₀ {res.resonant_ghz.toFixed(3)}
          </text>
        </svg>
      )}
    </div>
  );
}

export function S11Chart() {
  const spec = useApp((s) => s.spec);
  const results = useApp((s) => s.results);
  const candidates = useApp((s) => s.candidates);
  const anchors = useApp((s) => s.anchors);
  const placements = useApp((s) => s.placements);
  const selected = useApp((s) => s.selectedCandidate);

  const sel = candidates.find((c) => c.candidate_id === selected);
  const band = spec.requirements.bands.find((b) => b.id === sel?.band_id);
  const res = sel ? results[sel.candidate_id] : undefined;
  const v = verdictOf(res);

  const others = sel
    ? candidates
        .filter((c) => c.band_id === sel.band_id && c.candidate_id !== sel.candidate_id)
        .map((c) => results[c.candidate_id])
        .filter((r): r is SimResult => r?.status === "complete" && r.s11_curve.length > 1)
    : [];

  if (!sel || !band) {
    return <Quiet>Select a candidate to see its S11 sweep.</Quiet>;
  }
  if (v === "pending") {
    return (
      <Quiet>
        Solving this placement. The sweep appears when the solver returns.
      </Quiet>
    );
  }
  if (v === "error" || !res || res.s11_curve.length < 2) {
    return (
      <Quiet>
        No sweep for this placement — {res?.notes?.trim() || "the solver returned nothing"}.
        Pick another candidate, or re-run the study.
      </Quiet>
    );
  }

  const anchor = anchors.find((a) => a.id === sel.anchor_id);
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="px-3 pt-2.5">
        <div className="flex items-baseline gap-2">
          <h3 className="truncate text-[12px] font-medium text-fg">{band.name}</h3>
          <span className="shrink-0 font-mono text-[10px] text-fg-muted">
            {band.f_low_ghz.toFixed(3)}–{band.f_high_ghz.toFixed(3)} GHz
          </span>
          <span className="ml-auto">
            <VerdictChip v={v} />
          </span>
        </div>
        <p className="mt-0.5 truncate text-[10px] text-fg-muted">
          {sel.antenna_type} {sel.length_mm} mm at {anchor?.label ?? sel.anchor_id}
          {placements[band.id] === sel.candidate_id && (
            <span className="text-accent"> · selected for the final design</span>
          )}
          {others.length > 0 && ` · ${others.length} other candidate${others.length > 1 ? "s" : ""} in grey`}
        </p>
      </div>

      <Plot res={res} band={band} others={others} />

      <dl className="grid grid-cols-6 gap-x-2 border-t border-ink-800 px-3 py-1.5">
        <Stat label="f₀ GHz" value={res.resonant_ghz.toFixed(3)} />
        <Stat label="S11 dB" value={res.s11_min_db.toFixed(1)} />
        <Stat label="BW MHz" value={Math.round(res.bandwidth_mhz).toString()} />
        <Stat label="η" value={`${Math.round(res.efficiency * 100)}%`} />
        <Stat label="VSWR" value={res.vswr.toFixed(2)} />
        <Stat label="Gain dBi" value={res.peak_gain_dbi.toFixed(1)} />
      </dl>
    </div>
  );
}
