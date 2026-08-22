"""Antenna geometry builders.

Contract (also taught to Devin by the nec-builder skill): a builder receives the
CSXCAD-free NEC geometry object, the chassis lattice, the Candidate, and the
next free wire tag; it appends wires and returns (feed_tag, feed_segment).
All builders must:
- land plane-touching endpoints EXACTLY on lattice nodes (junction rule),
- keep segment length within ~lambda/40..lambda/15,
- use metres (contracts are mm; convert at the boundary).

Agent-authored builders are hot-loaded here after passing sim/calibrate.py.
"""
from __future__ import annotations

from app.models import Candidate

from . import ifa, monopole

_REGISTRY = {
    "monopole": monopole.build,
    "IFA": ifa.build,
}


def build(geo, model, cand: Candidate, next_tag: int) -> tuple[int, int]:
    try:
        fn = _REGISTRY[cand.antenna_type]
    except KeyError:
        raise ValueError(
            f"no builder for antenna_type={cand.antenna_type!r}; "
            f"available: {sorted(_REGISTRY)}") from None
    return fn(geo, model, cand, next_tag)


def register(name: str, fn) -> None:
    """Used by the calibration gate to hot-load agent-authored builders."""
    _REGISTRY[name] = fn


def available() -> list[str]:
    return sorted(_REGISTRY)
