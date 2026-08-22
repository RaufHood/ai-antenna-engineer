// Contracts shared with the simulation + agent workstreams.
// Mirrors the JSON schemas in deep_research_on_challenge.md §5.
// All geometry is in millimetres, origin at the bottom-left-back corner of the device.

export type Vec3 = [number, number, number];
export type Bbox = [Vec3, Vec3]; // [min, max]

export type EmClass = "pec" | "lossy_metal" | "dielectric" | "air";

export interface DeviceComponent {
  /** Must match the glTF node name exported from Blender. */
  name: string;
  label: string;
  em: EmClass;
  epsilon_r?: number;
  loss_tangent?: number;
  bbox_mm: Bbox;
  /** Display-only hints for the viewer. */
  color: string;
  opacity?: number;
  metalness?: number;
  roughness?: number;
  /** Shell parts render as rounded frames rather than plain boxes. */
  shape?: "box" | "frame" | "glass";
  /** Explode direction in scene space. */
  explode?: Vec3;
}

export interface BandRequirement {
  id: string;
  name: string;
  short: string;
  service: string;
  f_low_ghz: number;
  f_high_ghz: number;
  /** Minimum antenna clearance (keep-out radius) in mm. */
  clearance_mm: number;
  s11_db_max: number;
  efficiency_min: number;
  /** Preferred antenna types, best first. */
  antenna_types: AntennaType[];
  /** Region weighting: how much this band likes each perimeter region. */
  region_pref: Record<RegionId, number>;
  color: string;
}

export type AntennaType =
  | "IFA"
  | "PIFA"
  | "monopole"
  | "loop"
  | "frame_slot"
  | "patch_array"
  | "ceramic_chip";

export type RegionId = "bottom" | "top" | "left" | "right";

export interface DeviceSpec {
  device_id: string;
  name: string;
  board: {
    size_mm: Vec3;
    stackup: string;
    epsilon_r: number;
    loss_tangent: number;
  };
  enclosure: { back: string; frame: string; epsilon_r_back: number };
  components: DeviceComponent[];
  requirements: {
    bands: BandRequirement[];
    vswr_max: number;
    isolation_db_max: number;
    sar_limit: { standard: string; w_per_kg: number; mass_g: number };
  };
}

export interface Anchor {
  id: string;
  label: string;
  region: RegionId;
  /** Centre of the candidate antenna volume, in mm. */
  pos_mm: Vec3;
  /** Outward normal along the device surface. */
  outward: Vec3;
  corner: boolean;
}

export interface Candidate {
  candidate_id: string;
  anchor_id: string;
  band_id: string;
  antenna_type: AntennaType;
  position_mm: Vec3;
  feed_point_mm: Vec3;
  length_mm: number;
  orientation: "edge" | "corner" | "face";
  keepout_mm: Bbox;
  /** Pre-simulation heuristic score, 0..1. */
  prior: number;
  rationale: string;
}

export interface SimResult {
  candidate_id: string;
  status: "queued" | "running" | "complete" | "failed";
  runtime_s: number;
  s11_curve: { f_ghz: number; s11_db: number }[];
  s11_min_db: number;
  resonant_ghz: number;
  bandwidth_mhz: number;
  efficiency: number;
  peak_gain_dbi: number;
  vswr: number;
  meets_requirements: boolean;
  notes: string;
}

export interface Job {
  job_id: string;
  candidate_id: string;
  band_id: string;
  status: "queued" | "running" | "complete" | "failed";
}

export interface AgentMessage {
  id: string;
  role: "user" | "agent";
  kind: "text" | "step" | "result";
  text: string;
  ts: number;
}
