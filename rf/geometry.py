"""Builds the openEMS/CSXCAD structure for a candidate IFA."""
from __future__ import annotations

import tempfile

from .models import (
    C0,
    IFA_ARM_WIDTH_MM,
    IFA_HEIGHT_MM,
    IFA_SHORT_GAP_MM,
    Band,
    Candidate,
    FDTDStructure,
    SimOptions,
)


def build_ifa_geometry(candidate: Candidate, band: Band, device: dict, sim: SimOptions) -> FDTDStructure:
    """Step 3/6: ground plane + short pin + radiating arm as CSXCAD PEC
    primitives, fed by an openEMS lumped port. Bare PEC only, no
    dielectrics yet -- that's step 6, once device['components'] carries
    real material data from a Blender export (rf/blend_loader/load_blend.py).

    Geometry convention (see IFA_* constants in models.py): candidate.
    position_mm is the short-circuit (grounded) pin location; candidate.
    feed_point_mm is the feed location, its z giving the pin height (falls
    back to IFA_HEIGHT_MM if 0). If the two collapse to the same (x, y) --
    true of the current frontend candidate generator, which has no
    separate short-point field -- the short pin is nudged IFA_SHORT_GAP_MM
    away so CSXCAD gets two distinct conductors. The radiating arm runs
    from the short pin, continuing past it (away from the feed) for
    length_mm.
    """
    import numpy as np
    from . import openems_env
    openems_env.setup()
    from CSXCAD import ContinuousStructure
    from openEMS import openEMS

    board = device.get("board", {}) if device else {}
    # board thickness/stackup is unused here -- bare PEC ground plane only
    # until step 6 (dielectrics from the Blender export) fills it in.
    board_w, board_l, _ = board.get("size_mm") or [100.0, 50.0, 1.6]

    f_low = band.f_low_ghz * 1e9
    f_high = band.f_high_ghz * 1e9
    f0 = (f_low + f_high) / 2.0
    # The Gaussian excitation must stay broadband even when the *reported*
    # band is narrow (progress_simulation.md chose a narrow GPS-L1 sweep
    # for a fast first pass). A narrow excitation pulse is LONG in the time
    # domain and makes the FDTD run slower, not faster -- narrowing the
    # reported band is a post-processing lever (fewer CalcPort frequency
    # points), not an excitation one. Reuse the ~0.5 f0/fc ratio from
    # openEMS's own Simple_Patch_Antenna tutorial rather than deriving fc
    # from the (possibly very narrow) band width.
    fc = 0.5 * f0

    h = candidate.feed_point_mm[2] if candidate.feed_point_mm[2] > 0 else IFA_HEIGHT_MM
    short_xy = np.array(candidate.position_mm[:2], dtype=float)
    feed_xy = np.array(candidate.feed_point_mm[:2], dtype=float)

    # Arm direction is derived from the board, not from the feed/short
    # vector: it points from the board centre through the short pin,
    # continued outward-to-inward reversed (i.e. from the short pin toward
    # the board interior). Deriving it from feed-short instead (as a first
    # cut did) is circular once short/feed collapse to one point below --
    # the nudge direction would silently become the arm direction too, and
    # for an edge-placed candidate that can point the arm straight off the
    # board into free space.
    center = np.array([board_w / 2.0, board_l / 2.0])
    outward = short_xy - center
    if np.linalg.norm(outward) < 1e-6:
        outward = np.array([1.0, 0.0])
    arm_dir = -outward / np.linalg.norm(outward)
    perp_unit = np.array([-arm_dir[1], arm_dir[0]])

    if np.allclose(short_xy, feed_xy):
        # Candidate has no dedicated short-point field. The feed MUST land
        # on the arm's centreline (offset along arm_dir, toward the open
        # end) so its top actually touches the arm conductor -- an offset
        # perpendicular to the arm (a first cut did this) leaves the feed
        # pin's top floating in free space next to the arm, not on it,
        # which drives nothing: the port sees near-total reflection at
        # every frequency (this is exactly what the first real run showed:
        # S11 flat at -0.05 dB, VSWR 314, across the whole band).
        feed_xy = short_xy + arm_dir * IFA_SHORT_GAP_MM

    open_xy = short_xy + arm_dir * candidate.length_mm
    perp = perp_unit * (IFA_ARM_WIDTH_MM / 2.0)

    mesh_div = 10.0 if sim.mesh_res == "coarse" else 20.0
    mesh_res_mm = (C0 / f_high / 1e-3) / mesh_div         # lambda/N at f_high
    margin_mm = (C0 / f_low / 1e-3) / 4.0                  # >= lambda/4 at f_low

    NrTS = 15000 if sim.mesh_res == "coarse" else 30000
    FDTD = openEMS(NrTS=NrTS, EndCriteria=1e-4)
    FDTD.SetGaussExcite(f0, fc)
    FDTD.SetBoundaryCond([sim.boundary] * 6)

    CSX = ContinuousStructure()
    FDTD.SetCSX(CSX)
    mesh = CSX.GetGrid()
    mesh.SetDeltaUnit(1e-3)  # working unit: mm

    mesh.AddLine('x', [-margin_mm, board_w + margin_mm])
    mesh.AddLine('y', [-margin_mm, board_l + margin_mm])
    # Explicit lines at 0 and h: the pins/arm (h = a few mm) are much
    # smaller than mesh_res_mm (tens of mm), so the general lambda/N mesh
    # alone would never place a line at the pin-top height -- the whole
    # pin would fall inside one coarse z-cell with no line bracketing its
    # top, which is exactly what caused the lumped port to fail to snap
    # to the grid ("Dimension is: 0") on the first run of this geometry.
    mesh.AddLine('z', [-margin_mm, 0, h, h + margin_mm])

    # metal_edge_res inserts extra lines flanking each conductor edge (the
    # openEMS "thirds rule" refinement) -- without it, AddEdges2Grid only
    # adds a line exactly at the primitive's own boundary, which is not
    # enough to bracket a zero-width pin/port with usable cells either.
    edge_res = mesh_res_mm / 2.0

    ground = CSX.AddMetal('ground')
    ground.AddBox(priority=10, start=[0, 0, 0], stop=[board_w, board_l, 0])
    FDTD.AddEdges2Grid(dirs='xy', properties=ground, metal_edge_res=edge_res)

    short_pin = CSX.AddMetal('short_pin')
    short_pin.AddBox(priority=10,
                      start=[short_xy[0], short_xy[1], 0],
                      stop=[short_xy[0], short_xy[1], h])
    FDTD.AddEdges2Grid(dirs='xy', properties=short_pin, metal_edge_res=edge_res)

    arm = CSX.AddMetal('radiator_arm')
    arm.AddBox(priority=10,
               start=[short_xy[0] - perp[0], short_xy[1] - perp[1], h],
               stop=[open_xy[0] + perp[0], open_xy[1] + perp[1], h])
    FDTD.AddEdges2Grid(dirs='xy', properties=arm, metal_edge_res=edge_res)

    port = FDTD.AddLumpedPort(1, 50, [feed_xy[0], feed_xy[1], 0],
                               [feed_xy[0], feed_xy[1], h],
                               'z', 1.0, priority=5, edges2grid='xy')

    mesh.SmoothMeshLines('all', mesh_res_mm, 1.4)

    nf2ff = FDTD.CreateNF2FFBox()

    sim_path = tempfile.mkdtemp(prefix=f"openems_{candidate.candidate_id}_")

    return FDTDStructure(FDTD=FDTD, port=port, nf2ff=nf2ff, sim_path=sim_path)
