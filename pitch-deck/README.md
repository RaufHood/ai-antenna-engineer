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
| 01 | Cover | the wordmark, nothing else |
| 02 | The problem | three figures for the manual loop, five for how often it repeats |
| 03 | How it works | the six stages, and the millisecond solve that makes them possible |
| 04 | The product | a live capture of one study, start to report |
| 05 | Inside the loop | the geometry it reads and the positions it rules out |
| 06 | The result | 27 real candidate responses converging on the accepted design |
| 07 | What it costs | same study, both ways, with the arithmetic shown |
| 08 | The team | |
| 09 | Close | |

Speaker-led: the slides carry figures, the narration stays with the speaker.

## Every figure traces back to this repo

The one exception is the market strip on slide 02 — external industry
estimates, labelled as such on the slide.

| slide | claim | where it comes from |
|---|---|---|
| 02 | ≈1 h per full-wave run · 15 mm keep-out | [deep_research_on_challenge.md](../deep_research_on_challenge.md) |
| 03 | 1.9 / 17 / 83 / 404 ms · 2.0 s | measured per solve; the same numbers the UI shows |
| 04 | 29 solves, finished 0:01 | live capture of the running app |
| 05 | 191 parts, 106 conductive, 455 of 1034 points, 5 legal of 20 | [rf/placement.py](../rf/placement.py) — `python -m app.sim.priors` |
| 06 | the candidate sweep | one polyline per `s11_*.csv` in `backend/var/artifacts/run_local/`, plotted point-for-point; the accepted design is `c013` |
| 06 | 97% efficiency · 172.6 MHz · 3 iterations | that run's `report.md` and `run.json` |
| 07 | 41 × 91 ms = 3.7 s against 41 × 1 h | measured solve time. The full-wave hour and the $130K–$220K loaded salary are external estimates, and the arithmetic is printed on the slide |

If anyone pushes on the cost claim, the defensible number is the measured
one: **3.7 s of solver time for a 41-candidate study.**

## Two files that look like results and are not

Both live in `runs/demo/media/` and are deliberately absent from the deck:

- **`s11.png`** is watermarked *demo data*. `rf/viz/data.py` fabricates that
  resonance analytically.
- **`field.gif` / `field.mp4`** are the same fixture. `synth_demo_run()`
  writes "an outgoing damped cylindrical wave from the feed … mimicking
  openEMS's HDF5 layout" — a hand-written wave, not a solve.

`orbit_beauty` **is** real (Blender frames of the actual geometry), which is
why the deck's `assets/orbit.mp4` is re-cut from it: motion on the page
without claiming any physics.

## Editing

Colours are `:root` variables at the top of the `<style>` block; the accent
is the app's own `--signal #4c9dff`, taken from
[frontend/src/app/globals.css](../frontend/src/app/globals.css). Type roles
follow, then components, then one commented `<section>` per slide. Slide
numbers are generated at runtime, so sections can be reordered freely.

The PDF is built by screenshotting each slide, not by printing the page —
Chrome's paged renderer silently drops slides from a document this tall.

**This folder is a copy.** The deck is developed at
[damiavicensramis/kevin-pitch](https://github.com/damiavicensramis/kevin-pitch),
which is what GitHub Pages serves. Edit there and re-copy, or the two drift.
