"use client";

import { Html, RoundedBox } from "@react-three/drei";
import { Suspense, useMemo } from "react";
import * as THREE from "three";
import { SCALE, sceneCenter, sceneSize } from "@/lib/geometry";
import { useApp } from "@/lib/store";
import type { DeviceComponent } from "@/lib/types";
import { CustomModel } from "./CustomModel";
import { DeviceXray } from "./DeviceXray";

/** The aluminium rim, drawn as four rails so the internals stay visible. */
function FrameRails({
  size,
  material,
}: {
  size: [number, number, number];
  material: React.ReactNode;
}) {
  const [w, h, d] = size;
  const t = 1.8 * SCALE;
  const rails: { pos: [number, number, number]; args: [number, number, number] }[] =
    [
      { pos: [-w / 2 + t / 2, 0, 0], args: [t, h, d] },
      { pos: [w / 2 - t / 2, 0, 0], args: [t, h, d] },
      { pos: [0, -h / 2 + t / 2, 0], args: [w - 2 * t, t, d] },
      { pos: [0, h / 2 - t / 2, 0], args: [w - 2 * t, t, d] },
    ];
  return (
    <>
      {rails.map((r, i) => (
        <RoundedBox
          key={i}
          position={r.pos}
          args={r.args}
          radius={Math.min(0.012, Math.min(...r.args) * 0.35)}
          smoothness={3}
          creaseAngle={0.5}
        >
          {material}
        </RoundedBox>
      ))}
    </>
  );
}

function Part({ c }: { c: DeviceComponent }) {
  const explode = useApp((s) => s.explode);
  const hidden = useApp((s) => s.hidden);
  const selected = useApp((s) => s.selectedComponent);
  const hovered = useApp((s) => s.hoveredComponent);
  const showLabels = useApp((s) => s.showLabels);
  const selectComponent = useApp((s) => s.selectComponent);
  const hoverComponent = useApp((s) => s.hoverComponent);

  const size = useMemo(() => sceneSize(c.bbox_mm), [c.bbox_mm]);
  const center = useMemo(() => sceneCenter(c.bbox_mm), [c.bbox_mm]);

  if (hidden.includes(c.name)) return null;

  const isSel = selected === c.name;
  const isHov = hovered === c.name;
  const dim = selected !== null && !isSel;

  const dir = c.explode ?? [0, 0, 0];
  const pos: [number, number, number] = [
    center[0] + dir[0] * explode * 1.05,
    center[1] + dir[1] * explode * 1.05,
    center[2] + dir[2] * explode * 1.35,
  ];

  const radius = Math.min(0.05, Math.min(...size) * 0.35);
  const glass = c.shape === "glass";
  const opacity = dim ? (c.opacity ?? 1) * 0.2 : (c.opacity ?? 1);

  const material = (
    <meshPhysicalMaterial
      color={c.color}
      metalness={c.metalness ?? 0.4}
      roughness={c.roughness ?? 0.5}
      transparent={glass || opacity < 1}
      opacity={opacity}
      clearcoat={glass ? 1 : 0.2}
      clearcoatRoughness={0.1}
      emissive={new THREE.Color(isSel ? "#38bdf8" : isHov ? "#1e6f8f" : "#000000")}
      emissiveIntensity={isSel ? 0.5 : isHov ? 0.3 : 0}
      side={glass ? THREE.DoubleSide : THREE.FrontSide}
      depthWrite={!glass}
    />
  );

  const handlers = {
    onClick: (e: { stopPropagation: () => void }) => {
      e.stopPropagation();
      selectComponent(isSel ? null : c.name);
    },
    onPointerOver: (e: { stopPropagation: () => void }) => {
      e.stopPropagation();
      hoverComponent(c.name);
      document.body.style.cursor = "pointer";
    },
    onPointerOut: () => {
      hoverComponent(null);
      document.body.style.cursor = "auto";
    },
  };

  return (
    <group position={pos}>
      {c.shape === "frame" ? (
        <group {...handlers}>
          <FrameRails size={size} material={material} />
        </group>
      ) : (
        <RoundedBox args={size} radius={radius} smoothness={4} creaseAngle={0.5} {...handlers}>
          {material}
        </RoundedBox>
      )}

      {(showLabels || isSel) && (isSel || isHov) && (
        <Html
          center
          position={[0, size[1] / 2 + 0.06, size[2] / 2 + 0.02]}
          zIndexRange={[20, 0]}
        >
          <div className="pointer-events-none whitespace-nowrap rounded-md border border-sky-400/40 bg-slate-950/90 px-2 py-1 text-[11px] font-medium text-sky-100 shadow-lg backdrop-blur">
            {c.label}
            <span className="ml-2 text-[10px] font-normal text-slate-400">
              {c.em === "dielectric"
                ? `er ${c.epsilon_r} / tand ${c.loss_tangent}`
                : c.em === "pec"
                  ? "PEC"
                  : c.em}
            </span>
          </div>
        </Html>
      )}
    </group>
  );
}

/** Height (mm) the x-ray is scaled to, from the spec's own device outline. */
function deviceHeightMm(spec: { board: { size_mm: [number, number, number] } }) {
  return spec.board?.size_mm?.[1] ?? 146.6;
}

export function PhoneModel() {
  const spec = useApp((s) => s.spec);
  const modelUrl = useApp((s) => s.modelUrl);

  // A user-supplied export still wins — that is what the upload flow is for.
  if (modelUrl) {
    return (
      <Suspense fallback={null}>
        <CustomModel url={modelUrl} />
      </Suspense>
    );
  }

  // Default: the real iPhone 15 Pro (191 parts, exported from
  // data/apple_iphone_15_pro/), drawn as x-ray line art so the internals and
  // the antenna inside them stay legible — same visual language as the
  // offline renders in rf/runs/demo/media. The procedural RoundedBox handset
  // below is the fallback while the 5 MB model streams in, and if it fails to
  // load at all.
  return (
    <Suspense
      fallback={
        <group>
          {spec.components.map((c) => (
            <Part key={c.name} c={c} />
          ))}
        </group>
      }
    >
      <DeviceXray heightMm={deviceHeightMm(spec)} />
    </Suspense>
  );
}
