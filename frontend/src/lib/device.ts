import type { Anchor, DeviceSpec, RegionId, Vec3 } from "./types";

// iPhone 15 class outline: 147.6 x 71.6 x 7.8 mm.
export const W = 71.6; // x, width
export const H = 147.6; // y, height
export const T = 7.8; // z, thickness

export const phoneV1: DeviceSpec = {
  device_id: "phone_v1",
  name: "Handset A (147.6 x 71.6 x 7.8 mm)",
  board: {
    size_mm: [W, H, T],
    stackup: "FR4",
    epsilon_r: 4.4,
    loss_tangent: 0.02,
  },
  enclosure: { back: "glass", frame: "aluminum", epsilon_r_back: 5.5 },
  components: [
    {
      name: "frame",
      label: "Aluminium frame",
      em: "pec",
      bbox_mm: [
        [0, 0, 0],
        [W, H, T],
      ],
      color: "#d7dbe3",
      metalness: 0.85,
      roughness: 0.25,
      shape: "frame",
      explode: [0, 0, 0],
    },
    {
      name: "screen_glass",
      label: "Display + cover glass",
      em: "dielectric",
      epsilon_r: 5.5,
      loss_tangent: 0.01,
      bbox_mm: [
        [1.4, 1.4, T - 1.4],
        [W - 1.4, H - 1.4, T],
      ],
      color: "#101a30",
      opacity: 0.3,
      metalness: 0.1,
      roughness: 0.08,
      shape: "glass",
      explode: [0, 0, 1],
    },
    {
      name: "back_glass",
      label: "Back glass",
      em: "dielectric",
      epsilon_r: 5.5,
      loss_tangent: 0.008,
      bbox_mm: [
        [1.2, 1.2, 0],
        [W - 1.2, H - 1.2, 1.1],
      ],
      color: "#16203a",
      opacity: 0.28,
      metalness: 0.2,
      roughness: 0.15,
      shape: "glass",
      explode: [0, 0, -1],
    },
    {
      name: "ground_plane",
      label: "PCB ground plane",
      em: "pec",
      bbox_mm: [
        [36, 100, 3.5],
        [64, 132, 3.8],
      ],
      color: "#d9a441",
      metalness: 0.9,
      roughness: 0.35,
      explode: [0.12, 0, -0.42],
    },
    {
      name: "pcb",
      label: "Logic board (FR4)",
      em: "dielectric",
      epsilon_r: 4.4,
      loss_tangent: 0.02,
      bbox_mm: [
        [36, 100, 2.4],
        [64, 132, 3.5],
      ],
      color: "#1f6f4a",
      metalness: 0.05,
      roughness: 0.75,
      explode: [0.12, 0, -0.42],
    },
    {
      name: "camera_module",
      label: "Camera module",
      em: "pec",
      bbox_mm: [
        [6, 104, 3.6],
        [30, 132, 7.4],
      ],
      color: "#2b2f38",
      metalness: 0.75,
      roughness: 0.3,
      explode: [-0.22, 0.12, -0.34],
    },
    {
      name: "battery",
      label: "Battery pack",
      em: "lossy_metal",
      bbox_mm: [
        [5, 36, 1.6],
        [66, 98, 5.8],
      ],
      color: "#3f4a63",
      metalness: 0.4,
      roughness: 0.6,
      explode: [0, -0.08, -0.72],
    },
    {
      name: "taptic_engine",
      label: "Taptic engine",
      em: "lossy_metal",
      bbox_mm: [
        [6, 20, 2.2],
        [30, 33, 5.4],
      ],
      color: "#4a4f5c",
      metalness: 0.6,
      roughness: 0.45,
      explode: [-0.18, -0.16, -0.6],
    },
    {
      name: "speaker",
      label: "Loudspeaker",
      em: "lossy_metal",
      bbox_mm: [
        [38, 20, 2.2],
        [66, 33, 5.4],
      ],
      color: "#454b57",
      metalness: 0.5,
      roughness: 0.5,
      explode: [0.18, -0.16, -0.6],
    },
  ],
  requirements: {
    vswr_max: 3.0,
    isolation_db_max: -12,
    sar_limit: { standard: "FCC", w_per_kg: 1.6, mass_g: 1 },
    bands: [
      {
        id: "lte_low",
        name: "B5 / n5 low-band",
        short: "B5",
        service: "Cellular low-band",
        f_low_ghz: 0.824,
        f_high_ghz: 0.894,
        clearance_mm: 24,
        s11_db_max: -6,
        efficiency_min: 0.4,
        antenna_types: ["IFA", "frame_slot", "PIFA"],
        region_pref: { bottom: 1, top: 0.72, left: 0.5, right: 0.5 },
        color: "#34d399",
      },
      {
        id: "gps_l1",
        name: "GPS L1",
        short: "GPS",
        service: "GNSS",
        f_low_ghz: 1.559,
        f_high_ghz: 1.61,
        clearance_mm: 14,
        s11_db_max: -8,
        efficiency_min: 0.45,
        antenna_types: ["IFA", "ceramic_chip", "patch_array"],
        region_pref: { bottom: 0.35, top: 1, left: 0.6, right: 0.6 },
        color: "#fbbf24",
      },
      {
        id: "wifi24",
        name: "Wi-Fi / BT 2.4 GHz",
        short: "WiFi 2.4",
        service: "ISM",
        f_low_ghz: 2.4,
        f_high_ghz: 2.4835,
        clearance_mm: 12,
        s11_db_max: -8,
        efficiency_min: 0.5,
        antenna_types: ["IFA", "monopole", "ceramic_chip"],
        region_pref: { bottom: 0.8, top: 0.9, left: 0.65, right: 0.65 },
        color: "#a78bfa",
      },
      {
        id: "n78",
        name: "n78 C-band",
        short: "n78",
        service: "5G NR sub-6",
        f_low_ghz: 3.3,
        f_high_ghz: 3.8,
        clearance_mm: 9,
        s11_db_max: -6,
        efficiency_min: 0.5,
        antenna_types: ["IFA", "monopole", "frame_slot"],
        region_pref: { bottom: 0.85, top: 0.85, left: 0.8, right: 0.8 },
        color: "#22d3ee",
      },
      {
        id: "wifi5",
        name: "Wi-Fi 5 GHz",
        short: "WiFi 5",
        service: "UNII",
        f_low_ghz: 5.15,
        f_high_ghz: 5.85,
        clearance_mm: 7,
        s11_db_max: -8,
        efficiency_min: 0.5,
        antenna_types: ["monopole", "IFA", "patch_array"],
        region_pref: { bottom: 0.7, top: 0.95, left: 0.75, right: 0.75 },
        color: "#f472b6",
      },
    ],
  },
};

