"use client";

import { useEffect, useRef, useState } from "react";
import { useApp } from "@/lib/store";
import type { BandRequirement } from "@/lib/types";

/**
 * The brief: the device and the band. Two decisions, two controls, and the
 * numbers each one fixes. Everything that explains rather than decides —
 * solve cost, radiator size, how a .blend differs from a .glb — sits in a
 * tooltip on the control it describes, so the rail reads at a glance.
 */

/* --------------------------------------------------------------- primitives */

export function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-fg-faint">
      {children}
    </h2>
  );
}

/** One stroke weight for every glyph in this panel. */
function Icon({
  path,
  size = 13,
  className,
}: {
  path: React.ReactNode;
  size?: number;
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 16 16"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      {path}
    </svg>
  );
}

export const Chevron = ({ open }: { open: boolean }) => (
  <Icon
    size={12}
    className={`shrink-0 transition-transform duration-150 ${open ? "rotate-90" : ""}`}
    path={<path d="M6 3.5 10.5 8 6 12.5" />}
  />
);

const FileIn = () => (
  <Icon
    path={
      <>
        <path d="M8 2.5v6.5" />
        <path d="M5.5 6.5 8 9l2.5-2.5" />
        <path d="M2.75 10.5v2a1 1 0 0 0 1 1h8.5a1 1 0 0 0 1-1v-2" />
      </>
    }
  />
);

const Spinner = () => (
  <Icon
    className="animate-spin"
    path={
      <>
        <circle cx="8" cy="8" r="5.25" className="opacity-25" />
        <path d="M8 2.75A5.25 5.25 0 0 1 13.25 8" />
      </>
    }
  />
);

/* ------------------------------------------------------------------- device */

/** Strips the dimensions the catalogue repeats inside the device name. */
const bareName = (n: string) => n.replace(/\s*\([^)]*\)\s*$/, "").trim() || n;

function DeviceCard() {
  const spec = useApp((s) => s.spec);
  const deviceId = useApp((s) => s.deviceId);
  const modelUrl = useApp((s) => s.modelUrl);
  const modelName = useApp((s) => s.modelName);
  const uploading = useApp((s) => s.uploading);
  const setModel = useApp((s) => s.setModel);
  const uploadBlend = useApp((s) => s.uploadBlend);

  const fileRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);
  const [dragging, setDragging] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const [w, h, t] = spec.board.size_mm;
  const parts = spec.components.length;
  // deviceId is set only after a .blend has been extracted on the backend.
  const extracted = deviceId !== null;
  // A .glb with no .blend behind it is drawn but never solved. That is the
  // one case where what you see and what the solver reads disagree, and it
  // is the only time the card says anything about the viewer.
  const displayOnly = !!modelUrl && !extracted;

  async function load(file: File) {
    const name = file.name.toLowerCase();
    if (name.endsWith(".blend")) {
      setProblem(null);
      await uploadBlend(file);
      const err = useApp.getState().error;
      if (err) setProblem(`${file.name} was not extracted — ${err}`);
      return;
    }
    if (name.endsWith(".glb") || name.endsWith(".gltf")) {
      const prev = useApp.getState().modelUrl;
      if (prev?.startsWith("blob:")) URL.revokeObjectURL(prev);
      setModel(URL.createObjectURL(file), file.name);
      setProblem(null);
      return;
    }
    setProblem(`${file.name} is not a .blend or .glb.`);
  }

  function clearModel() {
    const prev = useApp.getState().modelUrl;
    if (prev?.startsWith("blob:")) URL.revokeObjectURL(prev);
    setModel(null, null);
    setProblem(null);
  }

  return (
    <section className="px-4 pb-5 pt-5">
      <SectionTitle>Device</SectionTitle>

      <div
        onDragEnter={(e) => {
          e.preventDefault();
          dragDepth.current += 1;
          setDragging(true);
        }}
        onDragOver={(e) => {
          e.preventDefault();
          e.dataTransfer.dropEffect = "copy";
        }}
        onDragLeave={() => {
          dragDepth.current = Math.max(0, dragDepth.current - 1);
          if (dragDepth.current === 0) setDragging(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          dragDepth.current = 0;
          setDragging(false);
          const f = e.dataTransfer.files?.[0];
          if (f) void load(f);
        }}
        aria-busy={uploading}
        className={`mt-3 rounded-lg border px-3.5 py-3 transition ${
          dragging
            ? "border-dashed border-accent bg-accent/5"
            : uploading
              ? "border-accent-dim bg-ink-900"
              : "border-ink-800 bg-ink-900"
        }`}
      >
        <p className="truncate text-[13px] font-medium text-fg">{bareName(spec.name)}</p>
        <p className="mt-1 font-mono text-[11px] text-fg-muted">
          {w} × {h} × {t} mm · {parts} parts
        </p>
        {extracted && (
          <p className="mt-1 truncate text-[11px] text-fg-muted">from {modelName}</p>
        )}

        {displayOnly && (
          <div className="mt-2.5 flex items-center gap-2 text-[11px]">
            <span className="rounded px-1.5 py-px text-warn ring-1 ring-warn/30">
              display only
            </span>
            <span className="min-w-0 truncate text-fg-muted" title={modelName ?? undefined}>
              {modelName} is drawn, not solved
            </span>
            <button
              onClick={clearModel}
              className="ml-auto shrink-0 text-fg-muted transition hover:text-fg"
            >
              Remove
            </button>
          </div>
        )}

        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          title="A .blend is extracted and solved. A .glb is drawn only. Drop a file here or choose one."
          className="mt-3 inline-flex w-full items-center justify-center gap-1.5 rounded-md border border-ink-700 py-1.5 text-[12px] text-fg transition hover:border-ink-600 hover:bg-ink-850 disabled:cursor-wait disabled:text-fg-muted"
        >
          {uploading ? <Spinner /> : <FileIn />}
          {uploading ? "Extracting…" : dragging ? "Drop to load" : "Load build file"}
        </button>
      </div>

      {problem && (
        <p role="alert" className="mt-2 text-[11px] leading-relaxed text-fail">
          {problem}
        </p>
      )}

      <input
        ref={fileRef}
        type="file"
        accept=".blend,.glb,.gltf"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = "";
          if (f) void load(f);
        }}
      />
    </section>
  );
}

