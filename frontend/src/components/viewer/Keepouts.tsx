"use client";

import { Edges } from "@react-three/drei";
import { useMemo } from "react";
import * as THREE from "three";
import { boxIntersection, sceneCenter, sceneSize } from "@/lib/geometry";
import { useApp } from "@/lib/store";
import type { Bbox } from "@/lib/types";
import { useBandMap, useVisibleCandidates } from "./useCandidates";

function Volume({
  bbox,
  color,
  opacity,
  dashed,
}: {
  bbox: Bbox;
  color: string;
  opacity: number;
  dashed?: boolean;
}) {
  const size = sceneSize(bbox);
  const center = sceneCenter(bbox);
  return (
    <mesh position={center}>
      <boxGeometry args={size} />
      <meshBasicMaterial
        color={color}
        transparent
        opacity={opacity}
        depthWrite={false}
        side={THREE.DoubleSide}
        toneMapped={false}
      />
      <Edges color={color} scale={1.001} threshold={15} linewidth={dashed ? 1 : 2} />
    </mesh>
  );
}

/**
 * Antenna keep-out volumes. Where two keep-outs overlap, the intersection is
 * drawn solid red: two bands are competing for the same clearance.
 */
export function Keepouts() {
  const show = useApp((s) => s.showKeepouts);
  const selected = useApp((s) => s.selectedCandidate);
  const bands = useBandMap();
  const visible = useVisibleCandidates();

  const conflicts = useMemo(() => {
    const out: Bbox[] = [];
    for (let i = 0; i < visible.length; i++) {
      for (let k = i + 1; k < visible.length; k++) {
        if (visible[i].band_id === visible[k].band_id) continue;
        const x = boxIntersection(visible[i].keepout_mm, visible[k].keepout_mm);
        if (x) out.push(x);
      }
    }
    return out;
  }, [visible]);

  if (!show) return null;

  return (
    <group>
      {visible.map((c) => (
        <Volume
          key={c.candidate_id}
          bbox={c.keepout_mm}
          color={bands[c.band_id].color}
          opacity={selected === c.candidate_id ? 0.16 : 0.07}
          dashed={selected !== c.candidate_id}
        />
      ))}
      {conflicts.map((b, i) => (
        <Volume key={`x${i}`} bbox={b} color="#ef4444" opacity={0.4} />
      ))}
    </group>
  );
}
