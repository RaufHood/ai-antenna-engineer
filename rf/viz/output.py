"""Shared animation writer for every renderer in rf/viz.

One place owns the two things that are easy to get wrong per-module:

- **Even pixel dimensions.** H.264 (yuv420p) requires both dimensions to be
  divisible by 2. A matplotlib figure whose height rounds to an odd pixel
  count (e.g. 660x919) makes ffmpeg fail *silently*, leaving a 0-byte .mp4
  next to a perfectly good GIF. We pad to even instead of cropping, so
  nothing is lost, and we delete the file if the encode still failed.
- **Smoothness.** GIF timing quantises to 10 ms and caps at 256 colours;
  the MP4 twin is what you actually put on a slide. Both are written from
  the same FuncAnimation so they can never drift apart.
"""
from __future__ import annotations

import shutil
from pathlib import Path


def save_animation(anim, out_gif: str | Path, fps: int, dpi: int,
                   mp4_dpi: int | None = None) -> str:
    """Write `anim` as a GIF, plus an .mp4 twin when ffmpeg is available.

    `mp4_dpi` lets the mp4 be rendered larger than the GIF (a 1080p twin of
    a 648p GIF, say) from the same animation. Returns the GIF path -- the
    contract every renderer promises; the mp4 is a bonus and never raises.
    """
    from matplotlib import animation

    out = Path(out_gif)
    out.parent.mkdir(parents=True, exist_ok=True)
    anim.save(str(out), writer=animation.PillowWriter(fps=fps), dpi=dpi)

    if not shutil.which("ffmpeg"):
        return str(out)

    mp4 = out.with_suffix(".mp4")
    try:
        anim.save(
            str(mp4),
            writer=animation.FFMpegWriter(
                fps=fps,
                bitrate=6000,
                # pad (not crop) to even dimensions, then force the pixel
                # format every player expects.
                extra_args=["-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                            "-pix_fmt", "yuv420p"],
            ),
            dpi=mp4_dpi or dpi,
        )
    except Exception:
        pass
    # a silent ffmpeg failure leaves an empty file behind: don't ship it
    if mp4.exists() and mp4.stat().st_size == 0:
        mp4.unlink()
    return str(out)
