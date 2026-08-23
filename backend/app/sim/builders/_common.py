"""Shared geometry helpers for builders."""
from __future__ import annotations

import math

from app.models import Candidate
from app.sim.chassis import ChassisModel


def snap_to_node(model: ChassisModel, x_mm: float, y_mm: float) -> tuple[int, int]:
    """Indices of the lattice node nearest to a point given in mm."""
    x, y = x_mm / 1000.0, y_mm / 1000.0
    i = min(range(len(model.xs)), key=lambda k: abs(model.xs[k] - x))
    j = min(range(len(model.ys)), key=lambda k: abs(model.ys[k] - y))
    return i, j


def edge_frame(model: ChassisModel, i: int, j: int) -> tuple[tuple[float, float], tuple[float, float]]:
    """(along, outward) unit xy vectors for the board edge nearest node (i,j).
    'along' points toward the far end of that edge (maximum arm room);
    'outward' points off the board — the clearance strip where antennas live."""
    xs, ys = model.xs, model.ys
    d_edges = {
        "left": xs[i] - xs[0], "right": xs[-1] - xs[i],
        "bottom": ys[j] - ys[0], "top": ys[-1] - ys[j],
    }
    nearest = min(d_edges, key=d_edges.get)
    if nearest == "bottom":
        out = (0.0, -1.0)
    elif nearest == "top":
        out = (0.0, 1.0)
    elif nearest == "left":
        out = (-1.0, 0.0)
    else:
        out = (1.0, 0.0)
    if nearest in ("bottom", "top"):
        along = (1.0, 0.0) if xs[-1] - xs[i] >= xs[i] - xs[0] else (-1.0, 0.0)
    else:
        along = (0.0, 1.0) if ys[-1] - ys[j] >= ys[j] - ys[0] else (0.0, -1.0)
    return along, out


def seg_count(length_m: float, f_hi_ghz: float = 2.7) -> int:
    """Segments for a wire: aim ~lambda/25 per segment, at least 3 for arms."""
    lam = 299_792_458.0 / (f_hi_ghz * 1e9)
    return max(3, math.ceil(length_m / (lam / 25.0)))


def height_m(cand: Candidate) -> float:
    """Element height above the plane (metres). Param 'height_mm', default 2."""
    return max(0.5, cand.params.get("height_mm", 2.0)) / 1000.0


def offset_m(cand: Candidate) -> float:
    """Lateral clearance-strip offset beyond the board edge (metres).
    Param 'offset_mm', default 2.5 — the PCB-keepout strip a phone antenna
    actually occupies. Running the arm OVER the plane cancels radiation."""
    return max(0.5, cand.params.get("offset_mm", 2.5)) / 1000.0
