# Apple iPhone 15 Pro — .blend with materials

`A2848` (US / Puerto Rico, eSIM-only, no SIM tray) · FCC ID `BCG-E8435A`.
Blender 5.2.0 LTS · units are **millimetres** (1 Blender unit = 1 mm).
**191 leaf objects · 13 material keys · 234,814 polygons · 142.4 g modelled.**

- `apple_iphone_15_pro.blend` — self-contained: **0 external file references**.
- `materials.json` — material table: key, EM constants, per-key mass/volume/part
  count, the 10 material gaps, and the omitted-parts record.

## Read this before simulating: the antennas are not in this model

Every radiator was excluded per the brief — antenna flexes, the mmWave module,
the 6 RF coax cables and their connectors, UWB, NFC, the GPS/Wi-Fi/BT combo
elements, the diversity elements, the aperture tuners, and the antenna contact
springs. This is the **platform** the antennas sit in, not the antennas.

Deliberately **kept**, because they are structure rather than radiators:

- the **MagSafe array** (18 magnets + alignment magnet) — a magnet is not a radiator;
- the **inductive charging coil** (12 turns) — a coil is not a radiator;
- the **plastic split lines in the titanium band**, which is the one you care
  about: they are what breaks the frame into **five electrically separate
  segments**. Objects `exterior.frame.band_seg_1..5__stainless`, split by
  `exterior.frame.split_*__nylon`.

## There are no textures — this is a flat material-ID model

Each of the 13 materials is a single Principled BSDF with one flat saturated
base colour. **No image textures, no procedural node trees, no UV maps** on any
of the 191 meshes. The colours exist so material assignment is readable at a
glance, not to look photoreal.

## Material identity (what the solver reads)

Carried three redundant ways — verified consistent on all 191 objects, 0 mismatches:

1. object **name**: `<node_path>__<material_key>` — e.g. `battery.cell__lipo`
2. object **custom property** `material_key`
3. **slot-0 material** `MAT_<key>`

| key | parts | mass | eps_r | sigma (S/m) |
|---|---|---|---|---|
| `lens` | 15 | 39.934 g | 5.5 | 0.003 |
| `lipo` | 1 | 33.367 g | 1.0 | 1e5 |
| `aluminium` | 2 | 17.983 g | 1.0 | 3.5e7 |
| `stainless` | 59 | 17.821 g | 1.0 | 1.1e6 |
| `copper` | 18 | 13.547 g | 1.0 | 5.8e7 |
| `pet` | 18 | 11.696 g | 3.0 | 0.006 |
| `steel` | 24 | 3.342 g | 1.0 | 1.45e6 |
| `fr4` | 1 | 1.839 g | 4.4 | 0.02 |
| `abs` | 33 | 1.571 g | 2.9 | 0.005 |
| `cfrp` | 2 | 0.825 g | 4.5 | 1e4 |
| `rubber` | 11 | 0.271 g | 3.0 | 0.005 |
| `foam` | 2 | 0.095 g | 1.1 | 1e-4 |
| `nylon` | 5 | 0.095 g | 2.9 | 0.002 |

Collections `exterior` (25 objects) and `interior` (166) split the model.

## The 10 material gaps — none of these keys is the real material

The vocabulary has 21 fixed keys; a part with no match is mapped to the nearest
one and **flagged**, never silently substituted. `materials.json` carries the full
record with published constants. The ones that bite hardest for RF:

- **The titanium band is mapped to `stainless`.** Ti-6Al-4V has sigma ~5.8e5 S/m,
  roughly half the `stainless` value, and it is the single most important
  conductor in the device — it *is* the antenna carrier.
- **The MagSafe magnets are mapped to `steel`.** They are sintered NdFeB N52,
  not carbon steel: different sigma, and a large remanent magnetisation that the
  vocabulary cannot express at all.
- **Ceramic Shield and the back glass are mapped to `lens`** (eps_r 5.5). Both are
  glass-ceramics, not optical glass.
- **The OLED stack is mapped to `pet`.** The real stack is polyimide + organic
  layers + thin-film encapsulation + a **metal cathode** — that last layer is a
  conductor this model does not have.
- `cfrp` stands in for pyrolytic graphite, `fr4` for silica-filled epoxy moulding
  compound, `nylon` for glass-filled LCP / PC-ABS, and the silicon dies inside the
  shield cans are not modelled at all (the cans are).

## What was changed relative to the working file

The scene's render output path was an absolute path into the author's Desktop;
it is now `//renders/`. Fake user set on all 13 materials. Geometry, materials,
`material_key` properties and collections are untouched.
