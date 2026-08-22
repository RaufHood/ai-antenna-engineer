"""Resolves config['device'] to a manifest dict."""
from __future__ import annotations

import json
from pathlib import Path


def load_device(config: dict) -> dict:
    """If device.manifest_path is set, it points at a device.json written
    by rf/blend_loader/load_blend.py (bpy runs there, in its own venv,
    against a .blend + materials.json sidecar — see
    rf/blend_loader/load_blend.py and progress_simulation.md step 6). This
    function only reads that JSON; it never imports bpy, so the openEMS
    side stays out of the bpy venv. Inline device fields (if any) are
    layered on top of the loaded manifest.
    """
    device = config.get("device", {})
    manifest_path = device.get("manifest_path")
    if not manifest_path:
        return device
    manifest = json.loads(Path(manifest_path).read_text())
    return {**manifest, **{k: v for k, v in device.items() if k != "manifest_path"}}