/**
 * Candidate placement anchors along the device perimeter, at antenna height.
 * Port of backend/app/geometry/spec.py `make_anchors`, same ids and spacing,
 * so what the viewer shows before a run is the set the agent picks from. The
 * backend measures its outline from its own RF sheets (1.4 mm inside ours),
 * so positions differ by that much until a run starts and its anchors arrive.
 */
export function makeAnchors(spec: DeviceSpec, spacingMm = 18): Anchor[] {
  const [w, h, t] = spec.board.size_mm;
  const ground = spec.components.find((c) => c.name === "ground_plane") ?? spec.components[0];
  const gTop = ground.bbox_mm[1][2];
  const z = +Math.min(gTop + 2, Math.max(t - 0.5, gTop + 0.5)).toFixed(2);
  const m = Math.min(6, w / 8);
  const r = (v: number) => +v.toFixed(2);
  const out: Anchor[] = [];
  const add = (id: string, label: string, region: RegionId, pos: Vec3, outward: Vec3, corner: boolean) =>
    out.push({ id, label, region, pos_mm: [r(pos[0]), r(pos[1]), r(pos[2])], outward, corner });

  add("c_bl", "bottom-left corner", "bottom", [m, m, z], [-0.7, -0.7, 0], true);
  add("c_br", "bottom-right corner", "bottom", [w - m, m, z], [0.7, -0.7, 0], true);
  add("c_tl", "top-left corner", "top", [m, h - m, z], [-0.7, 0.7, 0], true);
  add("c_tr", "top-right corner", "top", [w - m, h - m, z], [0.7, 0.7, 0], true);
  const nBottom = Math.floor((w - 2 * m) / spacingMm);
  for (let i = 1; i < nBottom; i++) {
    const x = m + i * spacingMm;
    add(`e_b${i}`, `bottom edge ${i}`, "bottom", [x, m, z], [0, -1, 0], false);
    add(`e_t${i}`, `top edge ${i}`, "top", [x, h - m, z], [0, 1, 0], false);
  }
  const nSide = Math.floor((h - 2 * m) / spacingMm);
  for (let i = 1; i < nSide; i++) {
    const y = m + i * spacingMm;
    add(`e_l${i}`, `left edge ${i}`, "left", [m, y, z], [-1, 0, 0], false);
    add(`e_r${i}`, `right edge ${i}`, "right", [w - m, y, z], [1, 0, 0], false);
  }
  return out;
}

export const anchors: Anchor[] = makeAnchors(phoneV1);
