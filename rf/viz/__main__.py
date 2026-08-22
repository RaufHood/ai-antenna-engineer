"""One-command media pipeline for a run directory.

    .venv-viz/bin/python -m rf.viz runs/demo
    .venv-viz/bin/python -m rf.viz runs/demo --only s11,dashboard

Creates <run>/media/ and calls every renderer in rf/viz. Each renderer is
imported lazily inside its own branch, so a sibling module that does not
exist yet (or fails) never kills the rest of the pipeline. Ends with a
summary table (name, output, size, seconds). Exit code 0 if at least one
renderer produced output, non-zero if everything failed.
"""
from __future__ import annotations

import argparse
import importlib
import sys
import time
from pathlib import Path

# name, module (relative to rf.viz), preferred entry points, default output
_RENDERERS = [
    ("s11",       ".s11",           ("render_s11",),                          "s11.png"),
    ("placement", ".placement3d",   ("render_placement",),                    "placement.png"),
    ("field",     ".anim_field",    ("render_field", "render_field_animation"), "field.gif"),
    ("orbit",     ".anim_orbit",    ("render_orbit", "render_orbit_animation"), "orbit.gif"),
    ("dashboard", ".anim_dashboard", ("render_dashboard",),                   "dashboard.gif"),
    ("map",       ".heatmap",       ("render_placement_map",),                "placement_map.png"),
]
_NAMES = [r[0] for r in _RENDERERS]


def _resolve(module_name: str, preferred: tuple[str, ...]):
    """Import lazily and find the renderer entry point."""
    module = importlib.import_module(module_name, package=__package__)
    for name in preferred:
        fn = getattr(module, name, None)
        if callable(fn):
            return fn
    for name in sorted(dir(module)):          # tolerate a renamed entry point
        fn = getattr(module, name)
        if name.startswith("render") and callable(fn):
            return fn
    raise AttributeError(f"no render* function in {module.__name__}")


def _hsize(n_bytes: int) -> str:
    if n_bytes >= 1024 * 1024:
        return f"{n_bytes / (1024 * 1024):.1f} MB"
    return f"{n_bytes / 1024:.1f} KB"


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m rf.viz",
        description="Render every figure and animation for a run directory.")
    ap.add_argument("run_dir", help="run directory (e.g. runs/demo)")
    ap.add_argument("--only", default=None, metavar=",".join(_NAMES),
                    help="comma-separated subset of renderers to run")
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir)
    if not (run_dir / "result.json").exists():
        print(f"error: {run_dir / 'result.json'} not found - not a run directory.")
        print("hint: fabricate the demo run first:")
        print("    python -m rf.viz.data      # writes runs/demo (labelled DEMO)")
        return 2

    if args.only:
        selected = [t.strip() for t in args.only.split(",") if t.strip()]
        unknown = [t for t in selected if t not in _NAMES]
        if unknown:
            print(f"error: unknown renderer(s) {', '.join(unknown)}; "
                  f"valid: {', '.join(_NAMES)}")
            return 2
    else:
        selected = list(_NAMES)

    from .data import load_run
    run = load_run(run_dir)
    media = run_dir / "media"
    media.mkdir(parents=True, exist_ok=True)
    pipeline_start = time.time()

    print(f"media pipeline - {run_dir}  "
          f"(candidate {run['result'].get('candidate_id', '?')})")

    rows = []   # (name, status, [Path, ...], seconds, note)
    for name, module_name, preferred, default_out in _RENDERERS:
        if name not in selected:
            continue
        print(f"  [{name}] ...", flush=True)
        try:
            fn = _resolve(module_name, preferred)
        except ModuleNotFoundError as exc:
            rows.append((name, "skipped", [], 0.0,
                         f"module not available ({exc.name})"))
            continue
        except AttributeError as exc:
            rows.append((name, "skipped", [], 0.0, str(exc)))
            continue

        out_path = media / default_out
        t0 = time.perf_counter()
        try:
            returned = fn(run, str(out_path))
        except Exception as exc:
            rows.append((name, "FAILED", [], time.perf_counter() - t0,
                         f"{type(exc).__name__}: {exc}"))
            continue
        dt = time.perf_counter() - t0

        if returned is None:
            paths = [out_path]
        elif isinstance(returned, (list, tuple)):
            paths = [Path(p) for p in returned]
        else:
            paths = [Path(returned)]
        # animations may write an mp4 twin next to the gif
        for p in list(paths):
            twin = p.with_suffix(".mp4")
            if (p.suffix == ".gif" and twin.exists()
                    and twin.stat().st_mtime >= pipeline_start
                    and twin not in paths):
                paths.append(twin)
        paths = [p for p in paths if p.exists() and p.stat().st_size > 0]
        if paths:
            rows.append((name, "ok", paths, dt, ""))
        else:
            rows.append((name, "FAILED", [], dt, "renderer wrote no output"))

    # ------------------------------------------------------------- summary
    file_w = max([28] + [len(_rel(p, run_dir)) for _, _, ps, _, _ in rows
                         for p in ps])
    print()
    print(f"{'renderer':<11} {'status':<8} {'output':<{file_w}} {'size':>9} {'secs':>7}")
    print(f"{'-' * 11} {'-' * 8} {'-' * file_w} {'-' * 9} {'-' * 7}")
    for name, status, paths, dt, note in rows:
        if not paths:
            print(f"{name:<11} {status:<8} {note:<{file_w}} {'-':>9} {dt:>7.1f}")
            continue
        for j, p in enumerate(paths):
            lead_name = name if j == 0 else ""
            lead_status = status if j == 0 else ""
            secs = f"{dt:.1f}" if j == 0 else ""
            print(f"{lead_name:<11} {lead_status:<8} {_rel(p, run_dir):<{file_w}} "
                  f"{_hsize(p.stat().st_size):>9} {secs:>7}")

    n_ok = sum(1 for r in rows if r[1] == "ok")
    n_fail = sum(1 for r in rows if r[1] == "FAILED")
    n_skip = sum(1 for r in rows if r[1] == "skipped")
    print(f"\n{n_ok} ok, {n_fail} failed, {n_skip} skipped -> {media}")
    return 0 if n_ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
