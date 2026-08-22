"""Inverted-F antenna: inverted-L plus a shorting post from the arm back down
to the plane near the feed. The feed-short gap sets the impedance transform —
THE knob that matches an electrically short element to 50 ohm.

Geometry (clearance strip, outside the plane footprint):
  feed post: edge node -> arm start (slanted)
  arm part 1: arm start -> short point   (gap_mm along the edge)
  short post: short point -> nearest lattice node (slanted down-in)
  arm part 2: short point -> tip
'length_mm' = total radiating length: post + gap + remaining arm.
Params: gap_mm (default 5), height_mm, offset_mm."""
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
    gap = max(1.0, cand.params.get("gap_mm", 5.0)) / 1000.0

    x1, y1, z1 = x0 + ox * o, y0 + oy * o, z0 + h          # arm start (SHORT end)
    xf, yf = x1 + ax * gap, y1 + ay * gap                  # feed point on arm

    post = math.sqrt(o * o + h * h)
    arm2 = max(cand.length_mm / 1000.0 - post - gap, 0.002)

    tag = next_tag
    # short post: lattice node -> arm start (the IFA's grounded end)
    geo.wire(tag, 1, x0, y0, z0, x1, y1, z1, WIRE_RAD_M, 1.0, 1.0)
    # arm section short -> feed point
    geo.wire(tag + 1, max(1, seg_count(gap) - 2), x1, y1, z1, xf, yf, z1,
             WIRE_RAD_M, 1.0, 1.0)
    # feed post: same lattice node -> feed point (lattice pitch >> gap, so both
    # posts share the foot node; the slant angle difference keeps the loop area)
    feed_tag = tag + 2
    geo.wire(feed_tag, 1, x0, y0, z0, xf, yf, z1, WIRE_RAD_M, 1.0, 1.0)
    # radiating arm feed point -> tip
    geo.wire(tag + 3, seg_count(arm2), xf, yf, z1,
             xf + ax * arm2, yf + ay * arm2, z1, WIRE_RAD_M, 1.0, 1.0)
    return feed_tag, 1
