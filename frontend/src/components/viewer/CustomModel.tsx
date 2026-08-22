"use client";

import { useGLTF } from "@react-three/drei";
import { useMemo } from "react";
import * as THREE from "three";
import { H } from "@/lib/device";
import { SCALE } from "@/lib/geometry";
import { useApp } from "@/lib/store";

/**
 * Renders a user-supplied Blender export in place of the procedural handset.
 * The model is auto-centred and scaled so its tallest axis matches the device
 * height from the spec, which keeps candidate pins and keep-out volumes aligned
 * even when the exporter's units differ.
 */
export function CustomModel({ url }: { url: string }) {
  const { scene } = useGLTF(url);
  const selectComponent = useApp((s) => s.selectComponent);
  const hoverComponent = useApp((s) => s.hoverComponent);

  const { object, fit } = useMemo(() => {
    const clone = scene.clone(true);
    const box = new THREE.Box3().setFromObject(clone);
    const size = new THREE.Vector3();
    const center = new THREE.Vector3();
    box.getSize(size);
    box.getCenter(center);
    const tallest = Math.max(size.x, size.y, size.z) || 1;
    const s = (H * SCALE) / tallest;
    return { object: clone, fit: { s, center } };
  }, [scene]);

  return (
    <group
      scale={fit.s}
      position={[-fit.center.x * fit.s, -fit.center.y * fit.s, -fit.center.z * fit.s]}
      onClick={(e) => {
        e.stopPropagation();
        selectComponent(e.object.name || null);
      }}
      onPointerOver={(e) => {
        e.stopPropagation();
        hoverComponent(e.object.name || null);
      }}
      onPointerOut={() => hoverComponent(null)}
    >
      <primitive object={object} />
    </group>
  );
}
