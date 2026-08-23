"""Backend runner for the SHARED extraction script (tools/extract_blend.py).

The same file Devin executes in its VM runs here in a subprocess with a
bpy-capable interpreter — demo insurance and the source of the viewer glb.
bpy needs Python 3.11 while the backend is 3.12, so the interpreter is
resolved, in order:

  BPY_PYTHON=/path/to/python   (a venv that has `bpy`)
  BLENDER=/path/to/blender     (headless `blender -b --python`)
  uv run --no-project --python 3.11 --with bpy   (ephemeral; first run downloads ~220 MB)

Outputs land in var/devices/<device_id>/ (geometry.json, device.glb,
parts/*.stl) and are reused when the .blend hash matches."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent
SCRIPT = REPO_DIR / "tools" / "extract_blend.py"
VAR_DIR = Path(os.environ.get("DEVICES_DIR", BACKEND_DIR / "var" / "devices"))


class ExtractError(RuntimeError):
    pass


def device_id_for(blend: Path) -> str:
    h = hashlib.sha256()
    with blend.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return f"dev_{h.hexdigest()[:10]}"


def _command(args: list[str]) -> list[str]:
    if py := os.environ.get("BPY_PYTHON"):
        return [py, str(SCRIPT), *args]
    if bl := os.environ.get("BLENDER"):
        return [bl, "-b", "--python", str(SCRIPT), "--", *args]
    return ["uv", "run", "--no-project", "--python", "3.11", "--with", "bpy",
            "python", str(SCRIPT), *args]


def ingest(blend_src: Path, sidecar_src: Path | None, device_id: str | None = None) -> Path:
    """Copy the upload into its device dir (the script wants the sidecar next
    to the .blend, named materials.json). Returns the device dir."""
    device_id = device_id or device_id_for(blend_src)
    d = VAR_DIR / device_id
    d.mkdir(parents=True, exist_ok=True)
    dst = d / blend_src.name
    if dst.resolve() != blend_src.resolve():
        shutil.copyfile(blend_src, dst)
    if sidecar_src and sidecar_src.exists():
        side = d / "materials.json"
        if side.resolve() != sidecar_src.resolve():
            shutil.copyfile(sidecar_src, side)
    return d


def extract_sync(device_dir: Path, timeout_s: float | None = None) -> dict:
    blend = next(device_dir.glob("*.blend"), None)
    if blend is None:
        raise ExtractError(f"no .blend in {device_dir}")
    out = device_dir / "out"
    cached = out / "geometry.json"
    if cached.exists():
        try:
            g = json.loads(cached.read_text())
            if g.get("source_sha256") == hashlib.sha256(blend.read_bytes()).hexdigest():
                return g
        except (json.JSONDecodeError, OSError):
            pass
    args = [str(blend), "--out", str(out)]
    side = device_dir / "materials.json"
    if side.exists():
        args += ["--materials", str(side)]
    timeout_s = timeout_s or float(os.environ.get("EXTRACT_TIMEOUT_S", "900"))
    try:
        proc = subprocess.run(_command(args), capture_output=True, text=True,
                              timeout=timeout_s, cwd=str(REPO_DIR))
    except FileNotFoundError as e:
        raise ExtractError(f"extraction interpreter not found: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise ExtractError(f"extraction timed out after {timeout_s:.0f}s") from e
    if proc.returncode != 0 or not cached.exists():
        tail = "\n".join(proc.stderr.strip().splitlines()[-12:])
        raise ExtractError(f"extract_blend.py failed (rc={proc.returncode}):\n{tail}")
    return json.loads(cached.read_text())


async def extract(device_dir: Path) -> dict:
    return await asyncio.to_thread(extract_sync, device_dir)


def artifact_path(device_dir: Path, name: str) -> Path | None:
    """Resolve a public artifact name to a file inside the device dir."""
    out = device_dir / "out"
    candidates = {
        "geometry.json": out / "geometry.json",
        "device.glb": out / "device.glb",
        "materials.json": device_dir / "materials.json",
    }
    p = candidates.get(name)
    if p is None and name.startswith("parts/") and name.endswith(".stl"):
        p = (out / name).resolve()
        if out.resolve() not in p.parents:
            return None
    return p if p and p.exists() else None
