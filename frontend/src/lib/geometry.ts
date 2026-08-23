import { H, T, W } from "./device";
import type { Bbox, Vec3 } from "./types";

/** 1 mm in scene units. Keeps the handset ~3 units tall. */
export const SCALE = 0.02;

/**
 * The device the viewer is currently centring on, in millimetres.
 *
 * `toScene` has to subtract half the device to put its centre at the origin,
 * and it is called from render paths that have no access to the store. It used
 * the phone's constants, which was invisible while the phone was the only
 * device and put every MacBook candidate pin a hundred millimetres outside the
 * laptop the moment a second one arrived.
 *
 * One module-level value, written once whenever the spec changes, is the
 * smallest honest fix: the alternative is threading a size through every
 * geometry helper and every component that calls one.
 */
let deviceSize: Vec3 = [W, H, T];

export function setSceneDevice(size: Vec3): void {
  deviceSize = size;
}

/** Device millimetres -> centred scene coordinates. */
export function toScene([x, y, z]: Vec3): Vec3 {
  const [w, h, t] = deviceSize;
  return [(x - w / 2) * SCALE, (y - h / 2) * SCALE, (z - t / 2) * SCALE];
}

export function sizeOf([min, max]: Bbox): Vec3 {
  return [max[0] - min[0], max[1] - min[1], max[2] - min[2]];
}

export function centerOf([min, max]: Bbox): Vec3 {
  return [
    (min[0] + max[0]) / 2,
    (min[1] + max[1]) / 2,
    (min[2] + max[2]) / 2,
  ];
}

export function sceneSize(b: Bbox): Vec3 {
  const s = sizeOf(b);
  return [s[0] * SCALE, s[1] * SCALE, s[2] * SCALE];
}

export function sceneCenter(b: Bbox): Vec3 {
  return toScene(centerOf(b));
}

export function boxesOverlap(a: Bbox, b: Bbox): boolean {
  return (
    a[0][0] < b[1][0] &&
    a[1][0] > b[0][0] &&
    a[0][1] < b[1][1] &&
    a[1][1] > b[0][1] &&
    a[0][2] < b[1][2] &&
    a[1][2] > b[0][2]
  );
}

export function boxIntersection(a: Bbox, b: Bbox): Bbox | null {
  if (!boxesOverlap(a, b)) return null;
  return [
    [
      Math.max(a[0][0], b[0][0]),
      Math.max(a[0][1], b[0][1]),
      Math.max(a[0][2], b[0][2]),
    ],
    [
      Math.min(a[1][0], b[1][0]),
      Math.min(a[1][1], b[1][1]),
      Math.min(a[1][2], b[1][2]),
    ],
  ];
}
