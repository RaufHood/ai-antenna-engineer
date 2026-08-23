"""Pre-render the Evidence gallery that ships with the app.

The gallery is built from a run, and a run belongs to a session: open the app
fresh and there is nothing to look at until you have waited out a study and a
render. That is the wrong first impression for a tool whose whole claim is
"here is the evidence", and it is a bad thing to depend on live in a demo.

So two studies are rendered ahead of time — Wi-Fi 2.4 and GPS L1, the two
bands the pitch talks about — and their artifacts are parked under a stable
id the normal media route already serves. The app shows them whenever the
current session has none of its own, clearly labelled as prepared rather than
passed off as this run's output.

Nothing here is staged: these are real PyNEC solves and a real openEMS field
dump, produced by the same orchestrator the live button calls. Re-running this
script is the only way they change.

    backend/.venv/bin/python scripts/build_showcase.py

Takes a couple of minutes. Skips the GIFs: each is the same frames as its MP4
at three times the size, and the gallery draws the MP4.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.mock import MockAgent
from app.geometry.spec import default_spec
from app.runs import orchestrator
from app.runs.store import Run
from app.sim import pool
from app.sim.priors import anchors_for

REPO = Path(__file__).resolve().parents[2]
SHOWCASE_ID = "_showcase"
OUT = REPO / "backend" / "var" / "media" / SHOWCASE_ID
BANDS = ["wifi24", "gps_l1"]


async def build() -> None:
    pool.start_pool()
    try:
        media_dir = OUT / "media"
        if OUT.exists():
            shutil.rmtree(OUT)
        media_dir.mkdir(parents=True)

        entries: list[dict] = []
        for band_id in BANDS:
            t0 = time.time()
            spec = default_spec([band_id])
            anchors, source = anchors_for(spec, [band_id])
            run = Run(
                id=f"showcase_{band_id}",
                prompt=f"Place a {band_id} antenna in this phone.",
                band_ids=[band_id], spec=spec, anchors=anchors, device=None,
                extract_mode="backend", ambiguities=[], spec_source="manifest",
                media=True,
            )
            await orchestrator.drive(run, MockAgent())

            best = (run.final or {}).get("best_candidate") or {}
            res = run.results.get(best.get("candidate_id"))
            verdict = (
                f"S11 {res.s11_min_db:.1f} dB, efficiency {res.efficiency:.0%}, "
                f"{res.clearance_mm} mm clear"
                if res else "no winner"
            )
            print(f"  {band_id}: {len(run.results)} solves, {len(run.media_artifacts)} "
                  f"artifacts, {time.time() - t0:.0f}s — {verdict} (anchors {source})")

            # The GIF of a clip is the same frames as its MP4 at three times the
            # size, and the gallery draws the MP4. Ship one of each.
            for art in run.media_artifacts:
                if art["name"].endswith(".gif"):
                    continue
                src = REPO / "backend" / "var" / "media" / run.id / "media" / art["name"]
                if not src.exists() or src.stat().st_size == 0:
                    print(f"     ! missing {art['name']}")
                    continue
                shutil.copy2(src, media_dir / art["name"])
                entries.append({
                    "name": art["name"], "kind": art["kind"], "title": art["title"],
                    "caption": art["caption"], "band_id": art["band_id"],
                    "url": f"/runs/{SHOWCASE_ID}/media/{art['name']}",
                })

        (OUT / "showcase.json").write_text(json.dumps({
            "built_from": "mock agent + PyNEC solves + one openEMS field dump per band",
            "device": default_spec(BANDS).name,
            "bands": BANDS,
            "artifacts": entries,
        }, indent=1), encoding="utf-8")

        total = sum(f.stat().st_size for f in media_dir.iterdir())
        print(f"\n{len(entries)} artifacts, {total / 1e6:.1f} MB -> {media_dir}")
    finally:
        pool.shutdown_pool()


if __name__ == "__main__":
    asyncio.run(build())
