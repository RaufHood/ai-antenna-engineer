"""geometry.json (tools/extract_blend.py output) -> DeviceSpec.

Facts (bboxes, materials) come from the extraction script; this module adds
the EM *judgment* heuristically — em class from sigma/eps_r, structural role
from names, ground-plane choice — and lists every ambiguity so the agent can
question or override it (DESIGN.md §8). Agent overrides are applied here too,
so there is exactly one place where a spec is assembled."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.geometry.bands import requirements_for
from app.models import (Board, ComponentRole, DeviceComponent, DeviceSpec, EmClass,
                        Enclosure)

MIN_EXTENT_MM = 1.5   # screws, springs, labels: invisible to the RF model

_ROLE_HINTS: list[tuple[ComponentRole, tuple[str, ...]]] = [
    ("ground", ("ground", "gnd", "pour", "groundplane", "ground_plane", "midplate",
                "mid_plate", "substructure")),
    ("display", ("display", "screen", "lcd", "oled", "panel", "touch")),
    ("battery", ("battery", "cell", "pack")),
    ("back_cover", ("back", "rear", "cover", "lid")),
    ("frame", ("frame", "rail", "housing", "chassis", "rim", "band", "enclosure", "midframe")),
    ("board", ("pcb", "board", "logic", "mainboard", "motherboard", "fr4", "flex")),
    ("shield", ("shield", "can", "emi")),
    ("module", ("camera", "speaker", "usb", "taptic", "haptic", "motor", "mic",
                "sensor", "connector", "port", "lens", "sim", "button", "coil",
                "nfc", "vibr", "earpiece", "lidar", "flash")),
]

_DIELECTRIC_GUESS: dict[str, tuple[float, float]] = {  # role -> (eps_r, tan d)
    "back_cover": (5.5, 0.008), "display": (5.5, 0.01), "board": (4.4, 0.02),
}


@dataclass
class Override:
    em: EmClass | None = None
    role: ComponentRole | None = None
    epsilon_r: float | None = None
    note: str = ""


@dataclass
class Classified:
    spec: DeviceSpec
    ambiguities: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)


def _em_from_material(eps: float | None, sigma: float | None) -> EmClass | None:
    if sigma is None and eps is None:
        return None
    s = sigma or 0.0
    e = eps or 1.0
    if s >= 1e6:
        return "pec"
    if s >= 1e3:
        return "lossy_metal"
    if e > 1.05:
        return "dielectric"
    return "air"


def _role_from_name(*names: str) -> ComponentRole:
    text = " ".join(n.lower() for n in names)
    for role, hints in _ROLE_HINTS:
        if any(re.search(rf"(^|[^a-z]){h}", text) for h in hints):
            return role
    return "other"


def _label(node_path: str, key: str) -> str:
    words = re.sub(r"[._/\-]+", " ", node_path).strip()
    words = words[:1].upper() + words[1:]
    return f"{words} ({key})" if key else words


def _loss_tangent(eps: float | None, sigma: float | None, f_ghz: float = 2.44) -> float | None:
    """tan d = sigma / (omega * eps0 * eps_r) — only meaningful for dielectrics."""
    if not eps or eps <= 1.0 or not sigma or sigma <= 0:
        return None
    omega = 2 * 3.141592653589793 * f_ghz * 1e9
    return round(sigma / (omega * 8.854e-12 * eps), 4)


def _is_sheet(c: DeviceComponent, size_z: float) -> bool:
    return (c.bbox_mm[1][2] - c.bbox_mm[0][2]) <= max(0.15 * size_z, 0.6)


def _pick_ground(comps: list[DeviceComponent], size_z: float) -> DeviceComponent | None:
    """The reference plane: a named ground if there is one (sheet-like ones
    first — a thick rail called 'substructure' is a frame, not a plane), else
    the largest thin metal sheet, lower one preferred so the antenna volume
    stays inside the device."""
    metal = [c for c in comps if c.em in ("pec", "lossy_metal")]
    named = [c for c in metal if c.role == "ground"]
    if named:
        return max(named, key=lambda c: (_is_sheet(c, size_z), _footprint(c)))
    thin = [c for c in metal if _is_sheet(c, size_z) and c.role not in ("frame", "module")]
    if not thin:
        return None
    return max(thin, key=lambda c: (_footprint(c), -c.bbox_mm[1][2]))


def _footprint(c: DeviceComponent) -> float:
    (x0, y0, _), (x1, y1, _) = c.bbox_mm
    return (x1 - x0) * (y1 - y0)


def classify(geometry: dict, band_ids: list[str] | None = None,
             overrides: dict[str, Override] | None = None,
             ground_override: str | None = None,
             geometry_path: str | None = None) -> Classified:
    overrides = overrides or {}
    amb: list[str] = []
    dropped: list[str] = []
    size = geometry["size_mm"]
    frame = geometry.get("frame", {})
    if frame.get("unit_confidence") in ("low", "none"):
        amb.append(f"unit scale guessed ({frame.get('unit_source')}); device reads "
                   f"{size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm — confirm")
    fix = frame.get("orientation_fix", {})
    if any(fix.values()):
        amb.append(f"orientation corrected from name votes: {fix}")

    comps: list[DeviceComponent] = []
    for p in geometry["parts"]:
        if max(p["extent_mm"]) < MIN_EXTENT_MM:
            dropped.append(p["blender_object"])
            continue
        name = p["blender_object"]
        node, key = p["node_path"], p.get("material_key") or ""
        role = _role_from_name(node, name, key)
        em = _em_from_material(p.get("eps_r"), p.get("sigma_S_per_m"))
        src = p.get("em_source", "none")
        eps, tan = p.get("eps_r"), _loss_tangent(p.get("eps_r"), p.get("sigma_S_per_m"))
        if em is None:
            guess = _DIELECTRIC_GUESS.get(role)
            if role in ("ground", "frame", "shield", "module"):
                em, src = "pec", "role-heuristic"
            elif role == "battery":
                em, src = "lossy_metal", "role-heuristic"
            elif guess:
                em, (eps, tan), src = "dielectric", guess, "role-heuristic"
            else:
                em, eps, tan, src = "dielectric", 3.0, 0.002, "default"
            amb.append(f"{name}: no material data; assumed {em} from role {role!r}")
        elif src == "name-heuristic":
            amb.append(f"{name}: material guessed from its name ({p.get('em_note')})")
        if em == "air":
            amb.append(f"{name}: eps_r~1, sigma~0 -> modelled as air (cavity/foam?)")
        ov = overrides.get(name) or overrides.get(node)
        if ov:
            em = ov.em or em
            role = ov.role or role
            eps = ov.epsilon_r if ov.epsilon_r is not None else eps
            src = "agent"
        comps.append(DeviceComponent(
            name=name, label=_label(node, key), em=em,
            epsilon_r=eps if em == "dielectric" else None,
            loss_tangent=tan if em == "dielectric" else None,
            bbox_mm=(tuple(p["bbox_mm"][0]), tuple(p["bbox_mm"][1])),
            role=role, em_source=src, sigma_s_per_m=p.get("sigma_S_per_m")))
    if dropped:
        amb.append(f"{len(dropped)} parts under {MIN_EXTENT_MM} mm dropped from the RF model")

    ground = None
    if ground_override:
        ground = next((c for c in comps if c.name == ground_override), None)
        if ground is None:
            amb.append(f"agent named ground {ground_override!r} which is not a part")
    if ground is None:
        ground = _pick_ground(comps, size[2])
    if ground is None:
        amb.append("no metal sheet found to serve as ground reference — using "
                   "a virtual plane at the device floor")
        ground = DeviceComponent(
            name="virtual_ground", label="Virtual ground (no metal sheet found)",
            em="pec", bbox_mm=((2.0, 2.0, 0.5), (size[0] - 2.0, size[1] - 2.0, 0.8)),
            role="ground", em_source="default")
        comps.append(ground)
    for c in comps:
        if c.role == "ground" and c is not ground:
            c.role = "shield"
    ground.role = "ground"

    board = next((c for c in comps if c.role == "board"), None) or ground
    back = next((c for c in comps if c.role == "back_cover"), None)
    frame_c = next((c for c in comps if c.role == "frame"), None)
    key_of = {p["blender_object"]: p.get("material_key") or "" for p in geometry["parts"]}

    spec = DeviceSpec(
        device_id=str(geometry["device_id"]),
        name=str(geometry["name"]),
        # frontend semantics: board.size_mm is the device outline (W, H, T)
        board=Board(size_mm=(size[0], size[1], size[2]), stackup="FR4",
                    epsilon_r=board.epsilon_r or 4.4, loss_tangent=board.loss_tangent or 0.02),
        enclosure=Enclosure(
            back=key_of.get(back.name, "glass") if back else "unknown",
            frame=key_of.get(frame_c.name, "aluminum") if frame_c else "unknown",
            epsilon_r_back=(back.epsilon_r if back and back.epsilon_r else 1.0)),
        components=comps,
        requirements=requirements_for(band_ids),
        geometry_path=geometry_path,
    )
    return Classified(spec=spec, ambiguities=amb, dropped=dropped)


def device_size(spec: DeviceSpec) -> tuple[float, float, float]:
    """Device extent = union of component boxes (origin is the min corner)."""
    return (max(c.bbox_mm[1][0] for c in spec.components),
            max(c.bbox_mm[1][1] for c in spec.components),
            max(c.bbox_mm[1][2] for c in spec.components))


def ground_of(spec: DeviceSpec) -> DeviceComponent:
    g = next((c for c in spec.components if c.role == "ground"), None)
    if g is None:  # canned specs predate roles; keep the old name contract
        g = next((c for c in spec.components if c.name == "pcb_ground"), None)
    if g is None:
        raise ValueError("spec has no ground component")
    return g
