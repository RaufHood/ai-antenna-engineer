"""Oracle scaling on the real structure: monopole + finite wire-grid ground plane.

NEC only forms junctions at segment ENDPOINTS, so the ground plane must be built
edge-by-edge between lattice nodes -- never as long crossing wires.
MoM solve cost is O(N^3) in segments, so grid density is the feasibility knob.
"""
import time
from PyNEC import nec_context

C = 299_792_458.0
F_MHZ = 868.0
LAM = C / (F_MHZ * 1e6)
RAD = 0.0005


def build(gp_w, gp_h, nx, ny, ant_i, ant_j, arm):
    """Ground plane = nx x ny node lattice, each edge its own wire."""
    ctx = nec_context(); geo = ctx.get_geometry(); tag = 1
    xs = [-gp_w/2 + gp_w*i/(nx-1) for i in range(nx)]
    ys = [-gp_h/2 + gp_h*j/(ny-1) for j in range(ny)]
    for j, y in enumerate(ys):
        for i in range(nx-1):
            geo.wire(tag, 1, xs[i], y, 0, xs[i+1], y, 0, RAD, 1.0, 1.0); tag += 1
    for i, x in enumerate(xs):
        for j in range(ny-1):
            geo.wire(tag, 1, x, ys[j], 0, x, ys[j+1], 0, RAD, 1.0, 1.0); tag += 1
    feed = tag
    geo.wire(feed, 7, xs[ant_i], ys[ant_j], 0, xs[ant_i], ys[ant_j], arm, RAD, 1.0, 1.0)
    ctx.geometry_complete(0)
    ctx.ex_card(0, feed, 1, 0, 0, 1.0, 0, 0, 0, 0, 0)
    ctx.fr_card(0, 1, F_MHZ, 0)
    return ctx, tag


def run(nx, ny, reps=3):
    t0 = time.perf_counter(); z = None; segs = 0
    for _ in range(reps):
        ctx, nw = build(0.10, 0.05, nx, ny, nx-1, ny//2, 0.070)
        ctx.xq_card(0)
        z = ctx.get_input_parameters(0).get_impedance()[0]
        segs = (nx-1)*ny + nx*(ny-1) + 7
    return segs, (time.perf_counter()-t0)/reps, z


print(f"{F_MHZ:.0f} MHz  lambda={LAM*1000:.0f}mm  board 100x50mm  monopole at edge\n")
print(f"{'grid':>8} {'segs':>6} {'ms/sim':>9}   Z (ohm)")
for nx, ny in [(5,3),(7,4),(9,5),(11,6),(15,8),(19,10),(25,13)]:
    try:
        segs, dt, z = run(nx, ny)
        print(f"{nx:>3}x{ny:<4} {segs:>6} {dt*1000:>9.1f}   {z.real:>7.1f} {z.imag:>+8.1f}j")
    except Exception as e:
        print(f"{nx:>3}x{ny:<4}  FAILED: {str(e)[:40]}")
