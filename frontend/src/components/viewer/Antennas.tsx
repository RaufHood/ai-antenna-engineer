"use client";

import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import * as THREE from "three";
import { SCALE, toScene } from "@/lib/geometry";
import { useApp } from "@/lib/store";
import type { Candidate } from "@/lib/types";
import { useBandMap, useVisibleCandidates } from "./useCandidates";

function RadiationPulse({ color }: { color: string }) {
  const a = useRef<THREE.Mesh>(null);
  const b = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    for (const [i, ref] of [a, b].entries()) {
      if (!ref.current) continue;
      const phase = (t * 0.55 + i * 0.5) % 1;
      const s = 0.08 + phase * 0.75;
      ref.current.scale.set(s, s, s);
      const m = ref.current.material as THREE.MeshBasicMaterial;
      m.opacity = 0.5 * (1 - phase) ** 1.6;
    }
  });
  return (
    <>
      {[a, b].map((ref, i) => (
        <mesh key={i} ref={ref} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[1, 0.03, 8, 48]} />
          <meshBasicMaterial color={color} transparent opacity={0.4} toneMapped={false} />
        </mesh>
      ))}
    </>
  );
}

function AntennaMarker({ cand }: { cand: Candidate }) {
  const bands = useBandMap();
  const band = bands[cand.band_id];
  const selected = useApp((s) => s.selectedCandidate);
  const select = useApp((s) => s.selectCandidate);
  const results = useApp((s) => s.results);
  const showLabels = useApp((s) => s.showLabels);

  const [W, H] = useApp((s) => s.spec.board.size_mm);

  const res = results[cand.candidate_id];
  const isSel = selected === cand.candidate_id;
  const running = res?.status === "running";
  const done = res?.status === "complete";
  const pass = done && res.meets_requirements;

  const p = toScene(cand.position_mm);
  const along = cand.position_mm[1] < H * 0.25 || cand.position_mm[1] > H * 0.75;
  const maxLen = (along ? W : H) - 12;
  const len = Math.min(cand.length_mm, maxLen);
  const meandered = cand.length_mm > maxLen;

  const color = done ? (pass ? band.color : "#ef4444") : band.color;
  const emissive = running ? 1.4 : isSel ? 1.1 : 0.55;

  const radiator: [number, number, number] = along
    ? [len * SCALE, 3 * SCALE, 0.8 * SCALE]
    : [3 * SCALE, len * SCALE, 0.8 * SCALE];

  // Keep the radiator inside the outline when it sits next to a corner.
  const cx = Math.min(Math.max(cand.position_mm[0], len / 2 + 5), W - len / 2 - 5);
  const cy = Math.min(Math.max(cand.position_mm[1], len / 2 + 5), H - len / 2 - 5);
  const rp = toScene(
    along ? [cx, cand.position_mm[1], cand.position_mm[2]] : [cand.position_mm[0], cy, cand.position_mm[2]],
  );

  return (
    <group>
      <mesh position={rp}>
        <boxGeometry args={radiator} />
        <meshStandardMaterial
          color={color}
          emissive={new THREE.Color(color)}
          emissiveIntensity={emissive}
          metalness={0.6}
          roughness={0.3}
          toneMapped={false}
        />
      </mesh>

      <mesh
        position={p}
        onClick={(e) => {
          e.stopPropagation();
          select(isSel ? null : cand.candidate_id);
        }}
        onPointerOver={(e) => {
          e.stopPropagation();
          document.body.style.cursor = "pointer";
        }}
        onPointerOut={() => (document.body.style.cursor = "auto")}
      >
        <sphereGeometry args={[isSel ? 0.055 : 0.04, 20, 20]} />
        <meshStandardMaterial
          color={color}
          emissive={new THREE.Color(color)}
          emissiveIntensity={emissive}
          toneMapped={false}
        />
      </mesh>

      {(isSel || running) && (
        <group position={p} scale={0.9}>
          <RadiationPulse color={color} />
        </group>
      )}

      {showLabels && (
        <Html center position={[p[0], p[1], p[2] + 0.14]} zIndexRange={[30, 10]}>
          <button
            onClick={() => select(isSel ? null : cand.candidate_id)}
            className={`-translate-y-6 whitespace-nowrap rounded border px-1.5 py-0.5 text-[9px] font-semibold shadow-lg backdrop-blur transition ${
              isSel
                ? "border-white/60 bg-slate-900/95 text-white"
                : "border-white/10 bg-slate-950/75 text-slate-300 hover:border-white/40"
            }`}
            style={{ borderLeftColor: color, borderLeftWidth: 3 }}
          >
            {band.short}
            {isSel && ` - ${cand.antenna_type}`}
            {isSel && meandered && (
              <span className="text-slate-400"> meandered</span>
            )}
            <span className="ml-1 font-mono font-normal text-slate-400">
              {running
                ? "sim..."
                : done
                  ? `${res.s11_min_db.toFixed(0)} dB`
                  : `${(cand.prior * 100).toFixed(0)}%`}
            </span>
          </button>
        </Html>
      )}
    </group>
  );
}

export function Antennas() {
  const show = useApp((s) => s.showPins);
  const visible = useVisibleCandidates();
  if (!show) return null;
  // Nothing is drawn until the agent has proposed something. The dots that
  // used to sit here marked the anchor set, and they read as antennas already
  // placed in a phone nobody had asked about yet — the device is the subject
  // before a run, and the legal region has a proper home in the placement map,
  // where it is drawn with its scores instead of as anonymous specks.
  return (
    <group>
      {visible.map((c) => (
        <AntennaMarker key={c.candidate_id} cand={c} />
      ))}
    </group>
  );
}
