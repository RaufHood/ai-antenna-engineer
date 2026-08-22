"""Calibration: does our oracle reproduce the textbook half-wave dipole?

Reference (Balanis / any antenna text): a thin half-wave dipole in free space
resonates (X = 0) at a length of ~0.47-0.48 lambda, with R_in ~ 70-73 ohm.
If we don't reproduce this, nothing downstream can be trusted.
"""
import time
from PyNEC import nec_context

C = 299_792_458.0
F0 = 300e6                 # 300 MHz -> lambda = 1.0 m exactly
LAM = C / F0
RADIUS = 0.0005            # thin wire
SEGMENTS = 41              # odd -> feed at centre segment


def dipole_impedance(length_m: float, freq_mhz: float) -> complex:
    ctx = nec_context()
    geo = ctx.get_geometry()
    half = length_m / 2.0
    geo.wire(1, SEGMENTS, 0, 0, -half, 0, 0, half, RADIUS, 1.0, 1.0)
    ctx.geometry_complete(0)
    ctx.ex_card(0, 1, (SEGMENTS + 1) // 2, 0, 0, 1.0, 0, 0, 0, 0, 0)
    ctx.fr_card(0, 1, freq_mhz, 0)
    ctx.xq_card(0)
    return ctx.get_input_parameters(0).get_impedance()[0]


t0 = time.time()
print(f"lambda at {F0/1e6:.0f} MHz = {LAM:.3f} m\n")
print(f"{'L/lambda':>9} {'R (ohm)':>10} {'X (ohm)':>10}")
best = None
for ratio in [0.44, 0.45, 0.46, 0.47, 0.475, 0.48, 0.49, 0.50]:
    z = dipole_impedance(ratio * LAM, F0 / 1e6)
    print(f"{ratio:>9.3f} {z.real:>10.2f} {z.imag:>10.2f}")
    if best is None or abs(z.imag) < abs(best[1].imag):
        best = (ratio, z)
elapsed = time.time() - t0

r, z = best
print(f"\nResonance (|X| minimal): L = {r:.3f} lambda, Z = {z.real:.1f} {z.imag:+.1f}j ohm")
print(f"Textbook:                L ~ 0.47-0.48 lambda, R ~ 70-73 ohm")
ok_len = 0.44 <= r <= 0.49
ok_r = 60.0 <= z.real <= 85.0
print(f"\nlength  {'PASS' if ok_len else 'FAIL'}   R  {'PASS' if ok_r else 'FAIL'}")
print(f"8 sweeps in {elapsed:.2f}s  ->  {elapsed/8*1000:.0f} ms per simulation")
