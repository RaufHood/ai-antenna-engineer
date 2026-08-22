"""Chassis lattice model shared by the oracle and the builders.

Separate module so builders never import the oracle (no cycle).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.models import DeviceSpec

C = 299_792_458.0
Z0 = 50.0
WIRE_RAD_M = 0.0005


@dataclass
class ChassisModel:
    xs: list[float]  # lattice node coords, metres
    ys: list[float]
    z_plane: float   # metres
    pitch: float     # metres


def chassis_from_spec(spec: DeviceSpec, f_high_ghz: float) -> ChassisModel:
    ground = next(c for c in spec.components if c.name == "pcb_ground")
    (x0, y0, z0), (x1, y1, z1) = ground.bbox_mm
    lam = C / (f_high_ghz * 1e9)
    pitch = lam / 10.0
    w, h = (x1 - x0) / 1000.0, (y1 - y0) / 1000.0
    nx = max(3, round(w / pitch) + 1)
    ny = max(3, round(h / pitch) + 1)
    xs = [x0 / 1000.0 + w * i / (nx - 1) for i in range(nx)]
    ys = [y0 / 1000.0 + h * j / (ny - 1) for j in range(ny)]
    return ChassisModel(xs=xs, ys=ys, z_plane=(z1 / 1000.0),
                        pitch=min(w / (nx - 1), h / (ny - 1)))


def build_plane(geo, m: ChassisModel) -> int:
    """Edge-by-edge lattice; returns next free tag."""
    tag = 1
    for j, y in enumerate(m.ys):
        for i in range(len(m.xs) - 1):
            geo.wire(tag, 1, m.xs[i], y, m.z_plane, m.xs[i + 1], y, m.z_plane,
                     WIRE_RAD_M, 1.0, 1.0)
            tag += 1
    for i, x in enumerate(m.xs):
        for j in range(len(m.ys) - 1):
            geo.wire(tag, 1, x, m.ys[j], m.z_plane, x, m.ys[j + 1], m.z_plane,
                     WIRE_RAD_M, 1.0, 1.0)
            tag += 1
    return tag
