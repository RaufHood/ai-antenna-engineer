"use client";

import { useMemo, useState } from "react";
import { sizeOf } from "@/lib/geometry";
import { useApp } from "@/lib/store";
import type {
  BandRequirement,
  Bbox,
  Candidate,
  DeviceComponent,
  RegionId,
  Vec3,
} from "@/lib/types";
import { Chevron, SectionTitle } from "./SpecPanel";

/**
 * The device's parts. Closed by default — the brief is the device and the
 * band, not its bill of materials — and one click opens the parts that crowd
 * the antenna, then the full list with hide/isolate. A part selected in the
 * viewer shows its card regardless, because that click was a question.
 */

const EM_LABEL: Record<string, string> = {
  pec: "PEC",
  lossy_metal: "lossy metal",
  dielectric: "dielectric",
  air: "air",
};

const isConductor = (em: string) => em === "pec" || em === "lossy_metal";

/** Shortest distance from a point to a part's bounds, in mm. 0 = inside. */
function gapTo(bbox: Bbox, p: Vec3) {
  const d = [0, 1, 2].map((i) => Math.max(bbox[0][i] - p[i], 0, p[i] - bbox[1][i]));
  return Math.hypot(d[0], d[1], d[2]);
}

function minGap(bbox: Bbox, sites: Vec3[]) {
  let best = Infinity;
  for (const s of sites) best = Math.min(best, gapTo(bbox, s));
  return best;
}

/**
 * The enclosure: a part that spans nearly the whole device in plan — frame,
 * cover glass, back glass. Adjacent to every site by definition, so ranking
 * it by proximity says nothing.
 */
function isEnclosure(c: DeviceComponent, device: Vec3) {
  const s = sizeOf(c.bbox_mm);
  return s[0] >= 0.9 * device[0] && s[1] >= 0.9 * device[1];
}

/** The regions this band would rather sit in — where the agent will look. */
function preferredRegions(b: BandRequirement): RegionId[] {
  const prefs = Object.entries(b.region_pref) as [RegionId, number][];
  const best = Math.max(...prefs.map(([, v]) => v));
  return prefs.filter(([, v]) => v >= best - 0.02).map(([k]) => k);
}

/** One part. Hover and click drive the 3D viewer, in both lists. */
function PartRow({
  c,
  trailing,
  hideControl = false,
}: {
  c: DeviceComponent;
  trailing?: React.ReactNode;
  hideControl?: boolean;
}) {
  const hidden = useApp((s) => s.hidden);
  const selected = useApp((s) => s.selectedComponent);
  const toggleHidden = useApp((s) => s.toggleHidden);
  const selectComponent = useApp((s) => s.selectComponent);
  const hoverComponent = useApp((s) => s.hoverComponent);

  const isHidden = hidden.includes(c.name);
  const isSel = selected === c.name;

  return (
    <div
      onMouseEnter={() => hoverComponent(c.name)}
      onMouseLeave={() => hoverComponent(null)}
      onClick={() => selectComponent(isSel ? null : c.name)}
      className={`group flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-[12px] transition ${
        isSel ? "bg-accent/10" : "hover:bg-ink-850"
      }`}
    >
      <span
        className="h-2.5 w-2.5 shrink-0 rounded-sm ring-1 ring-white/15"
        style={{ background: c.color, opacity: isHidden ? 0.3 : 1 }}
      />
      <span className={`min-w-0 flex-1 truncate ${isHidden ? "text-fg-muted" : "text-fg"}`}>
        {c.label}
      </span>
      {trailing}
      {hideControl && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            toggleHidden(c.name);
          }}
          className={`w-8 shrink-0 text-right text-[11px] transition ${
            isHidden
              ? "text-fg-muted hover:text-fg"
              : "text-fg-muted opacity-0 hover:text-fg focus-visible:opacity-100 group-hover:opacity-100"
          }`}
        >
          {isHidden ? "show" : "hide"}
        </button>
      )}
    </div>
  );
}

