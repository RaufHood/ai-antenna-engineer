"""Band catalogue — mirrors frontend/src/lib/device.ts `phoneV1.requirements`
verbatim (ADR-8). Requirements are NOT in the .blend; they come from here,
selected by band id at run creation."""
from __future__ import annotations

from app.models import BandRequirement, Requirements, SarLimit

_BANDS = [
    {"id": "lte_low", "name": "B5 / n5 low-band", "short": "B5", "service": "Cellular low-band",
     "f_low_ghz": 0.824, "f_high_ghz": 0.894, "clearance_mm": 24, "s11_db_max": -6,
     "efficiency_min": 0.4, "antenna_types": ["IFA", "frame_slot", "PIFA"],
     "region_pref": {"bottom": 1, "top": 0.72, "left": 0.5, "right": 0.5}, "color": "#34d399"},
    {"id": "gps_l1", "name": "GPS L1", "short": "GPS", "service": "GNSS",
     "f_low_ghz": 1.559, "f_high_ghz": 1.61, "clearance_mm": 14, "s11_db_max": -8,
     "efficiency_min": 0.45, "antenna_types": ["IFA", "ceramic_chip", "patch_array"],
     "region_pref": {"bottom": 0.35, "top": 1, "left": 0.6, "right": 0.6}, "color": "#fbbf24"},
    {"id": "wifi24", "name": "Wi-Fi / BT 2.4 GHz", "short": "WiFi 2.4", "service": "ISM",
     "f_low_ghz": 2.4, "f_high_ghz": 2.4835, "clearance_mm": 12, "s11_db_max": -8,
     "efficiency_min": 0.5, "antenna_types": ["IFA", "monopole", "ceramic_chip"],
     "region_pref": {"bottom": 0.8, "top": 0.9, "left": 0.65, "right": 0.65}, "color": "#a78bfa"},
    {"id": "n78", "name": "n78 C-band", "short": "n78", "service": "5G NR sub-6",
     "f_low_ghz": 3.3, "f_high_ghz": 3.8, "clearance_mm": 9, "s11_db_max": -6,
     "efficiency_min": 0.5, "antenna_types": ["IFA", "monopole", "frame_slot"],
     "region_pref": {"bottom": 0.85, "top": 0.85, "left": 0.8, "right": 0.8}, "color": "#22d3ee"},
    {"id": "wifi5", "name": "Wi-Fi 5 GHz", "short": "WiFi 5", "service": "UNII",
     "f_low_ghz": 5.15, "f_high_ghz": 5.85, "clearance_mm": 7, "s11_db_max": -8,
     "efficiency_min": 0.5, "antenna_types": ["monopole", "IFA", "patch_array"],
     "region_pref": {"bottom": 0.7, "top": 0.95, "left": 0.75, "right": 0.75}, "color": "#f472b6"},
]

CATALOG: dict[str, BandRequirement] = {
    b["id"]: BandRequirement.model_validate(b) for b in _BANDS}


def requirements_for(band_ids: list[str] | None = None) -> Requirements:
    """Full catalogue by default (the frontend shows all bands); the run's
    `band_ids` picks which ones the agent must satisfy."""
    ids = [b for b in (band_ids or list(CATALOG)) if b in CATALOG]
    return Requirements(
        bands=[CATALOG[b] for b in ids] or list(CATALOG.values()),
        vswr_max=3.0, isolation_db_max=-12.0,
        sar_limit=SarLimit(standard="FCC", w_per_kg=1.6, mass_g=1))


def unknown(band_ids: list[str]) -> list[str]:
    return [b for b in band_ids if b not in CATALOG]
