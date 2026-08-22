"""Offline self-test of the backend seams — no Devin, no bpy, ~10 s.

    uv run python scripts/selftest.py

Covers: canned loop with the mock agent, rf_adapter field mapping against a
stubbed rf.run_simulation, mock fallback when the agent channel dies before
any simulation, user notes reaching the agent, report rendering, and — if a
cached device exists under var/devices — the agent-extraction turn + brief.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.geometry.spec import make_anchors, phone_v1  # noqa: E402
from app.models import Candidate, DoneRequest, SimulateRequest  # noqa: E402
from app.runs import orchestrator, report  # noqa: E402
from app.runs.store import Run  # noqa: E402
from app.sim import pool, rf_adapter  # noqa: E402
from app.sim.score import hints_for  # noqa: E402


def test_rf_adapter() -> None:
    spec = phone_v1()
    band = spec.requirements.bands[0]
    cand = Candidate(candidate_id="a1", anchor_id="c_bl", band_id="wifi24",
                     antenna_type="IFA", position_mm=(6, 6, 5.5), feed_point_mm=(6, 6, 5.5),
                     length_mm=30.0, orientation="corner", params={"height_mm": 3.0, "gap_mm": 5})
    cfg = rf_adapter.build_config(spec, band, cand)
    assert set(cfg["candidate"]) == {"candidate_id", "antenna_type", "position_mm",
                                     "feed_point_mm", "length_mm", "orientation"}
    assert cfg["candidate"]["feed_point_mm"][2] == 3.0 and cfg["band"]["id"] == "wifi24"
    assert "manifest_path" not in cfg["device"] and cfg["device"]["board"]["size_mm"]

    # solve() shells out to rf/.venv's interpreter (rf.cli, stdin/stdout JSON) --
    # openEMS is Python-3.11-only, this process is 3.12 (see rf_adapter's
    # module docstring). Stub subprocess.run itself rather than importing rf.
    stub_out = {
        "candidate_id": cand.candidate_id, "status": "complete", "runtime_s": 12.5,
        "s11_curve": [{"f_ghz": 2.4, "s11_db": -9.0}, {"f_ghz": 2.44, "s11_db": -15.0}],
        "s11_min_db": -15.0, "resonant_ghz": 2.44, "bandwidth_mhz": 80.0, "efficiency": 0.6,
        "peak_gain_dbi": 1.5, "vswr": 1.4, "sar_w_per_kg": 0.0, "meets_requirements": True,
        "notes": "stub"}

    def _out_path(args) -> pathlib.Path:
        return pathlib.Path(args[args.index("--out") + 1])

    real_run, real_rf_python = rf_adapter.subprocess.run, rf_adapter._rf_python
    rf_adapter._rf_python = lambda: pathlib.Path("stub-python")
    try:
        def fake_ok(args, **k):
            _out_path(args).write_text(json.dumps(stub_out))
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")
        rf_adapter.subprocess.run = fake_ok
        r = rf_adapter.solve(spec, band, cand)
        assert r.status == "complete" and r.s11_min_db == -15.0 and r.impedance_ohm == (0.0, 0.0)
        assert not any("radiation resistance" in h for h in hints_for(spec, band, cand, r))

        # a crash before the result file is written (e.g. no openEMS on this
        # machine) -- rf.cli's own except-handler normally still writes a
        # "failed" result, but a subprocess-level crash (no CSXCAD, engine
        # segfault) can leave no file at all; that's the path under test here
        rf_adapter.subprocess.run = lambda args, **k: types.SimpleNamespace(
            returncode=1, stdout="", stderr="ImportError: no module named CSXCAD")
        r = rf_adapter.solve(spec, band, cand)
        assert r.status == "failed" and "ImportError" in r.notes

        def boom(*a, **k):
            raise rf_adapter.subprocess.TimeoutExpired(cmd="rf.cli", timeout=1)
        rf_adapter.subprocess.run = boom
        r = rf_adapter.solve(spec, band, cand)
        assert r.status == "failed" and "timed out" in r.notes
    finally:
        rf_adapter.subprocess.run, rf_adapter._rf_python = real_run, real_rf_python

    rf_adapter._rf_python = lambda: None
    try:
        r = rf_adapter.solve(spec, band, cand)
        assert r.status == "failed" and "rf/.venv not found" in r.notes
    finally:
        rf_adapter._rf_python = real_rf_python
    print("ok  rf_adapter mapping + subprocess dispatch + failure paths")


class _Dying:
    async def start(self, ctx): pass
    async def brief(self, ctx): pass
    async def next_action(self, rep): raise RuntimeError("boom")
    async def narrate(self): return []
    async def close(self, reason): return None


class _Noting:
    seen: list[str] = []

    def __init__(self) -> None:
        self.n = 0

    async def start(self, ctx): self.ctx = ctx
    async def brief(self, ctx): pass

    async def next_action(self, rep):
        if rep:
            _Noting.seen += rep.notes
        self.n += 1
        if self.n == 1:
            a = self.ctx.anchors[-1]
            return SimulateRequest(action="simulate", candidates=[Candidate(
                candidate_id="x1", anchor_id=a.id, band_id="wifi24", antenna_type="IFA",
                position_mm=a.pos_mm, feed_point_mm=a.pos_mm, length_mm=31,
                orientation="edge", params={"gap_mm": 5.5})])
        return DoneRequest(action="done", ranking=["x1"], rationale="ok")

    async def narrate(self): return []
    async def close(self, reason): return {"status": "concluded", "final": {"rationale": "r"}}


async def test_loop() -> None:
    spec = phone_v1()
    run = Run(id="t_canned", prompt="p", band_ids=["wifi24"], spec=spec, anchors=make_anchors(spec))
    from app.agent.mock import MockAgent
    await orchestrator.drive(run, MockAgent())
    assert run.status == "finished" and run.final["best"]["meets_requirements"]
    assert [e.seq for e in run.log.events] == list(range(1, len(run.log.events) + 1))
    print(f"ok  canned loop: {run.iteration} iterations, {len(run.results)} sims, "
          f"best {run.final['best_candidate']['anchor_id']} {run.final['best']['s11_min_db']} dB")

    run = Run(id="t_fallback", prompt="p", band_ids=["wifi24"], spec=spec, anchors=make_anchors(spec))
    await orchestrator.drive(run, _Dying())
    assert run.status == "finished" and run.final["best"] and "mock-fallback" in run.spec_source
    print("ok  agent death before first sim -> mock fallback finished the run")

    run = Run(id="t_notes", prompt="p", band_ids=["wifi24"], spec=spec, anchors=make_anchors(spec))
    run.inbox.append("prefer the bottom edge")
    await orchestrator.drive(run, _Noting())
    assert any("NOTE FROM THE USER: prefer the bottom edge" in n for n in _Noting.seen)
    assert run.final["agent_report"]["status"] == "concluded"
    md = report.markdown(run)
    assert "# Antenna design report" in md and "Agent's structured report" in md
    assert report.render(run, "s11_x1.csv")[0].startswith("f_ghz,s11_db")
    assert "x1" in json.dumps(report.run_json(run))
    print("ok  user note delivered, agent report captured, artifacts render:",
          report.artifact_names(run))


async def test_device_loop() -> None:
    from app.geometry import extract as ex
    from app.runs import devices
    cached = sorted(ex.VAR_DIR.glob("*/out/geometry.json"))
    if not cached:
        print("--  no cached device under var/devices; skipping extraction-turn test "
              "(run dev_run.py with BLEND=... once)")
        return
    ddir = cached[0].parent.parent
    blend = next(ddir.glob("*.blend"))
    dev = devices.register(blend, ddir / "materials.json")
    await devices.prepare(dev, ["wifi24"])
    assert dev.status == "ready", dev.error
    from app.agent.mock import MockAgent
    from app.geometry import bands
    run = Run(id="t_device", prompt="p", band_ids=["wifi24"],
              spec=dev.spec.model_copy(update={"requirements": bands.requirements_for(["wifi24"])}),
              anchors=dev.anchors, device=dev, extract_mode="agent", spec_source="backend")
    await orchestrator.drive(run, MockAgent())
    assert run.status == "finished" and run.spec_source == "agent" and run.final["best"]
    assert run.spec.geometry_path and run.spec.geometry_path.endswith("geometry.json")
    dec = [e for e in run.log.events if e.type.value == "decision" and e.stage == "extract"]
    assert dec and dec[0].payload["decision"] == "spec accepted"
    print(f"ok  device {dev.id} ({dev.spec.name}): extraction turn, cross-check, "
          f"{len(run.results)} sims, best {run.final['best']['s11_min_db']} dB")


async def main() -> None:
    test_rf_adapter()
    pool.start_pool()
    try:
        await test_loop()
        await test_device_loop()
    finally:
        pool.shutdown_pool()
    print("ALL OK")


if __name__ == "__main__":
    asyncio.run(main())
