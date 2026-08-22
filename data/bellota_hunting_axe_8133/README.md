# Bellota hunting axe 8133 — .blend with materials and textures

Blender 5.2.0 LTS · units are **millimetres** (1 Blender unit = 1 mm) · 3 parts, 845.2 g.

- `bellota_hunting_axe_8133.blend` — self-contained: **0 external file references**.
- `materials.json` — the material table: key, EM constants, shader, real material, gaps.

Open it and switch the viewport to **Material Preview**.

## There are no texture files — that is not an omission

Every material is **procedural** and the meshes have **no UV maps**, so there is
nothing on disk to ship next to the .blend. The textures *are* the node trees:

- **Wood** — `PBR_beech_varnished`, `PBR_beech_endgrain`: Noise Texture → Mapping →
  ColorRamp on generated coordinates, noise stretched along **Y** (the handle
  axis) so the grain runs the right way.
- **Head** — `PBR_head_two_finishes`: an **Attribute** node reads the per-vertex
  float attribute **`u_from_edge`** (each vertex's true distance from the cutting
  edge, baked by `bx_pbr.bake_u_from_edge`) into MapRange → MixShader. That is
  what gives the polished bit against the lacquered body on a single forging —
  what Bellota actually ships, "Pulido y lacado".

**So the look lives only inside the .blend.** Exporting to OBJ/STL/glTF loses it:
`u_from_edge` is mesh data those formats cannot carry, and procedural nodes do
not survive either. If you need it elsewhere, the meshes must be UV-unwrapped and
the shaders baked to image maps — that has not been done.

## The five materials in the file

| Blender object | `material_key` | eps_r | sigma (S/m) | shader in slot 0 | mass |
|---|---|---|---|---|---|
| `head.forging__steel` | `steel` | 1.0 | 1.45e6 | `PBR_head_two_finishes` | 680.0 g |
| `haft.handle__walnut` | `walnut` | 2.2 | 0.012 | `PBR_beech_varnished` | 162.1 g |
| `haft.wedge__walnut` | `walnut` | 2.2 | 0.012 | `PBR_beech_endgrain` | 3.1 g |

`MAT_steel` and `MAT_walnut` — the flat material-ID colours used by the FDTD /
material pass — are also in the file, unassigned but kept alive with a fake user.
Swap them into slot 0 to get the flat pass back; each object's own `material_key`
custom property says which one it takes.

Material identity is carried three redundant ways, none of which the colour layer
touches: the object **name** (`<node_path>__<material_key>`), the object custom
property **`material_key`**, and the **`MAT_<key>`** datablock.

## Before using these for simulation, read `materials.json`

- **`steel` carries no `mu_r`** — it is 1 by omission. Forged carbon tool steel is
  ferromagnetic (mu_r ~40–100 at 1–13 GHz), and Zs scales as sqrt(mu_r), so
  leaving it at 1 misstates the loss of 80% of the object's mass. Set it by hand.
- **`walnut` stands in for beech** (*Fagus sylvatica*, 12% MC assumed): beech is
  10–30% higher in eps_r, and wood is anisotropic — along the grain runs 15–25%
  above across it.
- The varnish film (~30–80 µm) is not modelled.

## What was changed relative to the working file

1. `MAT_steel` / `MAT_walnut` were orphaned (0 users, no fake user) and would have
   been purged on the next save — **fake user set on every material**.
2. The `BX_ENCODE` scene was removed. It was a video-encode-only scene whose
   180-frame image strip was the file's only source of external references, all
   of them absolute paths into the author's Desktop.

Geometry, materials and attributes are otherwise untouched: 376,558 polygons
across the three meshes, same as the source.
