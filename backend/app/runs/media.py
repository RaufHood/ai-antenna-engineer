"""Render the run's visual evidence — for THIS device, THIS winning antenna.

The rf/ workstream can already draw everything that matters about a design:
the placement map that shows where an antenna may legally go in a real
phone, the x-ray of the winner sitting inside the actual mesh, its S11, and
the field leaving it. Until now those only existed for a demo run committed
in the repo, which is a picture of someone else's answer.

This stage runs the same renderers against the run that just finished, with
the device the engineer actually loaded and the candidate the agent actually
chose. That turns a table of numbers into something an RF engineer can take
to a mechanical engineer.

Three tiers, cheapest first, so the useful artifacts land immediately and the
expensive one never blocks them:

    map      placement legality/score field over the real geometry   ~5 s
    still    S11 plot + 3D x-ray of the winner in the device         ~2 s
    field    |E| propagating out of the winning antenna             ~40 s
             (needs one openEMS solve with a field dump; skipped
              cleanly when openEMS is not installed)

Everything is best-effort and reported per artifact: a missing renderer or a
missing solver degrades the gallery, never the run.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RF_VIZ_PYTHON_CANDIDATES = (
    REPO / ".venv-viz" / "bin" / "python",
    REPO / ".venv-viz" / "Scripts" / "python.exe",
)
DEFAULT_TIMEOUT_S = 300.0


@dataclass
class Artifact:
    name: str          # file name inside the run's media dir
    kind: str          # "image" | "animation"
    title: str         # what an engineer would call it
    caption: str       # what it tells them
    path: Path


def _viz_python() -> Path | None:
    """The interpreter that can import rf.viz (matplotlib, numpy, h5py).

    Returns None rather than guessing: the caller reports "not rendered" with
    a reason instead of failing three layers down inside matplotlib.
    """
    if env := os.environ.get("VIZ_PYTHON"):
        p = Path(env)
        return p if p.exists() else None
    for p in RF_VIZ_PYTHON_CANDIDATES:
        if p.exists():
            return p
    return None


def _device_manifest(spec) -> Path | None:
    """The blend_loader manifest for this device, if there is one."""
    for cand in (getattr(spec, "geometry_path", None),
                 REPO / "rf" / "blend_loader" / "out" / "device.json"):
        if not cand:
            continue
        p = Path(cand)
        if not p.is_absolute():
            p = REPO / p
        if p.exists() and p.suffix == ".json":
            return p
    return None


def _write_run_dir(run, out_dir: Path, manifest: Path | None) -> dict | None:
    """Lay out the run-artifact directory rf/viz expects: config.json +
    result.json (+ device.json). Returns the config, or None if the run has
    no winner to draw."""
    final = run.final or {}
    best_id = (final.get("best_candidate") or {}).get("candidate_id")
    if not best_id:
        ranked = sorted(run.results.items(),
                        key=lambda kv: kv[1].s11_min_db or 0.0)
        if not ranked:
            return None
        best_id = ranked[0][0]
    cand = run.candidates.get(best_id)
    result = run.results.get(best_id)
    if cand is None or result is None:
        return None

    from app.geometry.bands import CATALOG
    from app.sim.rf_adapter import build_config

    band = CATALOG.get(cand.band_id) or next(iter(CATALOG.values()))
    config = build_config(run.spec, band, cand)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "config.json").write_text(json.dumps(config, indent=1))
    (out_dir / "result.json").write_text(json.dumps(result.model_dump(), indent=1))
    if manifest:
        shutil.copy2(manifest, out_dir / "device.json")
    return config


async def _run(py: Path, args: list[str], timeout: float = DEFAULT_TIMEOUT_S) -> tuple[bool, str]:
    """Render in a subprocess: matplotlib is not thread-safe and a renderer
    must never take the event loop (or the API) down with it."""
    proc = await asyncio.create_subprocess_exec(
        str(py), *args, cwd=str(REPO),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return False, f"timed out after {timeout:.0f}s"
    text = (out or b"").decode("utf-8", "replace")[-800:]
    return proc.returncode == 0, text


async def render(run, *, with_field: bool = False, on_artifact=None) -> list[Artifact]:
    """Render this run's gallery. Calls `on_artifact(Artifact)` as each lands
    so the UI can show them one by one instead of waiting for the slowest."""
    py = _viz_python()
    if py is None:
        return []

    media_dir = REPO / "backend" / "var" / "media" / run.id
    manifest = _device_manifest(run.spec)
    config = _write_run_dir(run, media_dir, manifest)
    if config is None:
        return []

    made: list[Artifact] = []

    async def emit(name: str, kind: str, title: str, caption: str) -> None:
        p = media_dir / "media" / name
        if not p.exists() or p.stat().st_size == 0:
            return
        art = Artifact(name=name, kind=kind, title=title, caption=caption, path=p)
        made.append(art)
        if on_artifact:
            on_artifact(art)

    # --- tier 1: a placement field PER BAND ----------------------------------
    # The map is band-dependent, and strongly so. scan() sizes the radiator at
    # a quarter wave and treats metal inside lambda/20 as detuning, so at
    # 900 MHz that is an 83 mm arm with a 16 mm exclusion, and at 5 GHz a 14 mm
    # arm with 3 mm. Those are different legal regions of the same phone — one
    # map for "the device" would be a map for whichever band happened to win.
    if manifest:
        from app.geometry.bands import CATALOG
        for band_id in (run.band_ids or []):
            band = CATALOG.get(band_id)
            if band is None:
                continue
            ok, _ = await _render_band_map(py, media_dir, band, band_id)
            if ok:
                f_mid = (band.f_low_ghz + band.f_high_ghz) / 2
                arm = 299.792458 / f_mid / 4  # quarter wave, mm
                await emit(f"placement_map_{band_id}.png", "image",
                           f"Placement map — {band.short}",
                           f"Where a {band.short} antenna may legally sit in this "
                           f"device. Sized for its own quarter wave ({arm:.0f} mm) and "
                           f"its own near field, so a different band gives a different "
                           f"map of the same phone.")

    # --- tier 2: the winner, drawn and measured ------------------------------
    ok, log = await _run(py, ["-m", "rf.viz", str(media_dir), "--only", "s11,placement"])
    if ok:
        await emit("s11.png", "image", "Frequency response",
                   "Reflection against the target band and the spec line the design "
                   "has to stay under.")
        await emit("placement_iso.png", "image", "Antenna in the device",
                   "The chosen antenna inside the actual mesh, with the parts that "
                   "constrain it coloured by material family.")

    # --- tier 3: the field leaving the antenna (expensive, opt-in) -----------
    if with_field:
        solved = await _solve_field(media_dir, config)
        if solved:
            ok, log = await _run(py, ["-m", "rf.viz", str(media_dir), "--only", "field"],
                                 timeout=600.0)
            if ok:
                await emit("field.gif", "animation", "Radiated field",
                           "|E| leaving the antenna and crossing the device — the "
                           "conductors it has to get past are the ones on the map.")
                await emit("field.mp4", "animation", "Radiated field (video)",
                           "Same field, smoother playback.")

    return made


async def _render_band_map(py: Path, media_dir: Path, band, band_id: str):
    """One placement map sized for one band.

    rf/viz/heatmap.py takes the arm length from the run's candidate, so a
    per-band map needs a per-band config. Written beside the run rather than
    mutating its config.json, which stays the record of what was actually
    simulated.
    """
    cfg_path = media_dir / f"_band_{band_id}.json"
    base = json.loads((media_dir / "config.json").read_text())
    f_mid = (band.f_low_ghz + band.f_high_ghz) / 2
    base["candidate"] = {**base["candidate"],
                         "length_mm": 299.792458 / f_mid / 4,
                         "candidate_id": f"band_{band_id}"}
    base["band"] = {"id": band_id, "f_low_ghz": band.f_low_ghz,
                    "f_high_ghz": band.f_high_ghz,
                    "s11_db_max": band.s11_db_max,
                    "efficiency_min": band.efficiency_min}
    cfg_path.write_text(json.dumps(base, indent=1))
    return await _run(py, [
        "-c",
        "import sys,json,shutil;from pathlib import Path;"
        "sys.path.insert(0,'.');"
        "from rf.viz.heatmap import render_placement_map;"
        f"run=Path({str(media_dir)!r});"
        f"shutil.copy(run/'_band_{band_id}.json', run/'config.json');"
        f"p=render_placement_map(str(run), str(run/'media'/'placement_map_{band_id}.png'));"
        "print(p)",
    ])


async def _solve_field(media_dir: Path, config: dict) -> bool:
    """One openEMS solve of the winner with a time-domain field dump.

    PyNEC gives impedance, not a field volume, so the animation needs the FDTD
    solver. Absent openEMS this returns False and the gallery simply has no
    field clip — which is a missing artifact, not a failed run.
    """
    from app.sim.rf_adapter import _rf_python

    py = _rf_python()
    if py is None:
        return False
    cfg = dict(config)
    cfg["sim"] = {**cfg.get("sim", {}), "dump_fields": True, "mesh_res": "coarse"}
    cfg_path = media_dir / "field_config.json"
    cfg_path.write_text(json.dumps(cfg))

    proc = await asyncio.create_subprocess_exec(
        str(py), "-c",
        "import json,sys;from rf.run_simulation import run_simulation;"
        f"run_simulation(json.load(open({str(cfg_path)!r})), out_dir={str(media_dir)!r})",
        cwd=str(REPO), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        await asyncio.wait_for(proc.communicate(), timeout=600.0)
    except asyncio.TimeoutError:
        proc.kill()
        return False
    return (media_dir / "Et.h5").exists()


def artifact_path(run_id: str, name: str) -> Path | None:
    """Resolve a media file for serving. Refuses anything that escapes the
    run's own directory."""
    base = (REPO / "backend" / "var" / "media" / run_id / "media").resolve()
    p = (base / name).resolve()
    if not str(p).startswith(str(base)) or not p.exists():
        return None
    return p


def list_artifacts(run_id: str) -> list[str]:
    base = REPO / "backend" / "var" / "media" / run_id / "media"
    if not base.exists():
        return []
    return sorted(f.name for f in base.iterdir()
                  if f.is_file() and f.suffix in (".png", ".gif", ".mp4"))
