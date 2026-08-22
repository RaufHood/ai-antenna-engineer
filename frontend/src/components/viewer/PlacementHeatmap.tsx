"use client";

import { useMemo } from "react";
import * as THREE from "three";
import { H, T, W } from "@/lib/device";
import { SCALE } from "@/lib/geometry";
import { scorePoint } from "@/lib/rf";
import { useApp } from "@/lib/store";

const COLD = new THREE.Color("#dc2626");
const MID = new THREE.Color("#f59e0b");
const HOT = new THREE.Color("#22c55e");

function ramp(t: number) {
  const c = new THREE.Color();
  if (t < 0.5) c.copy(COLD).lerp(MID, t / 0.5);
  else c.copy(MID).lerp(HOT, (t - 0.5) / 0.5);
  return c;
}

/**
 * Placement-quality field sampled over the back surface for the focused band.
 * Green regions have enough clearance and chassis length; red regions sit over
 * the battery, camera or ground plane.
 */
export function PlacementHeatmap() {
  const spec = useApp((s) => s.spec);
  const show = useApp((s) => s.showHeatmap);
  const focusBand = useApp((s) => s.focusBand);
  const enabled = useApp((s) => s.enabledBands);
  const explode = useApp((s) => s.explode);

  const bandId = focusBand ?? enabled[0];
  const band = spec.requirements.bands.find((b) => b.id === bandId);

  const geometry = useMemo(() => {
    if (!band) return null;
    const nx = 56;
    const ny = 112;
    const g = new THREE.PlaneGeometry(W * SCALE, H * SCALE, nx, ny);
    const pos = g.attributes.position;
    const colors = new Float32Array(pos.count * 3);
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i) / SCALE + W / 2;
      const y = pos.getY(i) / SCALE + H / 2;
      const s = scorePoint(spec, band, [x, y, T * 0.5]);
      const c = ramp(s.total);
      colors[i * 3] = c.r;
      colors[i * 3 + 1] = c.g;
      colors[i * 3 + 2] = c.b;
    }
    g.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    return g;
  }, [spec, band]);

  if (!show || !geometry) return null;

  return (
    <mesh
      geometry={geometry}
      position={[0, 0, -(T / 2) * SCALE - 0.02 - explode * 1.6]}
    >
      <meshBasicMaterial
        vertexColors
        transparent
        opacity={0.82}
        side={THREE.DoubleSide}
        toneMapped={false}
      />
    </mesh>
  );
}