export function ComponentTree() {
  const components = useApp((s) => s.spec.components);
  const bands = useApp((s) => s.spec.requirements.bands);
  const enabled = useApp((s) => s.enabledBands);
  const device = useApp((s) => s.spec.board.size_mm);
  const anchors = useApp((s) => s.anchors);
  const candidates = useApp((s) => s.candidates);
  const placements = useApp((s) => s.placements);
  const hidden = useApp((s) => s.hidden);
  const selected = useApp((s) => s.selectedComponent);
  const toggleHidden = useApp((s) => s.toggleHidden);
  const selectComponent = useApp((s) => s.selectComponent);
  const isolateComponent = useApp((s) => s.isolateComponent);

  const [open, setOpen] = useState(false);
  const [allOpen, setAllOpen] = useState(false);

  const conductors = components.filter((c) => isConductor(c.em)).length;
  const dielectrics = components.filter((c) => c.em === "dielectric").length;

  // The binding keep-out is the widest one among the bands being solved.
  const driving = bands
    .filter((b) => enabled.includes(b.id))
    .reduce<BandRequirement | null>(
      (a, b) => (!a || b.clearance_mm > a.clearance_mm ? b : a),
      null,
    );

  // Measure against the placements the agent settled on once a run has
  // produced them; before that, against the anchors in the region the target
  // band prefers.
  const { sites, placed } = useMemo(() => {
    const chosen = Object.values(placements)
      .map((id) => candidates.find((c) => c.candidate_id === id))
      .filter((c): c is Candidate => !!c);
    if (chosen.length) {
      return { sites: chosen.map((c) => c.position_mm), placed: true };
    }
    const regions = driving ? preferredRegions(driving) : [];
    const scoped = regions.length ? anchors.filter((a) => regions.includes(a.region)) : [];
    return { sites: (scoped.length ? scoped : anchors).map((a) => a.pos_mm), placed: false };
  }, [placements, candidates, anchors, driving]);

  const ranked = useMemo(
    () =>
      components
        .filter((c) => !isEnclosure(c, device))
        .map((c) => ({ c, gap: minGap(c.bbox_mm, sites) }))
        .filter((r) => Number.isFinite(r.gap))
        .sort((a, b) => a.gap - b.gap),
    [components, device, sites],
  );

  const inKeepout = driving ? ranked.filter((r) => r.gap <= driving.clearance_mm) : [];
  const near = ranked.slice(0, 4);

  const sel = components.find((c) => c.name === selected) ?? null;
  const selHidden = !!sel && hidden.includes(sel.name);

  return (
    <section className="border-t border-ink-800 px-4 pb-6 pt-5">
      <button
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 text-left"
      >
        <SectionTitle>Components</SectionTitle>
        <span className="font-mono text-[11px] text-fg-muted">{components.length}</span>
        <span className="ml-auto flex items-center gap-3">
          {hidden.length > 0 && (
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => {
                e.stopPropagation();
                isolateComponent(null);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  e.stopPropagation();
                  isolateComponent(null);
                }
              }}
              className="text-[11px] text-accent transition hover:text-fg"
            >
              Show {hidden.length} hidden
            </span>
          )}
          <span className="text-fg-muted">
            <Chevron open={open} />
          </span>
        </span>
      </button>

      {sel && (
        <div className="mt-3 rounded-md border border-ink-800 bg-ink-900 px-3 py-2.5">
          <div className="flex items-baseline gap-2">
            <span
              className="h-2 w-2 shrink-0 translate-y-px rounded-sm ring-1 ring-white/15"
              style={{ background: sel.color }}
            />
            <span className="min-w-0 flex-1 truncate text-[12px] text-fg">{sel.label}</span>
            <span className="shrink-0 text-[11px] text-fg-muted">{EM_LABEL[sel.em]}</span>
          </div>
          <dl className="mt-1.5 space-y-0.5 font-mono text-[11px] text-fg-muted">
            <div>
              <dt className="inline">size </dt>
              <dd className="inline text-fg">
                {sizeOf(sel.bbox_mm)
                  .map((v) => v.toFixed(1))
                  .join(" × ")}{" "}
                mm
              </dd>
            </div>
            <div>
              <dt className="inline">at </dt>
              <dd className="inline text-fg">
                {sel.bbox_mm[0].map((v) => v.toFixed(1)).join(", ")} mm
              </dd>
            </div>
            {sel.em === "dielectric" && (
              <div>
                <dt className="inline">εr </dt>
                <dd className="inline text-fg">{sel.epsilon_r}</dd>
                <dt className="inline"> · tan δ </dt>
                <dd className="inline text-fg">{sel.loss_tangent}</dd>
              </div>
            )}
          </dl>
          <div className="mt-2 flex items-center gap-3 text-[11px]">
            <button
              onClick={() => isolateComponent(sel.name)}
              className="text-accent transition hover:text-fg"
            >
              Isolate
            </button>
            <button
              onClick={() => toggleHidden(sel.name)}
              className="text-fg-muted transition hover:text-fg"
            >
              {selHidden ? "Show" : "Hide"}
            </button>
            <button
              onClick={() => selectComponent(null)}
              className="ml-auto text-fg-muted transition hover:text-fg"
            >
              Clear
            </button>
          </div>
        </div>
      )}

      {open && (
        <>
          <p className="mt-3 flex items-center gap-3 text-[11px] text-fg-muted">
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-em-metal" />
              {conductors} conductors
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-em-dielectric" />
              {dielectrics} dielectrics
            </span>
          </p>

          {near.length > 0 && (
            <div className="mt-4">
              <div className="flex items-baseline justify-between gap-2">
                <p
                  className="min-w-0 truncate text-[11px] text-fg-muted"
                  title={
                    placed
                      ? "Gap to the nearest antenna the agent placed"
                      : `Gap to the nearest ${driving?.short ?? "candidate"} site`
                  }
                >
                  {placed ? "Nearest the antenna" : "Nearest the candidate sites"}
                </p>
                {driving && (
                  <span
                    className="shrink-0 font-mono text-[11px] text-fg-muted"
                    title={`Parts inside the ${driving.clearance_mm} mm keep-out`}
                  >
                    {inKeepout.length} in keep-out
                  </span>
                )}
              </div>
              <ul className="-mx-2 mt-1">
                {near.map(({ c, gap }) => (
                  <li key={c.name}>
                    <PartRow
                      c={c}
                      trailing={
                        <span className="shrink-0 font-mono text-[11px] text-fg-muted">
                          {gap.toFixed(1)} mm
                        </span>
                      }
                    />
                  </li>
                ))}
              </ul>
            </div>
          )}

          <button
            aria-expanded={allOpen}
            onClick={() => setAllOpen((o) => !o)}
            className="mt-3 flex w-full items-center gap-1.5 text-[12px] text-fg-muted transition hover:text-fg"
          >
            <Chevron open={allOpen} />
            <span>All parts</span>
          </button>

          {allOpen && (
            <ul className="-mx-2 mt-1">
              {components.map((c) => (
                <li key={c.name}>
                  <PartRow
                    c={c}
                    hideControl
                    trailing={
                      <span className="shrink-0 text-[11px] text-fg-muted">{EM_LABEL[c.em]}</span>
                    }
                  />
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
