"""Edge monopole (inverted-L): slanted feed post from a board-edge lattice node
up into the clearance strip, then an arm parallel to the edge, offset OUTSIDE
the plane footprint (PCB keepout — over-plane arms radiate ~nothing).
'length_mm' = total conductor length (post + arm), the lambda/4 quantity."""
from __future__ import annotations

import math

from app.models import Candidate
from app.sim.chassis import WIRE_RAD_M, ChassisModel

from ._common import edge_frame, height_m, offset_m, seg_count, snap_to_node


def build(geo, model: ChassisModel, cand: Candidate, next_tag: int) -> tuple[int, int]:
    i, j = snap_to_node(model, cand.position_mm[0], cand.position_mm[1])
    (ax, ay), (ox, oy) = edge_frame(model, i, j)
    x0, y0, z0 = model.xs[i], model.ys[j], model.z_plane
    h, o = height_m(cand), offset_m(cand)

    x1, y1, z1 = x0 + ox * o, y0 + oy * o, z0 + h   # arm start, in the strip
    post = math.sqrt(o * o + h * h)
    arm = max(cand.length_mm / 1000.0 - post, 0.002)

    feed_tag = next_tag
    geo.wire(feed_tag, 1, x0, y0, z0, x1, y1, z1, WIRE_RAD_M, 1.0, 1.0)
    geo.wire(feed_tag + 1, seg_count(arm), x1, y1, z1,
             x1 + ax * arm, y1 + ay * arm, z1, WIRE_RAD_M, 1.0, 1.0)
    return feed_tag, 1
