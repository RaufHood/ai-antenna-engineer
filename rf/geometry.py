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


def _add_device_materials(CSX, parts: list[dict]) -> None:
    """Step 6: one CSXCAD material per distinct material_key in
    device['parts'] (from rf/blend_loader/load_blend.py's device.json),
    one AddBox per part. bbox_mm-only -- the STLs load_blend.py exported
    aren't imported as polyhedra; a phone-scale part count (~200) of full
    AddPolyhedronReader calls would blow the runtime budget geometry.py
    otherwise keeps bounded via margin_mm/mesh_res for a coarse first
    pass. Priority 1: strictly below the antenna's own PEC primitives
    (priority 10) and port (priority 5), so a device part can never mask
    the antenna geometry it's meant to sit alongside.

    A device manifest's coordinates are Blender-native (centred on the
    object); the ground plane/antenna above are corner-anchored at
    [0, board_w] x [0, board_l]. Coordinates here are shifted so the
    parts' own combined bbox starts at (0, 0, 0), aligning the two.
    There's no collision-avoidance with the antenna itself (e.g. against
    a battery or frame segment sharing its cell) -- that's on
    candidate.keepout_mm / placement choice, not this function.
    """
    usable = [p for p in parts if p.get("bbox_mm") and p.get("eps_r") is not None]
    if not usable:
        return

    xs = [c[0] for p in usable for c in p["bbox_mm"]]
    ys = [c[1] for p in usable for c in p["bbox_mm"]]
    zs = [c[2] for p in usable for c in p["bbox_mm"]]
    ox, oy, oz = -min(xs), -min(ys), -min(zs)

    materials: dict[str, object] = {}
    for p in usable:
        key = p.get("material_key") or "unknown"
        mat = materials.get(key)
        if mat is None:
            mat = CSX.AddMaterial(f"device_{key}")
            mat.SetMaterialProperty(
                epsilon=p["eps_r"],
                kappa=p.get("sigma_S_per_m") or 0.0,
                mue=p.get("mu_r") or 1.0,
            )
            materials[key] = mat
        (x0, y0, z0), (x1, y1, z1) = p["bbox_mm"]
        mat.AddBox(priority=1,
                   start=[x0 + ox, y0 + oy, z0 + oz],
                   stop=[x1 + ox, y1 + oy, z1 + oz])


def build_ifa_geometry(candidate: Candidate, band: Band, device: dict, sim: SimOptions) -> FDTDStructure:
    """Step 3/6: ground plane + short pin + radiating arm as CSXCAD PEC
    primitives, fed by an openEMS lumped port, plus every part in
    device['parts'] (if present) as a real dielectric/lossy material via
    _add_device_materials() -- bbox-approximated, see that function's
    docstring for what that does and doesn't capture.

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
    # board.size_mm still only sizes the synthetic flat ground plane below
    # (board thickness is unused) -- it's a proxy "PCB ground" the antenna
    # feeds against, not derived from device['parts']. Real dielectrics/
    # conductors around it come from _add_device_materials() instead, when
    # device['parts'] is present.
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

    _add_device_materials(CSX, device.get("parts") or [])

    if sim.dump_fields:
        # Time-domain E-field on the xy-plane through the antenna (z=h),
        # written as HDF5 (file_type=1) rather than the tutorials' default
        # VTK so visualize.render_field_animation() can read it with h5py
        # alone -- no ParaView needed to see the wave leave the feed.
        # dump_mode=2 (cell-interpolation) matches AddEdges2Grid's cells;
        # SetSubSampling keeps frames small since NrTS is in the thousands.
        et_dump = CSX.AddDump('Et', dump_type=0, file_type=1, dump_mode=2)
        et_dump.SetSubSampling([2, 2, 1])
        et_dump.AddBox(start=[-margin_mm, -margin_mm, h],
                        stop=[board_w + margin_mm, board_l + margin_mm, h])

    mesh.SmoothMeshLines('all', mesh_res_mm, 1.4)

    nf2ff = FDTD.CreateNF2FFBox()

    sim_path = tempfile.mkdtemp(prefix=f"openems_{candidate.candidate_id}_")

    geometry_mm = {
        "board_w": board_w, "board_l": board_l,
        "short_xy": short_xy.tolist(), "feed_xy": feed_xy.tolist(),
        "open_xy": open_xy.tolist(), "arm_width_mm": IFA_ARM_WIDTH_MM,
    }
    return FDTDStructure(FDTD=FDTD, port=port, nf2ff=nf2ff, sim_path=sim_path,
                          geometry_mm=geometry_mm)
