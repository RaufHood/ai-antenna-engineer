"use client";

import { useGLTF } from "@react-three/drei";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import { SCALE } from "@/lib/geometry";
import { useApp } from "@/lib/store";

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

/**
 * How far a part travels when the view is fully exploded, as a fraction of the
 * device's longest dimension. Big enough that the stack visibly comes apart,
 * small enough that the phone stays one object on screen rather than a cloud.
 */
const EXPLODE_REACH = 0.42;


/**
 * Parts near the mid-plane have almost no signed offset of their own, so a
 * linear spread leaves the middle of the stack welded together while the outer
 * layers fly. Easing the magnitude pulls those middle layers out early and
 * lets the outer ones finish the journey.
 */
function ease(t: number): number {
  return Math.sign(t) * Math.pow(Math.abs(t), 0.55);
}

export function DeviceXray({ url = "/models/iphone15pro.glb" }: { url?: string }) {
  const { scene } = useGLTF(url);
  const explode = useApp((s) => s.explode);
  const offsets = useRef<{ line: THREE.Object3D; dir: THREE.Vector3 }[]>([]);

  // Build the line art once per model: EdgesGeometry is expensive over 191
  // meshes, and nothing about it changes as the user orbits.
  const { group, fit, spread } = useMemo(() => {
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

    // Where each part goes when the stack comes apart. A phone is a laminate,
    // so the separation is mostly along its thinnest axis — that is the
    // direction a teardown lays the parts out in, and the only one with room
    // between layers to see into. The other two axes get a light fan so parts
    // sharing a layer do not stay welded edge to edge.
    const whole = new THREE.Box3().setFromObject(out);
    const size = whole.getSize(new THREE.Vector3());
    const mid = whole.getCenter(new THREE.Vector3());
    const axes: (keyof THREE.Vector3 & ("x" | "y" | "z"))[] = ["x", "y", "z"];
    const stack = axes.reduce((a, b) => (size[a] <= size[b] ? a : b));
    const reach = Math.max(size.x, size.y, size.z) * EXPLODE_REACH;

    const spread: { line: THREE.Object3D; dir: THREE.Vector3 }[] = [];
    const partBox = new THREE.Box3();
    const partMid = new THREE.Vector3();
    for (const line of out.children) {
      partBox.setFromObject(line);
      partBox.getCenter(partMid);
      const dir = new THREE.Vector3();
      for (const axis of axes) {
        const half = size[axis] / 2 || 1;
        const t = (partMid[axis] - mid[axis]) / half;   // -1..1 within the device
        dir[axis] = axis === stack ? ease(t) * reach : t * reach * 0.16;
      }
      spread.push({ line, dir });
    }

    // The export is in millimetres on Blender's native axes (x width,
    // y length, z thickness), which is exactly the frame lib/geometry.ts
    // works in — so the scale is SCALE itself, not a fit. Fitting by the
    // tallest axis silently rescales the model whenever the spec's height
    // and the mesh's height disagree, which slides every candidate pin off
    // the geometry it is supposed to sit on.
    // Centre on the un-exploded stack: recomputing it as parts move would drag
    // the whole device across the viewport while the user drags the slider.
    return { group: out, fit: { s: SCALE, center: mid.clone() }, spread };
  }, [scene]);

  // Applied outside the memo so dragging the slider costs 191 vector writes,
  // not 191 EdgesGeometry rebuilds.
  offsets.current = spread;
  useEffect(() => {
    for (const { line, dir } of offsets.current) {
      line.position.set(dir.x * explode, dir.y * explode, dir.z * explode);
    }
  }, [explode, spread]);

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
