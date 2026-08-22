"""Dev driver: full run without HTTP. `uv run python scripts/dev_run.py`"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


async def main() -> None:
    import os

    from app.geometry.spec import make_anchors, phone_v1
    from app.runs import orchestrator
    from app.runs.store import Run
    from app.sim import pool

    if os.environ.get("AGENT", "mock") == "devin":
        from app.agent.devin import DevinAgent
        agent = DevinAgent()
    else:
        from app.agent.mock import MockAgent
        agent = MockAgent()

    pool.start_pool()
    spec = phone_v1()
    run = Run(id="run_local", prompt="Integrate a 2.4 GHz antenna into this phone",
              band_ids=["wifi24"], spec=spec, anchors=make_anchors(spec))
    await orchestrator.drive(run, agent)

    print(f"\nstatus={run.status} iterations={run.iteration} "
          f"sims={len(run.results)} events={len(run.log.events)}")
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
            print("  agent:", e.payload["text"])
        if e.type.value == "error":
            print("  ERROR:", e.payload)
    print("event mix:", mix)
    pool.shutdown_pool()


if __name__ == "__main__":
    asyncio.run(main())
