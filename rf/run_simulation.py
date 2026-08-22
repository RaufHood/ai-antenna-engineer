"""Backbone for the sim workstream's single entry point.

    run_simulation(config: dict) -> dict

Contract is fixed by frontend/src/lib/types.ts (Candidate / BandRequirement /
DeviceSpec in, SimResult out) so a FastAPI endpoint can call this directly and
frontend/src/lib/runner.ts's resultFor() can swap the mock simulate() for a
real HTTP call to that endpoint without changing shape on either side.

Solver: openEMS (FDTD), installed in rf/.venv from the vendored Windows
wheels (rf/vendor/openEMS/python/*.whl — see rf/requirements.txt and
rf/openems_env.py, which must run before `import CSXCAD` / `import
openEMS`). build_ifa_geometry/run_fdtd/postprocess (steps 3/5) are now a
real bare-PEC IFA-over-ground-plane solve, not a stub — but step 2 (run an
UNMODIFIED openEMS tutorial and check it against its own documented
result) still hasn't happened, so nothing here is cross-checked against a
known-good number yet. See rf/progress_simulation.md for the step-by-step
plan and rf/bench_scaling.py / rf/validate_dipole.py for the PyNEC
cross-check oracle (step 4) this geometry is meant to agree with.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

try:
    from . import openems_env
except ImportError:
    import openems_env

Vec3 = tuple[float, float, float]
Bbox = tuple[Vec3, Vec3]

C0 = 299_792_458.0

# IFA geometry conventions -- Candidate (frontend/src/lib/types.ts) has no
# dedicated short-pin field, so these fill the gap. Documented here rather
# than buried in build_ifa_geometry so they're easy to find and revisit.
IFA_HEIGHT_MM = 5.0       # pin height used when feed_point_mm.z is 0
IFA_SHORT_GAP_MM = 3.0    # short-to-feed spacing when position_mm and
                          # feed_point_mm collapse to the same (x, y)
IFA_ARM_WIDTH_MM = 2.0    # radiating-arm strip width


@dataclass
class Candidate:
    candidate_id: str
    antenna_type: str  # "IFA" first; see progress_simulation.md
    position_mm: Vec3
    feed_point_mm: Vec3
    length_mm: float
    orientation: Literal["edge", "corner", "face"] = "edge"
    keepout_mm: Bbox | None = None


@dataclass
class Band:
    id: str
    f_low_ghz: float
    f_high_ghz: float
    s11_db_max: float = -8.0
    efficiency_min: float = 0.45


@dataclass
class SimOptions:
    mesh_res: Literal["coarse", "fine"] = "coarse"
    boundary: Literal["MUR", "PML_8"] = "MUR"
    freq_points: int = 21


@dataclass
class SimResult:
    candidate_id: str
    status: Literal["queued", "running", "complete", "failed"]
    runtime_s: float
    s11_curve: list[dict]  # [{"f_ghz": ..., "s11_db": ...}, ...]
    s11_min_db: float
    resonant_ghz: float
    bandwidth_mhz: float
    efficiency: float
    peak_gain_dbi: float
    vswr: float
    sar_w_per_kg: float
    meets_requirements: bool
    notes: str

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "status": self.status,
            "runtime_s": self.runtime_s,
            "s11_curve": self.s11_curve,
            "s11_min_db": self.s11_min_db,
            "resonant_ghz": self.resonant_ghz,
            "bandwidth_mhz": self.bandwidth_mhz,
            "efficiency": self.efficiency,
            "peak_gain_dbi": self.peak_gain_dbi,
            "vswr": self.vswr,
            "sar_w_per_kg": self.sar_w_per_kg,
            "meets_requirements": self.meets_requirements,
            "notes": self.notes,
        }


def load_device(config: dict) -> dict:
    """Resolve config['device'] to a manifest dict.

    If device.manifest_path is set, it points at a device.json written by
    backend/load_blend.py (bpy runs there, in its own venv, against a .blend
    + materials.json sidecar — see backend/load_blend.py and
    progress_simulation.md step 6). This function only reads that JSON; it
    never imports bpy, so the openEMS side stays out of the bpy venv.
    Inline device fields (if any) are layered on top of the loaded manifest.
    """
    device = config.get("device", {})
    manifest_path = device.get("manifest_path")
    if not manifest_path:
        return device
    import json
    manifest = json.loads(Path(manifest_path).read_text())
    return {**manifest, **{k: v for k, v in device.items() if k != "manifest_path"}}


@dataclass
class FDTDStructure:
    """Bundles what run_fdtd/postprocess need. Not part of the frontend
    contract -- purely an internal hand-off between the three stages."""
    FDTD: object
    port: object
    nf2ff: object
    sim_path: str
    freq: object = None  # set by run_fdtd() after CalcPort


def build_ifa_geometry(candidate: Candidate, band: Band, device: dict, sim: SimOptions) -> FDTDStructure:
    """Step 3/6: ground plane + short pin + radiating arm as CSXCAD PEC
    primitives, fed by an openEMS lumped port. Bare PEC only, no
    dielectrics yet -- that's step 6, once device['components'] carries
    real material data from a Blender export (backend/load_blend.py).

    Geometry convention (see IFA_* constants above): candidate.position_mm
    is the short-circuit (grounded) pin location; candidate.feed_point_mm
    is the feed location, its z giving the pin height (falls back to
    IFA_HEIGHT_MM if 0). If the two collapse to the same (x, y) -- true of
    the current frontend candidate generator, which has no separate
    short-point field -- the short pin is nudged IFA_SHORT_GAP_MM away so
    CSXCAD gets two distinct conductors. The radiating arm runs from the
    short pin, continuing past it (away from the feed) for length_mm.
    """
    import numpy as np
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
        # Candidate has no dedicated short-point field; offset the feed to
        # the side of the short pin (off the arm axis), not along it.
        feed_xy = short_xy + perp_unit * IFA_SHORT_GAP_MM

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

    import tempfile
    sim_path = tempfile.mkdtemp(prefix=f"openems_{candidate.candidate_id}_")

    return FDTDStructure(FDTD=FDTD, port=port, nf2ff=nf2ff, sim_path=sim_path)


def run_fdtd(structure: FDTDStructure, band: Band, sim: SimOptions) -> FDTDStructure:
    """Step 5: run the FDTD solve, then CalcPort over the band's
    frequency window (sim.freq_points samples across
    [band.f_low_ghz, band.f_high_ghz]) to populate S-parameter data on
    structure.port. This is the slow step -- typically minutes even at
    sim.mesh_res == "coarse"; see progress_simulation.md step 7 for the
    runtime knobs.
    """
    import numpy as np
    structure.FDTD.Run(structure.sim_path, verbose=3, cleanup=True)

    n = max(sim.freq_points, 3)
    freq = np.linspace(band.f_low_ghz * 1e9, band.f_high_ghz * 1e9, n)
    structure.port.CalcPort(structure.sim_path, freq)
    structure.freq = freq
    return structure


def postprocess(structure: FDTDStructure, band: Band) -> dict:
    """Step 5: S11 curve -> resonant_ghz / bandwidth_mhz / vswr /
    s11_min_db from the port data run_fdtd() populated. peak_gain_dbi and
    efficiency need an NF2FF run at the resonant frequency (radiated vs.
    accepted power); sar_w_per_kg stays 0.0 until a tissue phantom exists.
    """
    import numpy as np
    port = structure.port
    freq = structure.freq

    s11 = port.uf_ref / port.uf_inc
    s11_db = 20.0 * np.log10(np.abs(s11))
    s11_curve = [{"f_ghz": float(f / 1e9), "s11_db": float(db)}
                 for f, db in zip(freq, s11_db)]

    i_min = int(np.argmin(s11_db))
    s11_min_db = float(s11_db[i_min])
    resonant_ghz = float(freq[i_min] / 1e9)
    gamma = min(float(np.abs(s11[i_min])), 0.999)
    vswr = (1.0 + gamma) / (1.0 - gamma)

    below = s11_db <= band.s11_db_max
    bandwidth_mhz = float((freq[below].max() - freq[below].min()) / 1e6) if below.any() else 0.0

    efficiency = 0.0
    peak_gain_dbi = -99.0
    if s11_min_db <= band.s11_db_max:
        # Coarse angular grid for speed; nf2ff needs a resonance to probe.
        theta = np.arange(-180.0, 180.0, 10.0)
        phi = np.array([0.0, 90.0])
        nf2ff_res = structure.nf2ff.CalcNF2FF(structure.sim_path, freq[i_min], theta, phi)
        p_rad = float(nf2ff_res.Prad[0])
        p_acc = float(port.P_acc[i_min])
        if p_acc > 0:
            efficiency = max(0.0, min(1.0, p_rad / p_acc))
        dmax_db = float(nf2ff_res.Dmax[0])
        peak_gain_dbi = dmax_db + 10.0 * np.log10(efficiency) if efficiency > 0 else dmax_db - 99.0

    meets = s11_min_db <= band.s11_db_max and efficiency >= band.efficiency_min

    return {
        "s11_curve": s11_curve,
        "s11_min_db": s11_min_db,
        "resonant_ghz": resonant_ghz,
        "bandwidth_mhz": bandwidth_mhz,
        "efficiency": efficiency,
        "peak_gain_dbi": peak_gain_dbi,
        "vswr": vswr,
        "sar_w_per_kg": 0.0,  # stub -- needs a tissue phantom, see progress_simulation.md step 5
        "meets_requirements": meets,
        "notes": f"resonance {resonant_ghz:.4f} GHz, S11 {s11_min_db:.1f} dB"
                 + ("" if meets else " (below thresholds)"),
    }


def run_simulation(config: dict) -> dict:
    """Single entry point the FastAPI backend calls. See
    rf/progress_simulation.md for the config/result contract (mirrors
    frontend/src/lib/types.ts Candidate/BandRequirement -> SimResult)."""
    t0 = time.time()
    cand = Candidate(**config["candidate"])
    band = Band(**{k: config["band"][k] for k in
                   ("id", "f_low_ghz", "f_high_ghz", "s11_db_max", "efficiency_min")
                   if k in config["band"]})
    sim = SimOptions(**config.get("sim", {}))
    device = load_device(config)

    try:
        structure = build_ifa_geometry(cand, band, device, sim)
        port_result = run_fdtd(structure, band, sim)
        metrics = postprocess(port_result, band)
        result = SimResult(
            candidate_id=cand.candidate_id,
            status="complete",
            runtime_s=time.time() - t0,
            **metrics,
        )
    except NotImplementedError as e:
        result = SimResult(
            candidate_id=cand.candidate_id,
            status="failed",
            runtime_s=time.time() - t0,
            s11_curve=[], s11_min_db=0.0, resonant_ghz=0.0, bandwidth_mhz=0.0,
            efficiency=0.0, peak_gain_dbi=0.0, vswr=0.0, sar_w_per_kg=0.0,
            meets_requirements=False, notes=f"not runnable yet: {e}",
        )
    return result.to_dict()


if __name__ == "__main__":
    # Tutorial checkpoint (step 2/4): bare IFA over a 100x50mm ground plane,
    # no dielectrics, narrowed GPS L1 sweep (1565-1585 MHz) chosen in
    # progress_simulation.md for a fast first pass.
    demo_config = {
        "candidate": {
            "candidate_id": "gps_l1_ifa_demo",
            "antenna_type": "IFA",
            "position_mm": [95, 25, 0],
            "feed_point_mm": [95, 25, 5],
            "length_mm": 42.6,
            "orientation": "edge",
        },
        "band": {"id": "gps_l1", "f_low_ghz": 1.565, "f_high_ghz": 1.585,
                  "s11_db_max": -8, "efficiency_min": 0.45},
        "device": {"board": {"size_mm": [100, 50, 1.6]}},
        "sim": {"mesh_res": "coarse", "boundary": "MUR", "freq_points": 11},
    }
    import json
    print(json.dumps(run_simulation(demo_config), indent=2))
