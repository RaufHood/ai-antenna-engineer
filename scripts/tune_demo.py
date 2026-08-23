"""Brute-force tuning sweep for the bare-board GPS-L1 IFA demo candidate.

77 solver calls at ~1 s each. Finds the (arm length, feed gap) with the
deepest in-band S11 and persists that run's artifacts for the media suite.
This is the manual preview of exactly the loop the Devin agent automates.
"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from rf.run_simulation import run_simulation

BASE = {
    "band": {"id": "gps_l1", "f_low_ghz": 1.565, "f_high_ghz": 1.585,
             "s11_db_max": -8, "efficiency_min": 0.45},
    "device": {"board": {"size_mm": [100, 50, 1.6]}},
    "sim": {"mesh_res": "coarse", "boundary": "MUR", "freq_points": 41},
}

def cand(length, gap):
    return {"candidate_id": f"L{length:g}_G{gap:g}", "antenna_type": "IFA",
            "position_mm": [95, 25, 0], "feed_point_mm": [95, 25 - gap, 5],
            "length_mm": length, "orientation": "edge"}

t0 = time.time()
rows = []
for L in [35, 37, 39, 41, 43, 45, 47, 49, 51, 53, 55]:
    for G in [2, 3, 4, 5, 6, 7, 8]:
        cfg = dict(BASE, candidate=cand(L, G))
        r = run_simulation(cfg)
        rows.append({"L": L, "G": G, "s11": r["s11_min_db"],
                     "f_res": r["resonant_ghz"], "vswr": r["vswr"]})
        print(f"L={L:2g} G={G:g}  S11={r['s11_min_db']:7.2f} dB  "
              f"f={r['resonant_ghz']:.4f}  vswr={r['vswr']:6.1f}", flush=True)

rows.sort(key=lambda x: x["s11"])
best = rows[0]
print(f"\nBEST: L={best['L']} G={best['G']}  S11={best['s11']:.2f} dB "
      f"@ {best['f_res']:.4f} GHz   ({time.time()-t0:.0f}s total)")
Path("runs").mkdir(exist_ok=True)
Path("runs/sweep_results.json").write_text(json.dumps(rows, indent=2))

# persist the winner with field dump for the media pipeline
cfg = dict(BASE, candidate=dict(cand(best["L"], best["G"]),
                                candidate_id="gps_l1_ifa_tuned"))
cfg["sim"] = dict(BASE["sim"], dump_fields=True)
r = run_simulation(cfg, out_dir="runs/gps_l1_ifa_tuned")
print(json.dumps({k: r[k] for k in ("s11_min_db", "resonant_ghz",
      "bandwidth_mhz", "vswr", "meets_requirements")}, indent=2))
