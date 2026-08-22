"""Thin CLI wrapper around run_simulation(), for callers that can't import
this package in-process (the FastAPI backend runs Python 3.12; openEMS/CSXCAD
are Python 3.11-only wheels installed in rf/.venv — see rf/README.md Setup).
Those callers shell out to rf/.venv's interpreter instead
(backend/app/sim/rf_adapter.py does exactly this).

Reads one config dict as JSON from stdin, writes the SimResult dict as JSON
to the file at --out. **Not stdout** -- openEMS's C++ engine writes its own
verbose progress logging directly to the process's stdout (confirmed live:
running this against a real config interleaves "openEMS 64bit -- version
..." / per-timestep energy lines with whatever this script prints), so a
JSON result on stdout is not reliably parseable. Same problem, same fix as
tools/extract_blend.py already uses for bpy's console spam: write the
result to a file, don't rely on stdout for structured data.

    python -m rf.cli --out result.json < config.json

Exit code is always 0 if stdin/the config were readable at all -- a failure
inside run_simulation() (including "no openEMS on this machine") is reported
as a normal "failed"-status result written to --out, not a crash, so the
caller always gets one parseable file back. A non-zero exit / no output file
means something more fundamental broke (bad --out path, stdin unreadable).

Run as `python -m rf.cli` from the repo root -- relative imports need
package context, same rule as every other rf/ module (see rf/README.md).
"""
from __future__ import annotations

import argparse
import json
import sys

from .run_simulation import run_simulation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="path to write the result JSON to")
    args = parser.parse_args(argv)

    config: dict = {}
    try:
        config = json.loads(sys.stdin.read())
        result = run_simulation(config)
    except Exception as e:
        result = {
            "candidate_id": config.get("candidate", {}).get("candidate_id", ""),
            "status": "failed", "runtime_s": 0.0, "s11_curve": [], "s11_min_db": 0.0,
            "resonant_ghz": 0.0, "bandwidth_mhz": 0.0, "efficiency": 0.0,
            "peak_gain_dbi": 0.0, "vswr": 0.0, "sar_w_per_kg": 0.0,
            "meets_requirements": False,
            "notes": f"rf.cli error: {type(e).__name__}: {e}",
        }
    with open(args.out, "w") as f:
        json.dump(result, f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
