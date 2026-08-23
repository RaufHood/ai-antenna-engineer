"""Turn a finished run's event log into a replay tape.

`RecordingAgent` writes a tape while a live agent is running, which only helps
if you remembered to set RECORD_TAPE before spending the quota. This recovers
one afterwards, from the run the backend already kept: the agent's proposals
are in `candidates_proposed` and its prose is in `agent_message`, which is
everything a tape needs.

The point is what the "fast" option in the picker actually is. A heuristic is
a stand-in; a recovered tape is the real agent's real decisions on this device,
replayed for free. Same solves either way — the solver re-runs every candidate
— so nothing here is a recording of results, only of choices.

    python scripts/tape_from_run.py <run_id> --out var/tapes/<name>.json
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path


def fetch(base: str, path: str) -> dict:
    with urllib.request.urlopen(f"{base}{path}", timeout=30) as r:
        return json.loads(r.read())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_id")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--force", action="store_true",
                    help="tape even a failed/stopped/fallback run (see the guard below)")
    args = ap.parse_args()

    run = fetch(args.base, f"/runs/{args.run_id}")
    events = fetch(args.base, f"/runs/{args.run_id}/log")["events"]

    # A tape claims to hold THE AGENT'S decisions. A run that failed, was
    # stopped, or was finished by the heuristic ends with a rationale the
    # orchestrator wrote, not the agent — and taping it attributes that text
    # to the agent for every future replay. It happened: the first iPhone tape
    # ended with Devin appearing to say "agent channel failed ([Errno 8] ...)",
    # because the recorded session died on a dropped poll. Refuse instead.
    final = run.get("final") or {}
    status = run.get("status")
    spec_source = run.get("spec_source") or ""
    why = None
    if status != "finished":
        why = f"the run is {status!r}, not 'finished'"
    elif "mock-fallback" in spec_source:
        why = "the heuristic agent finished it (spec_source has mock-fallback)"
    elif final.get("status") == "stopped":
        why = "it was stopped by the user"
    elif "agent channel failed" in (final.get("rationale") or ""):
        why = "its rationale is the orchestrator's failure notice, not the agent's"
    if why and not args.force:
        sys.exit(
            f"refusing to tape run {args.run_id}: {why}.\n"
            f"The tape would attribute words to the agent that the agent never "
            f"wrote. Record a clean run, or pass --force if you know better."
        )
    if why:
        print(f"WARNING: taping anyway ({why}) — --force", file=sys.stderr)

    turns: list[dict] = []
    pending: list[str] = []

    def flush() -> None:
        if pending:
            turns.append({"kind": "narrate", "lines": list(pending)})
            pending.clear()

    for e in events:
        kind, payload = e["type"], e.get("payload") or {}
        if kind == "agent_message":
            text = payload.get("text")
            if text:
                pending.append(text)
        elif kind == "candidates_proposed":
            flush()
            # Every batch is replayed as an explicit simulate. A sweep is just a
            # batch the agent generated, and the candidates it produced are
            # already here — replaying them names the same designs without
            # re-deriving the range.
            turns.append({"kind": "action", "action": {
                "action": "simulate", "candidates": payload.get("candidates") or []}})

    flush()
    turns.append({"kind": "action", "action": {
        "action": "done",
        "ranking": final.get("ranking") or [],
        "rationale": final.get("rationale") or "",
    }})
    turns.append({"kind": "close", "report": final.get("agent_report")})

    spec = run["spec"]
    w, h, t = spec["board"]["size_mm"]
    doc = {
        "version": 1,
        "run_prompt": run.get("prompt") or "",
        "band_ids": run.get("band_ids") or [b["id"] for b in spec["requirements"]["bands"]],
        "device": spec["name"],
        "device_id": spec.get("device_id"),
        "n_anchors": len(run.get("anchors") or []),
        "agent": "DevinAgent",
        "recovered_from_run": args.run_id,
        "turns": turns,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=1), encoding="utf-8")

    n_act = sum(1 for x in turns if x["kind"] == "action")
    n_cand = sum(len(x["action"].get("candidates", []))
                 for x in turns if x["kind"] == "action")
    print(f"{spec['name']} ({w:.0f} x {h:.0f} x {t:.0f} mm)")
    print(f"{n_act} actions, {n_cand} candidates, "
          f"{sum(1 for x in turns if x['kind'] == 'narrate')} narrations -> {args.out}")


if __name__ == "__main__":
    sys.exit(main())
