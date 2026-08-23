---
name: blend-extract
description: Extract device geometry (parts, world-space bounding boxes in mm, materials with eps_r / sigma) from a Blender .blend build file into geometry.json using the shared tools/extract_blend.py script. Use when a session receives a .blend attachment and must understand the device layout for antenna placement.
---

# blend-extract

Turn a `.blend` build file into `geometry.json` — the facts the antenna
design loop reasons over. The backend runs the **same script** as its
fallback, so your output and its output must agree; do not hand-roll an
alternative extractor.

## Procedure

1. Locate the attachment(s): the `.blend`, and `materials.json` if present
   (a sidecar with the material vocabulary — `eps_r`, `sigma_S_per_m` per
   material key, plus `material_gaps` notes worth reading).
2. Get a Python **3.11** environment with the `bpy` wheel (Blender as a
   module). Fastest options, in order:
   ```bash
   uv run --no-project --python 3.11 --with bpy python tools/extract_blend.py <file.blend> --out out --no-glb --no-stl
   ```
   or, without uv:
   ```bash
   python3.11 -m pip install bpy     # ~220 MB wheel, one-off
   python3.11 tools/extract_blend.py <file.blend> --out out --no-glb --no-stl
   ```
   Add `--materials materials.json` if the sidecar is not already next to
   the `.blend`. `--no-glb --no-stl` skips the viewer/solver exports you
   don't need here (the backend produces those).
3. Read `out/geometry.json`:
   - `size_mm` and `frame` — the device in the canonical frame (mm;
     x = width, y = height, z = thickness; origin at the min corner).
     `frame.unit_source` / `unit_confidence` say how units were decided;
     `orientation_fix` says whether name votes rotated the model. A handset
     is roughly 65-80 x 140-165 x 7-10 mm — if the numbers are off by 10x
     or 1000x, the units were misread: report it.
   - `parts[]` — one per mesh object, largest first: `blender_object`
     (the name to use in replies), `node_path`, `material_key`, `eps_r`,
     `sigma_S_per_m`, `em_source` (sidecar / name-heuristic / none),
     `bbox_mm`, `extent_mm`, `tris`.
   - `material_gaps` — the asset author's own caveats. Read them.
4. Classify for the EM model (the judgment the script does not make):
   - `sigma >= 1e6` → `pec`; `1e3 <= sigma < 1e6` → `lossy_metal`;
     otherwise `dielectric` with its `eps_r`; `eps_r ≈ 1, sigma ≈ 0` → `air`.
   - Roles: `ground` (the largest metal sheet the antenna sits over —
     PCB ground pour, or the display's metal backplate if that is all
     there is), `display`, `frame`, `battery`, `back_cover`, `board`,
     `shield`, `module` (camera, speaker, USB, haptics...), `other`.
   - Parts with `em_source: none` or `name-heuristic` are the ones to
     think about; the rest came from the sidecar and are usually right.
5. Reply with the `spec` action exactly as the session prompt specifies
   (one fenced ```json block: `extracted`, `ground`, `components` you want
   to set/override, `summary`). Keep it compact — no bbox dumps; the backend
   already has them.

## If it fails

Say so in the `spec` reply (`"extracted": {"method": "failed", "notes":
"<error>"}`) and still classify from whatever you could read (object
names alone are informative). The backend has already run the script and
will use its own geometry; your classification overrides still apply.
Do not spend more than a few minutes fighting the environment.
