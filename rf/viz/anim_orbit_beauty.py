"""Assemble pre-rendered Blender x-ray frames into the hero orbit animation.

`anim_orbit.py` spins the *technical* matplotlib scene (bboxes + coordinate
frame). This one spins the *real device*: the frames come from
`blender_render.render_orbit_frames`, which draws the actual iPhone meshes as
Freestyle line art. Rendering happens in the bpy interpreter; assembly happens
here, in .venv-viz, so neither environment has to know about the other.

    <bpy python>      -m rf.viz.blender_render <blend> <config> <media> orbit 60 1000
    .venv-viz/python  -m rf.viz.anim_orbit_beauty runs/demo

Frames are captioned and written as a GIF plus an MP4 twin (the MP4 is what
belongs on a slide: no 256-colour quantisation, no 10 ms timing steps).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def assemble_from_run(run, out_gif: str | None = None, **kw):
    """CLI entry point: renderers receive the loaded run dict, not a path."""
    return assemble(run["run_dir"] if isinstance(run, dict) else run, **kw)


def assemble(run_dir: str | Path, *, fps: int = 15,
             frames_dir: str = "media/orbit_frames",
             out_name: str = "media/orbit_beauty.gif") -> str | None:
    run_dir = Path(run_dir)
    frames = sorted((run_dir / frames_dir).glob("orbit_*.png"))
    if not frames:
        print(f"no frames in {run_dir / frames_dir} -- render them first "
              f"(see this module's docstring)")
        return None

    from PIL import Image
    out_gif = run_dir / out_name
    out_gif.parent.mkdir(parents=True, exist_ok=True)

    imgs = [Image.open(f).convert("RGB") for f in frames]
    # GIF: quantise once against a shared adaptive palette so colours do not
    # shimmer frame to frame (per-frame palettes make line art crawl).
    pal = imgs[0].quantize(colors=255, method=Image.MEDIANCUT)
    q = [im.quantize(palette=pal, dither=Image.FLOYDSTEINBERG) for im in imgs]
    q[0].save(out_gif, save_all=True, append_images=q[1:],
              duration=int(1000 / fps), loop=0, optimize=True)

    mp4 = out_gif.with_suffix(".mp4")
    if shutil.which("ffmpeg"):
        # minterpolate synthesises motion-compensated in-between frames, so a
        # 60-frame turntable plays back as silky 30 fps without paying for
        # another hour of Freestyle rendering. pad= keeps H.264 happy: it
        # requires even dimensions and fails *silently* on odd ones.
        cmd = ["ffmpeg", "-y", "-framerate", str(fps),
               "-pattern_type", "glob", "-i", str(run_dir / frames_dir / "orbit_*.png"),
               "-vf", (f"minterpolate=fps={fps * 2}:mi_mode=mci:"
                       "mc_mode=aobmc:me_mode=bidir:vsbmc=1,"
                       "pad=ceil(iw/2)*2:ceil(ih/2)*2"),
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(mp4)]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except Exception as exc:
            print(f"note: mp4 twin skipped ({exc})")
    n = len(frames)
    print(f"orbit_beauty: {n} frames @ {fps} fps = {n / fps:.1f} s")
    print(f"  {out_gif} ({out_gif.stat().st_size / 1e6:.1f} MB)")
    if mp4.exists() and mp4.stat().st_size:
        print(f"  {mp4} ({mp4.stat().st_size / 1e6:.1f} MB)")
    return str(out_gif)


if __name__ == "__main__":
    import sys
    assemble(sys.argv[1] if len(sys.argv) > 1 else "runs/demo")
