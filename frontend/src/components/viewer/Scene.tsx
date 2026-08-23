"use client";

import {
  ContactShadows,
  Environment,
  Grid,
  Lightformer,
  OrbitControls,
  PerspectiveCamera,
} from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Suspense, useEffect, useRef } from "react";
import * as THREE from "three";
import { useApp } from "@/lib/store";
import { Antennas } from "./Antennas";
import { Keepouts } from "./Keepouts";
import { PhoneModel } from "./PhoneModel";

export const VIEW_PRESETS: Record<string, [number, number, number]> = {
  Iso: [2.3, 1.5, 6.4],
  Front: [0, 0, 6.6],
  Back: [0, 0, -6.6],
  Edge: [6.4, 0, 0.8],
  Top: [0.5, 6.2, 1.4],
};

/** Smoothly flies the camera to a preset when the HUD dispatches `view-preset`. */
function CameraRig() {
  const camera = useThree((s) => s.camera);
  const target = useRef<THREE.Vector3 | null>(null);

  useEffect(() => {
    const onPreset = (e: Event) => {
      const name = (e as CustomEvent<string>).detail;
      const p = VIEW_PRESETS[name];
      if (p) target.current = new THREE.Vector3(...p);
    };
    window.addEventListener("view-preset", onPreset);
    return () => window.removeEventListener("view-preset", onPreset);
  }, []);

  // Orbit along a spherical path: a straight lerp between opposite presets
  // passes through the origin, where OrbitControls' minDistance clamp traps it.
  useFrame(() => {
    if (!target.current) return;
    const cur = new THREE.Spherical().setFromVector3(camera.position);
    const dst = new THREE.Spherical().setFromVector3(target.current);
    let dTheta = dst.theta - cur.theta;
    while (dTheta > Math.PI) dTheta -= Math.PI * 2;
    while (dTheta < -Math.PI) dTheta += Math.PI * 2;

    const k = 0.1;
    camera.position.setFromSpherical(
      new THREE.Spherical(
        THREE.MathUtils.lerp(cur.radius, dst.radius, k),
        THREE.MathUtils.lerp(cur.phi, dst.phi, k),
        cur.theta + dTheta * k,
      ),
    );
    camera.lookAt(0, 0, 0);
    if (camera.position.distanceTo(target.current) < 0.04) target.current = null;
  });
  return null;
}

export default function Scene() {
  const explode = useApp((s) => s.explode);
  const selectComponent = useApp((s) => s.selectComponent);
  const selectCandidate = useApp((s) => s.selectCandidate);

  return (
    <Canvas
      shadows
      dpr={[1, 2]}
      gl={{ antialias: true, preserveDrawingBuffer: true }}
      onPointerMissed={() => {
        selectComponent(null);
        selectCandidate(null);
      }}
    >
      <color attach="background" args={["#070a12"]} />
      <fog attach="fog" args={["#070a12", 11, 22]} />

      <PerspectiveCamera makeDefault position={[2.3, 1.5, 6.4]} fov={30} near={0.05} far={60} />
      <OrbitControls
        makeDefault
        enableDamping
        dampingFactor={0.08}
        minDistance={2}
        maxDistance={16}
        target={[0, 0, 0]}
      />
      <CameraRig />

      <ambientLight intensity={1.1} />
      <directionalLight position={[3, 5, 4]} intensity={2.2} castShadow />
      <directionalLight position={[-4, 2, -3]} intensity={1.2} color="#7dd3fc" />
      <directionalLight position={[0, -3, -5]} intensity={0.9} color="#c4b5fd" />

      <Suspense fallback={null}>
        <Environment resolution={256} frames={1}>
          <Lightformer intensity={2.4} position={[0, 3, 2]} scale={[6, 3, 1]} color="#ffffff" />
          <Lightformer intensity={1.2} position={[-4, 1, 1]} scale={[3, 6, 1]} color="#60a5fa" />
          <Lightformer intensity={1.0} position={[4, -1, 1]} scale={[3, 6, 1]} color="#f472b6" />
          <Lightformer intensity={0.8} position={[0, -3, -2]} scale={[6, 3, 1]} color="#a78bfa" />
        </Environment>

        {/* The assembly grows as it comes apart, so the whole scene is scaled
            back by the same amount and keeps the framing the intact phone had
            — otherwise the outer layers leave the viewport at half travel.
            Applied here and not inside the device: the antenna pins and
            keep-outs live in the same frame and have to travel with it, or the
            placement stops sitting where it was placed. */}
        <group scale={1 / (1 + 0.55 * explode)}>
          <PhoneModel />
          <Keepouts />
          <Antennas />
        </group>

        <ContactShadows
          position={[0, -1.68, 0]}
          opacity={0.5}
          scale={9}
          blur={2.6}
          far={4}
          color="#000000"
        />
      </Suspense>

      <Grid
        position={[0, -1.7, 0]}
        args={[16, 16]}
        cellSize={0.25}
        cellThickness={0.6}
        cellColor="#1e293b"
        sectionSize={1}
        sectionThickness={1}
        sectionColor="#334155"
        fadeDistance={16}
        fadeStrength={1.5}
        infiniteGrid
      />
    </Canvas>
  );
}
