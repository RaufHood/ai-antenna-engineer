"use client";

import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { WebGLPathTracer } from "three-gpu-pathtracer";

/**
 * Real ray tracing for the shaded view.
 *
 * The raster pass approximates light: reflections come from an environment
 * probe that knows nothing about the phone, and one part never shadows
 * another. On a device that is mostly polished titanium against dark glass
 * that approximation is exactly what is missing — the frame should be
 * reflecting the board, and the camera glass should be refracting what is
 * behind it.
 *
 * three-gpu-pathtracer traces the actual scene: every bounce, every shadow,
 * real refraction through the transmissive materials. It converges by
 * accumulating samples, so it is the wrong thing to run while someone is
 * dragging the camera and the right thing to run the moment they stop.
 *
 * Hence the two modes. Moving: the ordinary raster render, unchanged and
 * immediate. Still: samples accumulate until the image is clean, and any
 * camera movement drops straight back to raster. The viewer never feels slow,
 * and what you end up looking at is traced.
 *
 * Taking over rendering (useFrame priority 1) means this component owns BOTH
 * paths — when it is not tracing it must still call gl.render itself, or the
 * canvas goes black.
 */

/** Beyond this the image is clean enough that more samples are invisible. */
const MAX_SAMPLES = 320;
/** Bounces. 3 is enough for metal-and-glass; more mostly costs frames. */
const BOUNCES = 3;
/** Wait after the camera settles, so a slow orbit does not thrash the BVH. */
const SETTLE_MS = 180;

export function PathTracer({ enabled }: { enabled: boolean }) {
  const gl = useThree((s) => s.gl);
  const scene = useThree((s) => s.scene);
  const camera = useThree((s) => s.camera);
  const controls = useThree((s) => s.controls) as
    | (THREE.EventDispatcher & { addEventListener: unknown })
    | null;

  const tracer = useRef<WebGLPathTracer | null>(null);
  const ready = useRef(false);
  const lastMove = useRef(0);
  const [, force] = useState(0);

  // Build the accelerator only when tracing is actually wanted: the BVH over
  // 234k triangles costs real time and memory, and most sessions never ask.
  useEffect(() => {
    if (!enabled) return;
    let alive = true;

    // The raster scene is lit mostly by ambientLight and three directional
    // lights, which a path tracer does not see the same way: it takes its
    // illumination from the environment and from emissive geometry. Left at
    // the raster intensity the traced image comes back almost black — a dark
    // glass phone lit by four small lightformers. Brighten the environment
    // while tracing, and put it back on the way out so the raster view is
    // untouched.
    const priorEnv = scene.environmentIntensity;
    scene.environmentIntensity = 7.0;

    const pt = new WebGLPathTracer(gl);
    pt.bounces = BOUNCES;
    pt.renderScale = Math.min(1, 1 / gl.getPixelRatio());
    pt.tiles.set(2, 2);            // split each sample so the tab stays responsive
    pt.filterGlossyFactor = 0.5;   // tames fireflies on the polished frame
    tracer.current = pt;

    // setSceneAsync builds the BVH off the main thread where it can.
    Promise.resolve(pt.setSceneAsync(scene, camera))
      .then(() => {
        if (!alive) return;
        ready.current = true;
        force((n) => n + 1);
      })
      .catch(() => {
        // No BVH means no tracing; the raster path below still draws.
        ready.current = false;
      });

    return () => {
      alive = false;
      ready.current = false;
      tracer.current = null;
      scene.environmentIntensity = priorEnv;
      pt.dispose();
    };
  }, [enabled, gl, scene, camera]);

  // Any camera movement invalidates every sample accumulated so far.
  useEffect(() => {
    if (!controls) return;
    const onChange = () => {
      lastMove.current = performance.now();
      tracer.current?.updateCamera();
    };
    const target = controls as unknown as {
      addEventListener: (t: string, f: () => void) => void;
      removeEventListener: (t: string, f: () => void) => void;
    };
    target.addEventListener("change", onChange);
    return () => target.removeEventListener("change", onChange);
  }, [controls]);

  useFrame(() => {
    const pt = tracer.current;
    const moving = performance.now() - lastMove.current < SETTLE_MS;
    if (enabled && pt && ready.current && !moving && pt.samples < MAX_SAMPLES) {
      pt.renderSample();
      return;
    }
    // Everything else — disabled, still building, mid-orbit, or converged
    // enough — is the ordinary render. Converged is included on purpose: once
    // the samples are in, the traced result is already on screen and
    // re-rendering it would only burn GPU.
    if (!(enabled && pt && ready.current && !moving)) {
      gl.render(scene, camera);
    }
  }, 1);

  return null;
}
