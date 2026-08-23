"""Dev driver: full run without HTTP.

    uv run python scripts/dev_run.py                       # canned spec, mock agent
    BLEND=../data/phone_synth_v1/phone_synth_v1.blend uv run python scripts/dev_run.py
    AGENT=devin EXTRACT=agent BLEND=... uv run python scripts/dev_run.py

Env: AGENT=mock|devin, BLEND=<.blend path> (materials.json beside it is picked
up), EXTRACT=agent|backend (default agent when BLEND is set), BANDS=wifi24.
"""
import asyncio
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.config import describe_agent_config, load_env  # noqa: E402

load_env()          # backend/.env -> os.environ (shell always wins)


async def main() -> None:
    print(f"config: {describe_agent_config()}")
    from app.geometry import bands
    from app.geometry.spec import make_anchors, phone_v1
    from app.runs import devices, orchestrator
    from app.runs.store import Run
    from app.sim import pool

    kind = os.environ.get("AGENT", "mock")
    if kind == "replay":
        from app.agent.replay import ReplayAgent
        agent = ReplayAgent(os.environ.get("REPLAY_TAPE", "var/tapes/last.json"))
        print(f"replaying {agent.path} (recorded from {agent.meta.get('agent')})")
    elif kind == "devin":
        from app.agent.devin import DevinAgent
        agent = DevinAgent()
    else:
        from app.agent.mock import MockAgent
        agent = MockAgent()

    # Wrap whatever we chose so one live run can be kept and replayed later.
    if tape := os.environ.get("RECORD_TAPE"):
        from app.agent.replay import RecordingAgent
        agent = RecordingAgent(agent, tape)
        print(f"recording this run to {tape}")

    pool.start_pool()
    band_ids = os.environ.get("BANDS", "wifi24").split(",")
    device = None
    if blend := os.environ.get("BLEND"):
        bp = pathlib.Path(blend).resolve()
        side = bp.with_name("materials.json")
        device = devices.register(bp, side if side.exists() else None)
        print(f"extracting {bp.name} -> {device.dir} ...")
        await devices.prepare(device, band_ids)
        if device.status != "ready":
            sys.exit(f"extraction failed: {device.error}")
        print(f"device {device.id}: {device.name}, {device.geometry['n_parts']} parts, "
              f"{device.geometry['size_mm']} mm, {len(device.anchors)} anchors, "
              f"artifacts {device.artifacts()[:3]}...")
        for a in device.ambiguities:
            print("  caveat:", a)
        spec = device.spec.model_copy(update={"requirements": bands.requirements_for(band_ids)})
        anchors = device.anchors
        mode = os.environ.get("EXTRACT", "agent")
    else:
        spec, anchors, mode = phone_v1(), None, "backend"
        anchors = make_anchors(spec)

    run = Run(id="run_local", prompt="Integrate a 2.4 GHz antenna into this phone",
              band_ids=band_ids, spec=spec, anchors=anchors, device=device,
              extract_mode=mode, ambiguities=list(device.ambiguities) if device else [],
              spec_source="backend" if device else "canned")
    await orchestrator.drive(run, agent)

    print(f"\nstatus={run.status} iterations={run.iteration} "
          f"sims={len(run.results)} events={len(run.log.events)} "
          f"spec_source={run.spec_source}")
    f = run.final or {}
    if f.get("best"):
        b, c = f["best"], f["best_candidate"]
        print(f"best: {c['antenna_type']} @ {c['anchor_id']} L={c['length_mm']}mm "
              f"params={c['params']}")
        print(f"      s11min={b['s11_min_db']}dB res={b['resonant_ghz']}GHz "
              f"bw={b['bandwidth_mhz']}MHz Z={b['impedance_ohm']} "
              f"meets={b['meets_requirements']}")
        print(f"rationale: {f['rationale']}")
    else:
        print("no best result!", f.get("rationale"))
    mix: dict[str, int] = {}
    for e in run.log.events:
        mix[e.type.value] = mix.get(e.type.value, 0) + 1
        if e.type.value == "agent_message":
            print("  agent:", e.payload["text"][:300])
        if e.type.value == "decision" and e.stage == "extract":
            print("  extract:", e.payload)
        if e.type.value == "error":
            print("  ERROR:", e.payload)
    print("event mix:", mix)

    # Persist the artifacts. report.py renders them on demand from the run
    # record and nothing was writing them out, so a finished run left no trace
    # on disk — and "trigger to artifact with nobody touching it in between"
    # is the whole point. One directory per run, named so runs sort by time.
    from app.runs import report as report_mod
    out = pathlib.Path(os.environ.get("ARTIFACT_DIR", "var/artifacts")) / run.id
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name in report_mod.artifact_names(run):
        rendered = report_mod.render(run, name)
        if not rendered:
            continue
        body, _media = rendered          # render() -> (body, media_type)
        (out / name).write_text(body, encoding="utf-8")
        written.append(name)
    print(f"artifacts -> {out}/  ({', '.join(written)})")

    pool.shutdown_pool()


if __name__ == "__main__":
    asyncio.run(main())