/* -------------------------------------------------------------- target band */

/**
 * Solve cost for one candidate, one band. The solver meshes at lambda/10 at
 * the top of the band, so cost rises as f^3.72 — fitted to two measured
 * points on the PyNEC path: 83 ms at 2.4835 GHz, 2007 ms at 5.85 GHz.
 */
const REF_GHZ = 2.4835;
const REF_MS = 83;
const COST_EXP = 3.72;

function solveMs(b: BandRequirement) {
  return REF_MS * Math.pow(b.f_high_ghz / REF_GHZ, COST_EXP);
}

function fmtMs(ms: number) {
  if (ms < 10) return `${ms.toFixed(1)} ms`;
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

const ghz = (v: number) => v.toFixed(3);

/** The printed strip rf/placement.py collides against: 1.8 mm wide, 0.9 mm
 *  proud of the surface. Only its length changes with the band. */
const ARM_W_MM = 1.8;
const ARM_H_MM = 0.9;
const C_MM_GHZ = 299.792458;

/** Quarter wave at the band centre — the arm the solver starts from. */
function armMm(b: { f_low_ghz: number; f_high_ghz: number }): number {
  return C_MM_GHZ / ((b.f_low_ghz + b.f_high_ghz) / 2) / 4;
}

function Req({ label, value }: { label: string; value: string }) {
  return (
    <span className="whitespace-nowrap">
      <span className="text-[11px] text-fg-muted">{label} </span>
      <span className="font-mono text-[11px] text-fg">{value}</span>
    </span>
  );
}

function TargetBand() {
  const bands = useApp((s) => s.spec.requirements.bands);
  const enabled = useApp((s) => s.enabledBands);
  const toggleBand = useApp((s) => s.toggleBand);
  const focusBand = useApp((s) => s.focusBand);
  const setFocusBand = useApp((s) => s.setFocusBand);
  const running = useApp((s) => s.running);

  const [primaryId, setPrimaryId] = useState<string | null>(null);
  const [extrasOpen, setExtrasOpen] = useState(false);
  const didInit = useRef(false);

  // The brief opens on one band. Multi-band is legitimate but costly, so it
  // has to be asked for: narrow the store's default selection once.
  useEffect(() => {
    if (didInit.current) return;
    didInit.current = true;
    const s = useApp.getState();
    const ids = s.spec.requirements.bands.map((b) => b.id);
    const want = ids.includes("wifi24") ? "wifi24" : (s.enabledBands[0] ?? ids[0]);
    if (!want) return;
    const start = s.enabledBands;
    if (!start.includes(want)) s.toggleBand(want);
    for (const id of start) if (id !== want) s.toggleBand(id);
    setPrimaryId(want);
  }, []);

  const primary =
    bands.find((b) => b.id === primaryId && enabled.includes(b.id)) ??
    bands.find((b) => enabled.includes(b.id)) ??
    null;
  const extras = bands.filter((b) => enabled.includes(b.id) && b.id !== primary?.id);
  const others = bands.filter((b) => b.id !== primary?.id);
  const totalMs = bands
    .filter((b) => enabled.includes(b.id))
    .reduce((sum, b) => sum + solveMs(b), 0);
  const focused = !!primary && focusBand === primary.id;

  /** One band holds the primary slot; choosing a new one swaps it out. */
  function choose(id: string) {
    if (running) return;
    const s = useApp.getState();
    if (!s.enabledBands.includes(id)) s.toggleBand(id);
    const prev = primary?.id;
    if (prev && prev !== id && useApp.getState().enabledBands.includes(prev)) s.toggleBand(prev);
    setPrimaryId(id);
  }

  return (
    <section className="border-t border-ink-800 px-4 pb-5 pt-5">
      <SectionTitle>Target band</SectionTitle>

      <div role="radiogroup" aria-label="Primary target band" className="mt-3 flex flex-wrap gap-1.5">
        {bands.map((b) => {
          const isPrimary = b.id === primary?.id;
          const on = enabled.includes(b.id);
          return (
            <button
              key={b.id}
              role="radio"
              aria-checked={isPrimary}
              disabled={running}
              onClick={() => choose(b.id)}
              title={`${b.name} · ${ghz(b.f_low_ghz)}–${ghz(b.f_high_ghz)} GHz · ${fmtMs(solveMs(b))} per solve`}
              className={`flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-[12px] transition disabled:cursor-not-allowed disabled:opacity-60 ${
                isPrimary
                  ? "border-accent/50 bg-accent/10 text-fg"
                  : "border-ink-800 text-fg-muted hover:border-ink-600 hover:text-fg"
              }`}
            >
              <span
                className="h-1.5 w-1.5 shrink-0 rounded-full"
                style={{ background: on ? b.color : "var(--ink-600)" }}
              />
              {b.short}
            </button>
          );
        })}
      </div>

      {primary ? (
        <div
          className="mt-4"
          title={`Radiator ${armMm(primary).toFixed(0)} × ${ARM_W_MM} × ${ARM_H_MM} mm · ${(
            primary.antenna_types ?? ["IFA"]
          ).join(" / ")} · ${fmtMs(solveMs(primary))} per solve`}
        >
          <div className="flex items-baseline gap-2">
            <h3 className="min-w-0 flex-1 truncate text-[13px] font-medium text-fg">
              {primary.name}
            </h3>
            <span className="shrink-0 font-mono text-[11px] text-fg-muted">
              {ghz(primary.f_low_ghz)}–{ghz(primary.f_high_ghz)} GHz
            </span>
          </div>
          <div className="mt-1.5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <Req label="S11" value={`≤ ${primary.s11_db_max} dB`} />
            <Req label="Eff." value={`≥ ${Math.round(primary.efficiency_min * 100)}%`} />
            <Req label="Clear" value={`≥ ${primary.clearance_mm} mm`} />
          </div>
          {enabled.length > 1 && (
            <button
              aria-pressed={focused}
              onClick={() => setFocusBand(focused ? null : primary.id)}
              title="Show only this band's candidates in the viewer"
              className={`mt-2 text-[11px] transition ${
                focused ? "text-accent" : "text-fg-muted hover:text-fg"
              }`}
            >
              {focused ? "Showing this band only" : "Focus in viewer"}
            </button>
          )}
        </div>
      ) : (
        <p className="mt-4 text-[12px] text-fg-muted">Pick a band to solve for.</p>
      )}

      <div className="mt-4">
        <button
          aria-expanded={extrasOpen}
          onClick={() => setExtrasOpen((o) => !o)}
          className="flex w-full items-center gap-1.5 text-[12px] text-fg-muted transition hover:text-fg"
        >
          <Chevron open={extrasOpen} />
          <span>Also solve another band</span>
          {extras.length > 0 && (
            <span className="ml-auto font-mono text-[11px] text-fg">+{extras.length}</span>
          )}
        </button>

        {extrasOpen && (
          <ul className="mt-1.5 -mx-2">
            {others.map((b) => {
              const on = enabled.includes(b.id);
              return (
                <li key={b.id}>
                  <label
                    title={`${fmtMs(solveMs(b))} per solve`}
                    className={`flex items-center gap-2.5 rounded-md px-2 py-1.5 transition ${
                      running ? "cursor-not-allowed opacity-60" : "cursor-pointer hover:bg-ink-850"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={on}
                      disabled={running}
                      onChange={() => toggleBand(b.id)}
                      className="accent-accent"
                    />
                    <span
                      className="h-1.5 w-1.5 shrink-0 rounded-full"
                      style={{ background: on ? b.color : "var(--ink-600)" }}
                    />
                    <span className="min-w-0 flex-1 truncate text-[12px] text-fg">{b.name}</span>
                  </label>
                </li>
              );
            })}
          </ul>
        )}

        {extras.length > 0 && (
          <p className="mt-1.5 pl-[18px] text-[11px] text-fg-muted">
            {enabled.length} bands · {fmtMs(totalMs)} per candidate
          </p>
        )}
      </div>
    </section>
  );
}

export function SpecPanel() {
  return (
    <>
      <DeviceCard />
      <TargetBand />
    </>
  );
}
