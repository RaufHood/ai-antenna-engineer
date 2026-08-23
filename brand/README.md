# kevin — brand marks

Parody mark for the hackathon project. Kevin is the one who does antennas.

## Files

| file | use |
|---|---|
| `kevin-mark.svg` | icon only, square (200×200), favicon-safe |
| `kevin-lockup.svg` | icon + wordmark, horizontal (395×122) |

Both are monochrome and paint with `currentColor`, so they inherit the
surrounding text colour and work on light or dark without a second file.
Devin's own mark is monochrome black — the neon-green palette some tools
invent for it isn't theirs, and the parody only lands if the colour is right.

## The joke

At a glance it's the three-hexagon node cluster you already know, pointing
right. Three details only show up when you lean in — all of them vanish by
about 32 px, which is the point:

1. **The hairline whip** off the top of the right hexagon, with a ball tip.
   Turns the cluster into a small creature with one antenna up.
2. **The face in the hole.** The round negative space at the junction is
   Devin's; the two eyes and the smile in it are Kevin's.
3. **The face is made of hexagons.** The eyes are pointy-top hexagons at
   circumradius 3.4 — the same construction as the three big ones. The mouth
   is three straight segments on the hexagon's own 60° slope — a flat base
   with the corners lifted 2.6, no curve anywhere. The full hexagon underside
   lifts them 5.89, which turns the smile into a rictus; it is truncated on
   purpose. Above roughly 120 px you can see what the parts are; below that
   they read as plain dots and a line.

There is not a freehand curve in the mark. Every edge is either a hexagon edge
or a circle, the mouth is stroked at 2.2 — the same weight as the whip — and
its corners are round-joined to match the rounded hexagon corners, so the face
is built from the icon's own parts rather than drawn on top of it.

## Construction

Pointy-top hexagons, circumradius 38, centres at (64,66), (64,134), (133,100)
— an equilateral arrangement. Corners are rounded by stroking each polygon at
width 8 with `stroke-linejoin="round"` rather than by hand-built arcs. The
hole is a 21-radius mask circle at the centroid, biting all three hexagons.

The wordmark is drawn, not set: monoline at stroke 9.5 on a 52 x-height, butt
caps, geometric skeleton. No font dependency, so it renders identically
everywhere.
