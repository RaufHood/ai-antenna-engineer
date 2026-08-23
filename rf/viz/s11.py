"""Hero S11 frequency-response figure for a run directory.

    from rf.viz.s11 import render_s11
    render_s11(load_run("runs/demo"), "runs/demo/media/s11.png")

Reads only the run dict from rf.viz.data.load_run — never the solver.
All styling comes from rf.viz.theme (dark, Computer Modern, 300 dpi).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .theme import FG, PALETTE, apply_theme, cm_text

# Layout constants (inches / points) — geometry, not style.
_FIGSIZE = (9.6, 5.6)


def _mono_family() -> str:
    """Computer Modern typewriter if bundled, else generic monospace."""
    from matplotlib import font_manager
    try:
        font_manager.findfont("cmtt10", fallback_to_default=False)
        return "cmtt10"
    except Exception:
        return "monospace"


def _fmt(value, spec: str, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    try:
        return format(float(value), spec) + suffix
    except (TypeError, ValueError):
        return "n/a"


def _band_label(band: dict) -> str:
    band_id = (band or {}).get("id") or ""
    if not band_id:
        return "Target band"
    pretty = band_id.replace("_", " ").upper()
    return f"{pretty} target band"


def _result_chip(ax, result: dict) -> None:
    """Compact monospace metrics box, top-right; border color = verdict."""
    import matplotlib as mpl
    from matplotlib.offsetbox import AnchoredOffsetbox, TextArea, VPacker

    meets = bool(result.get("meets_requirements"))
    verdict = "PASS" if meets else "FAIL"
    border = PALETTE["good"] if meets else PALETTE["bad"]
    mono = _mono_family()

    eff = result.get("efficiency")
    eff_pct = None if eff is None else 100.0 * float(eff)
    body_lines = [
        f"S11 min {_fmt(result.get('s11_min_db'), '>7.1f', ' dB')}",
        f"BW      {_fmt(result.get('bandwidth_mhz'), '>7.1f', ' MHz')}",
        f"eff     {_fmt(eff_pct, '>7.1f', ' %')}",
        f"VSWR    {_fmt(result.get('vswr'), '>7.2f')}",
    ]
    title = TextArea(verdict, textprops=dict(
        color=border, fontfamily=mono, fontsize=11.5))
    body = TextArea("\n".join(body_lines), textprops=dict(
        color=FG, fontfamily=mono, fontsize=9.5, linespacing=1.45))
    chip = AnchoredOffsetbox(
        loc="upper right",
        child=VPacker(children=[title, body], align="left", pad=0, sep=5),
        pad=0.55, borderpad=0.85, frameon=True)
    chip.patch.set_facecolor(mpl.rcParams["legend.facecolor"])
    chip.patch.set_edgecolor(border)
    chip.patch.set_linewidth(1.4)
    chip.patch.set_alpha(1.0)
    chip.set_zorder(12)
    ax.add_artist(chip)


def render_s11(run: dict, out_png: str) -> str:
    """Render the S11 hero figure for `run` (a rf.viz.data.load_run dict)."""
    apply_theme()
    import matplotlib.pyplot as plt

    result = run.get("result") or {}
    band = run.get("band") or {}
    candidate = run.get("candidate") or {}
    config = run.get("config") or {}
    device = run.get("device")

    out = Path(out_png)
    out.parent.mkdir(parents=True, exist_ok=True)

    curve = result.get("s11_curve") or []
    fig, ax = plt.subplots(figsize=_FIGSIZE)

    if not curve:
        # Degrade gracefully: an honest empty-state, not a crash.
        ax.text(0.5, 0.5, "No S11 curve in this run\n(result.s11_curve is empty)",
                transform=ax.transAxes, ha="center", va="center",
                fontsize=14, color=FG, alpha=0.8)
        ax.set_axis_off()
        fig.savefig(out)
        plt.close(fig)
        return str(out)

    f = np.array([p["f_ghz"] for p in curve], dtype=float)
    s = np.array([p["s11_db"] for p in curve], dtype=float)

    # --- curve -------------------------------------------------------------
    ax.plot(f, s, color=PALETTE["s11"], label="$S_{11}$", zorder=5)

    # --- target band + spec line --------------------------------------------
    f_lo = band.get("f_low_ghz")
    f_hi = band.get("f_high_ghz")
    if f_lo is not None and f_hi is not None:
        ax.axvspan(f_lo, f_hi, color=PALETTE["band"], alpha=0.14,
                   label=_band_label(band), zorder=1)
    spec_db = band.get("s11_db_max")
    if spec_db is not None:
        ax.axhline(spec_db, color=PALETTE["spec"], linestyle="--",
                   linewidth=1.6, label=f"spec {spec_db:g} dB", zorder=4)

    # --- resonance marker ----------------------------------------------------
    f_res = result.get("resonant_ghz")
    if f_res is not None:
        s_res = float(s.min())
        ax.plot([f_res], [s_res], marker="o", markersize=8,
                color=PALETTE["resonance"], markeredgecolor=FG,
                markeredgewidth=0.7, linestyle="none", zorder=8)
        ax.annotate(rf"$f_{{\mathrm{{res}}}} = {f_res:.4f}$ GHz",
                    xy=(f_res, s_res), xytext=(-14, 40),
                    textcoords="offset points", ha="right", va="bottom",
                    fontsize=11.5, color=PALETTE["resonance"],
                    arrowprops=dict(arrowstyle="-|>",
                                    color=PALETTE["resonance"],
                                    linewidth=1.1,
                                    connectionstyle="arc3,rad=0.18",
                                    shrinkA=4, shrinkB=7),
                    zorder=9)

    # --- limits / labels -------------------------------------------------------
    ax.set_xlim(float(f.min()), float(f.max()))
    ax.set_ylim(float(s.min()) - 4.0, 0.0)
    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel("$S_{11}$ (dB)")

    # --- title + solver subtitle ----------------------------------------------
    ant = candidate.get("antenna_type") or "Antenna"
    cid = candidate.get("candidate_id") or "?"
    hint = (device or {}).get("name") or ""
    title = f"{ant} candidate {cm_text(cid)}" + (f" - {hint}" if hint else "")
    sim = config.get("sim") or {}
    if sim:
        subtitle = (f"openEMS FDTD - {sim.get('mesh_res', '?')} mesh"
                    f" - {sim.get('boundary', '?')}")
        ax.set_title(title, pad=28)
        ax.text(0.5, 1.022, subtitle, transform=ax.transAxes,
                ha="center", va="bottom", fontsize=10.5, color=FG, alpha=0.6)
    else:
        ax.set_title(title, pad=12)

    # --- chip, legend, watermark -----------------------------------------------
    _result_chip(ax, result)
    ax.legend(loc="lower right", fontsize=10, borderpad=0.7)

    if "DEMO" in (result.get("notes") or "").upper():
        ax.text(0.015, 0.025, "demo data", transform=ax.transAxes,
                ha="left", va="bottom", fontsize=10, style="italic",
                color=FG, alpha=0.3, zorder=11)

    fig.savefig(out)
    plt.close(fig)
    return str(out)


if __name__ == "__main__":
    from .data import load_run

    run = load_run("runs/demo")
    path = render_s11(run, "runs/demo/media/s11.png")
    print(f"s11 -> {Path(path).resolve()} ({Path(path).stat().st_size} bytes)")
