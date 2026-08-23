# Pitch deck

The nine slides we present. Open `index.html` — arrow keys, space, or swipe.

```
open pitch-deck/index.html      # the deck itself, one self-contained file
open pitch-deck/kevin-pitch.pdf # static export, 1920×1080 per page
pitch-deck/png/                 # one PNG per slide, for submission forms
```

**Live:** https://damiavicensramis.github.io/kevin-pitch/

| # | | |
|---|---|---|
| 01 | Cover | the wordmark and the one-line claim |
| 02 | Why antennas | one sentence, three shipment figures |
| 03 | Where they come from | the manual loop, priced per stage |
| 04 | The market | three segments, three drivers |
| 05 | The market, by analogy | what AI did to the software loop, and the gap it leaves here |
| 06 | The product | the same four beats as slide 03, in Kevin's numbers |
| 07 | Demo | the live run — the capture is the backstop |
| 08 | The team | |
| 09 | Questions | |

Speaker-led: the slides carry figures, the narration stays with the speaker.
One claim per slide, and numbers instead of sentences — nothing on a slide
that the speaker is going to say out loud anyway.

Slides 03 and 06 are deliberately the same component. The manual loop prices
its stages in amber (`≈ 1 hour`, `days to weeks`); Kevin's prices the same
beats in green (`83 ms`, `it decides when to stop`). Read against each other
they are the whole argument, so keep them structurally identical.

## Where each figure comes from

Two kinds of number are on these slides, and they are labelled differently in
each slide's footer:

**Measured on this repo** — cite these if anyone pushes.

| slide | claim | source |
|---|---|---|
| 03 | ≈ 1 h per full-wave run of a whole device | [deep_research_on_challenge.md](../deep_research_on_challenge.md) |
| 06 | 83 ms per Wi-Fi 2.4 GHz solve | measured per solve; the same number the UI shows |
| 06 | 38 candidates · 1 min 29 s upload to finished design | live Devin run, 23 Aug 2026, captured for `assets/ui-idle.png` |
| 06 | 191 parts screened, no solver | [rf/placement.py](../rf/placement.py) — `python -m app.sim.priors` |
| 07 | 176 parts · Wi-Fi / BT 2.4 GHz | the iPhone 15 Pro build file the app loads |

**External industry estimates** — not ours, and every slide carrying them says
so in its footer.

| slide | claim |
|---|---|
| 02 | 5.4B Bluetooth · 3.8B Wi-Fi devices a year · 6–12 antennas per phone |
| 03 | 3–6 weeks per redesign cycle · $130–220K loaded salary · 73% of EE roles unfilled after six months (IEEE) |
| 04 | $28B → $54B hardware · $23B → $50B 5G · $1.5B → $2.9B design software · +16.9%/yr · 30B+ IoT · 4 → 8 antennas per car |
| 05 | 47M developers · $7.6B tooling · $3.5B AI coding tools · 84% adoption |

Do not present an external estimate as a measurement. The defensible numbers
are the measured ones, and they are enough: **38 candidates simulated in
1 min 29 s, at 83 ms of solver time each.**

## Screenshots

`assets/ui-idle.png` is a real capture of the running app at 3200×1800,
taken with Playwright against `localhost:3000` at `deviceScaleFactor: 2`.
Re-shoot it the same way if the UI changes — a screenshot at 1× looks soft
on a 1920-wide slide.

`assets/ui-result.png`, `assets/placement-map.png` and `assets/orbit.mp4` are
left in place but no longer used by any slide; the trimmed deck hands the
finished run to the live demo instead of showing a still of it.

## Two files that look like results and are not

Both live in `runs/demo/media/` and are deliberately absent from the deck:

- **`s11.png`** is watermarked *demo data*. `rf/viz/data.py` fabricates that
  resonance analytically.
- **`field.gif` / `field.mp4`** are the same fixture. `synth_demo_run()`
  writes "an outgoing damped cylindrical wave from the feed … mimicking
  openEMS's HDF5 layout" — a hand-written wave, not a solve.

## Editing

Colours are `:root` variables at the top of the `<style>` block; the accent
is the app's own `--signal #4c9dff`, taken from
[frontend/src/app/globals.css](../frontend/src/app/globals.css). Type roles
follow, then components, then one commented `<section>` per slide. Slide
numbers are generated at runtime, so sections can be reordered freely.

Every slide is one of two registers: dark for the seven documentation slides,
flooded `--signal` for the cover and the close. Adding a third look breaks the
deck — reach for an existing component (`.stats`, `.pipeline` + `.pcost`,
`.ledger`, `.compare`, `.tick`) before writing a new one.

The PNGs and the PDF are both built from the live page at 1920×1080, and the
build refuses to export if Barlow and IBM Plex Mono have not loaded — a
fallback-font render is not this deck. The PDF is assembled from those PNGs
rather than printed from the page, because Chrome's paged renderer silently
drops slides from a document this tall.

**This folder is a copy.** The deck is developed at
[damiavicensramis/kevin-pitch](https://github.com/damiavicensramis/kevin-pitch),
which is what GitHub Pages serves. Edit there and re-copy, or the two drift.
