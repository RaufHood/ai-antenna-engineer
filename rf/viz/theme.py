"""Publication dark theme for every figure and animation in rf/viz.

One import, one call:

    from rf.viz.theme import apply_theme, PALETTE
    apply_theme()

Design language (deliberate, keep consistent across ALL media):
- true-black background (projector-friendly, hides letterboxing in decks)
- Computer Modern (matplotlib's bundled cmr10 -- no font install needed)
- one saturated accent per semantic role, see PALETTE
- 300 dpi default savefig, tight bounding box
"""
from __future__ import annotations

import matplotlib as mpl

BG = "#000000"
FG = "#e8e6e3"          # warm off-white text
GRID = "#2a2a2e"

PALETTE = {
    "s11":       "#00e5ff",   # cyan — reflection curves
    "spec":      "#ff3d71",   # red-pink — requirement/limit lines
    "band":      "#7c4dff",   # violet — target band shading
    "resonance": "#ffd740",   # amber — resonance markers/callouts
    "good":      "#00e676",   # green — PASS
    "bad":       "#ff5252",   # red — FAIL
    "antenna":   "#ffd740",   # amber — the antenna itself in 3D views
    "metal":     "#8c9eff",   # steel blue — conductor part edges
    "dielectric":"#69f0ae",   # mint — dielectric part edges
    "battery":   "#ff8a65",   # coral — battery (the classic antenna killer)
    "outline":   "#5c6bc0",   # indigo — enclosure/board outline
}

# Ordered categorical cycle for "many parts" plots
CYCLE = ["#00e5ff", "#ffd740", "#ff3d71", "#00e676", "#7c4dff",
         "#ff8a65", "#8c9eff", "#69f0ae", "#f48fb1", "#ffff8d"]


def apply_theme() -> None:
    mpl.rcParams.update({
        "figure.facecolor": BG,
        "savefig.facecolor": BG,
        "axes.facecolor": BG,
        "axes.edgecolor": GRID,
        "axes.labelcolor": FG,
        "axes.titlecolor": FG,
        "text.color": FG,
        "xtick.color": FG,
        "ytick.color": FG,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "axes.grid": True,
        "axes.axisbelow": True,
        "legend.facecolor": "#101014",
        "legend.edgecolor": GRID,
        "legend.framealpha": 0.9,
        # Computer Modern, shipped with matplotlib -- no system font needed.
        "font.family": "cmr10",
        "mathtext.fontset": "cm",
        "axes.formatter.use_mathtext": True,  # cmr10 has no unicode minus
        "axes.unicode_minus": False,
        "font.size": 12,
        "axes.titlesize": 15,
        "axes.labelsize": 12.5,
        "figure.dpi": 110,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.15,
        "axes.prop_cycle": mpl.cycler(color=CYCLE),
        "lines.linewidth": 2.2,
    })


def part_color(material_key: str) -> str:
    """Semantic edge colour for a device part by material family."""
    k = (material_key or "").lower()
    if "battery" in k or "lithium" in k or "lipo" in k:
        return PALETTE["battery"]
    if any(m in k for m in ("alumin", "copper", "steel", "titan", "gold", "metal")):
        return PALETTE["metal"]
    return PALETTE["dielectric"]

def cm_text(s: str) -> str:
    """Make a string safe to draw in Computer Modern.

    cmr10 is an OT1-encoded TeX text font: codepoint 0x5F is the dot accent,
    not an underscore. So `c004_ifa_e_t1` renders as `c004˙ifa˙e˙t1` in
    every figure that shows an identifier. Nothing in these labels needs a
    literal underscore, so trade it for the space it was standing in for.
    """
    return s.replace("__", " - ").replace("_", " ")
