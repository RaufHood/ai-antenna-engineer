import { phoneV1 } from "./device";
import type { DeviceComponent, DeviceSpec } from "./types";

const ROLE_COLOR: Record<string, string> = {
  ground: "#d9a441",
  battery: "#3f5d4a",
  display: "#101a30",
  frame: "#d7dbe3",
  back_cover: "#16203a",
  board: "#4a7c59",
  shield: "#64748b",
  module: "#7c5cbf",
  other: "#475569",
};

const EM_COLOR: Record<DeviceComponent["em"], string> = {
  pec: "#c4a35a",
  lossy_metal: "#8b9bb4",
  dielectric: "#1e3a5f",
  air: "#334155",
};

function colorFor(c: DeviceComponent): string {
  const role = (c as DeviceComponent & { role?: string }).role;
  if (role && ROLE_COLOR[role]) return ROLE_COLOR[role];
  return EM_COLOR[c.em] ?? "#64748b";
}

/**
 * Backend DeviceSpec omits viewer-only fields (component colour, some band
 * catalogue extras). Fill them so the existing UI can render the snapshot.
 */
export function hydrateSpec(raw: DeviceSpec): DeviceSpec {
  const catalog = Object.fromEntries(
    phoneV1.requirements.bands.map((b) => [b.id, b]),
  );
  const bands = (raw.requirements?.bands?.length
    ? raw.requirements.bands
    : phoneV1.requirements.bands
  ).map((b) => {
    const fallback = catalog[b.id];
    return {
      ...fallback,
      ...b,
      color: b.color || fallback?.color || "#94a3b8",
      region_pref: {
        ...(fallback?.region_pref ?? {
          bottom: 0.5,
          top: 0.5,
          left: 0.5,
          right: 0.5,
        }),
        ...b.region_pref,
      },
      antenna_types: b.antenna_types?.length
        ? b.antenna_types
        : (fallback?.antenna_types ?? ["IFA"]),
    };
  });

  return {
    ...raw,
    board: { ...phoneV1.board, ...raw.board },
    enclosure: { ...phoneV1.enclosure, ...raw.enclosure },
    components: (raw.components ?? []).map((c) => ({
      ...c,
      label: c.label || c.name,
      color: c.color || colorFor(c),
    })),
    requirements: {
      ...phoneV1.requirements,
      ...raw.requirements,
      bands,
      sar_limit: {
        ...phoneV1.requirements.sar_limit,
        ...raw.requirements?.sar_limit,
      },
    },
  };
}
