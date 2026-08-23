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
    band_id: str = ""  # which antenna this picture is of


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


def _winner_for_band(run, band_id: str):
    """The candidate this run actually chose for one band.

    Prefers the run's own ranking — that is the agent's decision — and falls
    back to the deepest match in band, so a run that ended early still draws
    something rather than nothing.
    """
    mine = [(cid, r) for cid, r in run.results.items()
            if (c := run.candidates.get(cid)) is not None and c.band_id == band_id]
    if not mine:
        return None
    ranking = (run.final or {}).get("ranking") or []
    for cid in ranking:
        for mine_cid, _ in mine:
            if mine_cid == cid:
                return run.candidates[cid]
    best = min(mine, key=lambda kv: kv[1].s11_min_db or 0.0)
    return run.candidates[best[0]]


def _write_run_dir(run, cand, band, out_dir: Path, manifest: Path | None) -> dict | None:
    """Lay out the artifact directory rf/viz expects for ONE antenna:
    config.json + result.json (+ device.json).

    One directory per band, because every renderer reads the run's single
    config.json and each band has its own winner. Sharing one directory would
    mean every picture described whichever antenna was written last.
    """
    result = run.results.get(cand.candidate_id)
    if result is None:
        return None

    from app.sim.rf_adapter import build_config

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
    """Render this run's gallery — one full set per band, for the antenna the
    agent actually chose for that band.

    A multi-band run is several antenna designs, not one. Each gets its own
    directory (every renderer reads a single config.json, so they cannot
    share), and its outputs are copied out under a band-suffixed name into one
    flat media directory the HTTP route can serve.

    `on_artifact(Artifact)` fires as each file lands, so the cheap pictures
    appear while the expensive ones are still solving.
    """
    py = _viz_python()
    if py is None:
        return []

    from app.geometry.bands import CATALOG

    media_dir = REPO / "backend" / "var" / "media" / run.id
    out_media = media_dir / "media"
    out_media.mkdir(parents=True, exist_ok=True)
    manifest = _device_manifest(run.spec)
    made: list[Artifact] = []

    async def emit(src_name: str, band_id: str, kind: str, title: str,
                   caption: str, band_dir: Path) -> None:
        src = band_dir / "media" / src_name
        if not src.exists() or src.stat().st_size == 0:
            return
        stem, _, ext = src_name.rpartition(".")
        name = f"{stem}_{band_id}.{ext}"
        shutil.copy2(src, out_media / name)
        art = Artifact(name=name, kind=kind, title=title, caption=caption,
                       path=out_media / name, band_id=band_id)
        made.append(art)
        if on_artifact:
            on_artifact(art)

    async def one_band(band_id: str) -> None:
        band = CATALOG.get(band_id)
        if band is None:
            return
        cand = _winner_for_band(run, band_id)
        if cand is None:
            return
        band_dir = media_dir / band_id
        config = _write_run_dir(run, cand, band, band_dir, manifest)
        if config is None:
            return
        short = band.short

        # --- cheap: the map, the response, the antenna in the mesh -----------
        # The map is sized from this band's own candidate, so a different band
        # gives a different legal region of the same phone.
        only = "s11,placement" + (",map" if manifest else "")
        ok, _ = await _run(py, ["-m", "rf.viz", str(band_dir), "--only", only])
        if ok:
            arm = 299.792458 / ((band.f_low_ghz + band.f_high_ghz) / 2) / 4
            await emit("placement_map.png", band_id, "image",
                       f"Placement map — {short}",
                       f"Where a {short} antenna may legally sit in this device. "
                       f"Sized for its own quarter wave ({arm:.0f} mm) and its own "
                       f"near field, so a different band maps the same phone "
                       f"differently.", band_dir)
            await emit("s11.png", band_id, "image", f"Frequency response — {short}",
                       "Reflection against the target band and the spec line the "
                       "design has to stay under.", band_dir)
            await emit("placement_iso.png", band_id, "image",
                       f"Antenna in the device — {short}",
                       "The chosen antenna inside the actual mesh, with the parts "
                       "that constrain it coloured by material family.", band_dir)

        # --- expensive: one FDTD solve, three animations out of it -----------
        if not with_field:
            return
        if not await _solve_field(band_dir, config):
            return
        # One rf.viz call, not three: each invocation pays a fresh interpreter
        # and a matplotlib import, which cost more than two of the renders. The
        # tool renders whatever it can and reports the rest, so a single failure
        # still leaves the others.
        await _run(py, ["-m", "rf.viz", str(band_dir),
                        "--only", "field,dashboard,orbit"], timeout=900.0)
        for fname, title, caption in _ANIMATIONS:
            await emit(fname, band_id, "animation", f"{title} — {short}",
                       caption, band_dir)

    # Bands are independent designs in their own directories, so they render
    # concurrently. Two bands took twice as long as one for no reason; the
    # solves are seconds and the renderers are separate processes.
    await asyncio.gather(*(one_band(b) for b in (run.band_ids or [])))
    return made


_ANIMATIONS = [
    ("field.mp4", "Radiated field",
     "|E| leaving the antenna and crossing the device — the conductors it has "
     "to get past are the ones on the map."),
    ("field.gif", "Radiated field (GIF)",
     "The same frames, for pasting into a deck."),
    ("dashboard.mp4", "Instrumented run",
     "The field, the response and the spec line together, so the wave and the "
     "number it produces move in step."),
    ("dashboard.gif", "Instrumented run (GIF)",
     "The same frames, for pasting into a deck."),
    ("orbit.mp4", "The placement in the round",
     "The chosen antenna orbited inside the device, which is how a mechanical "
     "engineer will ask to see it."),
    ("orbit.gif", "The placement in the round (GIF)",
     "The same frames, for pasting into a deck."),
]


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
    # "coarse" is lambda/10 at f_high — 12 mm cells at 2.4 GHz, which is wider
    # than the phone is thick. The field dump then comes back one cell deep and
    # the animation has nothing to draw. "fine" (lambda/20) resolves the slice.
    cfg["sim"] = {**cfg.get("sim", {}), "dump_fields": True, "mesh_res": "fine"}
    cfg_path = media_dir / "field_config.json"
    cfg_path.write_text(json.dumps(cfg))

    # run_simulation writes its own result.json into out_dir, overwriting the
    # PyNEC result every renderer reads. The two solvers disagree — a coarse
    # FDTD mesh on a wire model reports -0.8 dB where PyNEC reports -14.7 —
    # so the pictures rendered before the solve described a passing design and
    # the ones after stamped the same antenna FAIL. Keep the run's own result
    # authoritative and file the FDTD answer under its own name, where it is a
    # second opinion instead of a contradiction.
    result_path = media_dir / "result.json"
    keep = result_path.read_bytes() if result_path.exists() else None

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
        ok = False
    else:
        ok = (media_dir / "Et.h5").exists()

    if keep is not None:
        if result_path.exists():
            shutil.copy2(result_path, media_dir / "result_openems.json")
        result_path.write_bytes(keep)
    return ok


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
