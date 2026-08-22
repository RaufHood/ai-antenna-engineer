"use client";

import { Html, Line } from "@react-three/drei";
import { useMemo } from "react";
import * as THREE from "three";
import { toScene } from "@/lib/geometry";
import { useApp } from "@/lib/store";

/** Coupling between placed antennas, drawn pair-by-pair with the S21 figure. */
export function IsolationArcs() {
  const show = useApp((s) => s.showIsolation);
  const isolation = useApp((s) => s.isolation);
  const candidates = useApp((s) => s.candidates);
  const limit = useApp((s) => s.spec.requirements.isolation_db_max);
  const viewMode = useApp((s) => s.viewMode);
  const selected = useApp((s) => s.selectedCandidate);

  const arcs = useMemo(() => {
    // Ten pairs of arcs is unreadable, so show the coupling that matters:
    // everything touching the selected antenna, or just the failures.
    const relevant = selected
      ? isolation.filter((p) => p.a === selected || p.b === selected)
      : isolation.filter((p) => p.db > limit);

    return relevant
      .map((pair) => {
        const a = candidates.find((c) => c.candidate_id === pair.a);
        const b = candidates.find((c) => c.candidate_id === pair.b);
        if (!a || !b) return null;
        const pa = new THREE.Vector3(...toScene(a.position_mm));
        const pb = new THREE.Vector3(...toScene(b.position_mm));
        const mid = pa.clone().add(pb).multiplyScalar(0.5);
        mid.z += 0.55 + pa.distanceTo(pb) * 0.12;
        const curve = new THREE.QuadraticBezierCurve3(pa, mid, pb);
        return {
          ...pair,
          points: curve.getPoints(40),
          mid: curve.getPoint(0.5),
          ok: pair.db <= limit,
        };
      })
      .filter(Boolean) as {
      a: string;
      b: string;
      db: number;
      points: THREE.Vector3[];
      mid: THREE.Vector3;
      ok: boolean;
    }[];
  }, [isolation, candidates, limit, selected]);

  if (!show || viewMode !== "system" || !arcs.length) return null;

  return (
    <group>
      {arcs.map((arc) => (
        <group key={`${arc.a}-${arc.b}`}>
          <Line
            points={arc.points}
            color={arc.ok ? "#64748b" : "#ef4444"}
            lineWidth={arc.ok ? 1 : 2}
            dashed
            dashSize={0.05}
            gapSize={0.04}
            transparent
            opacity={arc.ok ? 0.5 : 0.95}
          />
          <Html center position={arc.mid} zIndexRange={[15, 5]}>
            <div
              className={`pointer-events-none rounded px-1.5 py-0.5 font-mono text-[9px] ${
                arc.ok
                  ? "bg-slate-900/80 text-slate-300"
                  : "bg-red-600/90 font-bold text-white"
              }`}
            >
              S21 {arc.db} dB
            </div>
          </Html>
        </group>
      ))}
    </group>
  );
}
