import { H, T, W } from "./device";
import type { Bbox, Vec3 } from "./types";

/** 1 mm in scene units. Keeps the handset ~3 units tall. */
export const SCALE = 0.02;

/** Device millimetres -> centred scene coordinates. */
export function toScene([x, y, z]: Vec3): Vec3 {
  return [(x - W / 2) * SCALE, (y - H / 2) * SCALE, (z - T / 2) * SCALE];
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
