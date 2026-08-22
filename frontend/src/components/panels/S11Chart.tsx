"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useApp } from "@/lib/store";

export function S11Chart() {
  const spec = useApp((s) => s.spec);
  const results = useApp((s) => s.results);
  const candidates = useApp((s) => s.candidates);
  const selected = useApp((s) => s.selectedCandidate);

  const sel = candidates.find((c) => c.candidate_id === selected);
  const band = spec.requirements.bands.find((b) => b.id === sel?.band_id);

  const siblings = sel
    ? candidates
        .filter((c) => c.band_id === sel.band_id)
        .map((c) => ({ cand: c, res: results[c.candidate_id] }))
        .filter((x) => x.res?.status === "complete")
    : [];

  if (!sel || !band || !siblings.length) {
    return (
      <div className="flex h-full items-center justify-center px-4 text-center text-[11px] text-slate-600">
        Run a placement study, then select an antenna to see its S11 sweep.
      </div>
    );
  }

  return (
    <div className="h-full w-full">
      <div className="px-3 pt-2 text-[10px] uppercase tracking-wider text-slate-500">
        S11 - {band.name}
      </div>
      <ResponsiveContainer width="100%" height="88%">
        <LineChart margin={{ top: 8, right: 16, bottom: 18, left: 0 }}>
          <CartesianGrid stroke="#1e293b" strokeDasharray="2 3" />
          <XAxis
            type="number"
            dataKey="f_ghz"
            domain={["dataMin", "dataMax"]}
            tick={{ fill: "#64748b", fontSize: 9 }}
            tickFormatter={(v) => v.toFixed(2)}
            label={{
              value: "GHz",
              position: "insideBottomRight",
              fill: "#475569",
              fontSize: 9,
            }}
          />
          <YAxis
            dataKey="s11_db"
            domain={[(d: number) => Math.min(d, -30), 0]}
            tick={{ fill: "#64748b", fontSize: 9 }}
            width={38}
            label={{
              value: "dB",
              angle: -90,
              position: "insideLeft",
              fill: "#475569",
              fontSize: 9,
            }}
          />
          <Tooltip
            contentStyle={{
              background: "#0f172a",
              border: "1px solid #334155",
              borderRadius: 6,
              fontSize: 11,
            }}
            labelFormatter={(v) => `${Number(v).toFixed(3)} GHz`}
            formatter={(v) => [`${Number(v).toFixed(2)} dB`, "S11"]}
          />
          <ReferenceArea
            x1={band.f_low_ghz}
            x2={band.f_high_ghz}
            fill={band.color}
            fillOpacity={0.12}
          />
          <ReferenceLine
            y={band.s11_db_max}
            stroke="#f59e0b"
            strokeDasharray="4 3"
            label={{
              value: `${band.s11_db_max} dB`,
              fill: "#f59e0b",
              fontSize: 9,
              position: "right",
            }}
          />
          {siblings.map(({ cand, res }) => {
            const isSel = cand.candidate_id === selected;
            return (
              <Line
                key={cand.candidate_id}
                data={res.s11_curve}
                dataKey="s11_db"
                type="monotone"
                dot={false}
                isAnimationActive={false}
                stroke={isSel ? band.color : "#334155"}
                strokeWidth={isSel ? 2.2 : 1}
                strokeOpacity={isSel ? 1 : 0.7}
              />
            );
          })}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
