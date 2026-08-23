"use client";

import { useGLTF } from "@react-three/drei";
import { useMemo } from "react";
import * as THREE from "three";

import { SCALE } from "@/lib/geometry";

/**
 * The real device, drawn as x-ray line art — the viewport twin of the beauty
 * renders in rf/runs/demo/media (placement_beauty_*.png, orbit_beauty.gif).
 *
 * The placeholder handset was a stack of RoundedBoxes: fine as scaffolding,
 * but it shows a generic slab where the whole point of the project is that the
 * antenna is fighting *this* phone's titanium frame, battery and shield cans.
 * This renders the actual 191-part iPhone 15 Pro export instead.
 *
 * Why edges and not shaded surfaces:
 *   - 191 nested solids render as an opaque blob; you cannot see the antenna,
 *     which sits inside. Edges leave the interior legible.
 *   - Silhouettes are what a mechanical drawing shows, and this *is* a
 *     mechanical decision.
 *   - It matches the still and animation renders exactly, so the deck and the
 *     live app look like one product.
 *
 * Colour carries meaning, not decoration — the same three families the physics
 * uses (rf/placement.py splits conductors from dielectrics at 1e4 S/m):
 *   steel blue  conductor  — a mirror: detunes the antenna, blocks radiation
 *   mint        dielectric — a radome: the field passes through
 *   coral       battery    — the classic antenna killer, called out on purpose
 *
 * The family comes from the node name's `__suffix`, which the Blender export
 * carries over from the material key, so nothing has to be looked up at
 * runtime.
 */

const COLORS = {
  metal: "#8c9eff",
  dielectric: "#69f0ae",
  battery: "#ff8a65",
} as const;

type Family = keyof typeof COLORS;

const METAL_KEYS = [
  "stainless", "steel", "alumin", "copper", "titan", "gold", "metal", "cfrp",
];

/** Node names look like `battery.cell__lipo` — the suffix is the material. */
function familyOf(name: string): Family {
  const key = (name.split("__")[1] ?? name).toLowerCase();
  if (key.includes("lipo") || key.includes("batt") || key.includes("lithium")) {
    return "battery";
  }
  return METAL_KEYS.some((m) => key.includes(m)) ? "metal" : "dielectric";
}

/** Edges thick enough to read, dim enough not to shout. Battery leads. */
const STYLE: Record<Family, { opacity: number; threshold: number }> = {
  metal: { opacity: 0.55, threshold: 25 },
  dielectric: { opacity: 0.34, threshold: 30 },
  battery: { opacity: 0.85, threshold: 18 },
};

export function DeviceXray({
  url = "/models/iphone15pro.glb",
  heightMm,
}: {
  url?: string;
  heightMm: number;
}) {
  const { scene } = useGLTF(url);

  // Build the line art once per model: EdgesGeometry is expensive over 191
  // meshes, and nothing about it changes as the user orbits.
  const { group, fit } = useMemo(() => {
    const out = new THREE.Group();
    const source = scene.clone(true);

    source.traverse((child) => {
      const mesh = child as THREE.Mesh;
      if (!mesh.isMesh || !mesh.geometry) return;

      const family = familyOf(mesh.name);
      const { opacity, threshold } = STYLE[family];

      // thresholdAngle keeps coplanar triangles from drawing a wire cage:
      // only real creases and silhouettes survive, which is what Freestyle
      // does in the offline renders.
      const edges = new THREE.EdgesGeometry(mesh.geometry, threshold);
      const line = new THREE.LineSegments(
        edges,
        new THREE.LineBasicMaterial({
          color: COLORS[family],
          transparent: true,
          opacity,
          depthWrite: false, // let far edges show through near ones: the x-ray
        }),
      );
      line.name = mesh.name;
      mesh.updateWorldMatrix(true, false);
      line.applyMatrix4(mesh.matrixWorld);
      out.add(line);
    });

    // Fit to the spec's device height so candidate pins and keep-outs, which
    // are placed in millimetres, land where they belong.
    const box = new THREE.Box3().setFromObject(out);
    const size = new THREE.Vector3();
    const center = new THREE.Vector3();
    box.getSize(size);
    box.getCenter(center);
    const tallest = Math.max(size.x, size.y, size.z) || 1;
    return {
      group: out,
      fit: { s: (heightMm * SCALE) / tallest, center },
    };
  }, [scene, heightMm]);

  return (
    <group
      scale={fit.s}
      position={[
        -fit.center.x * fit.s,
        -fit.center.y * fit.s,
        -fit.center.z * fit.s,
      ]}
    >
      <primitive object={group} />
    </group>
  );
}

useGLTF.preload("/models/iphone15pro.glb");
