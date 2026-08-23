"use client";

import { useEffect, useRef, useState } from "react";
import { useApp } from "@/lib/store";
import type { BandRequirement } from "@/lib/types";

/**
 * The brief: what the engineer is asking for, and nothing else.
 *
 *   Device      — which geometry the solver actually meshes, and how to
 *                 replace it.
 *   Target band — one band, chosen with its solve cost in view. Extra bands
 *                 are a deliberate addition, never the default.
 *
 * Everything that is reference rather than request (per-band metric grids,
 * the part list) lives elsewhere or behind a disclosure.
 */

/* --------------------------------------------------------------- primitives */

export function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-fg-muted">
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

function Tag({ tone, children }: { tone: "pass" | "warn"; children: React.ReactNode }) {
  return (
    <span
      className={`shrink-0 rounded px-1.5 py-px text-[10px] ring-1 ${
        tone === "pass" ? "text-pass ring-pass/30" : "text-warn ring-warn/30"
      }`}
    >
      {children}
    </span>
  );
}

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
  // Until then the solver meshes the built-in catalogue spec, whatever the
  // viewer happens to be drawing.
  const extracted = deviceId !== null;

  async function load(file: File) {
    const name = file.name.toLowerCase();
    if (name.endsWith(".blend")) {
      // Goes to the backend: parts and materials are extracted there and
      // become the geometry the solver meshes.
      setProblem(null);
      await uploadBlend(file);
      const err = useApp.getState().error;
      if (err) {
        setProblem(
          `${file.name} was not extracted — ${err}. Check the backend is running, then load the file again.`,
        );
      }
      return;
    }
    if (name.endsWith(".glb") || name.endsWith(".gltf")) {
      // Display only: a .glb never reaches the solver.
      const prev = useApp.getState().modelUrl;
      if (prev?.startsWith("blob:")) URL.revokeObjectURL(prev);
      setModel(URL.createObjectURL(file), file.name);
      setProblem(null);
      return;
    }
    setProblem(
      `Kevin reads .blend and .glb. ${file.name} is neither — export the build from Blender and load that.`,
    );
  }

  function clearModel() {
    const prev = useApp.getState().modelUrl;
    if (prev?.startsWith("blob:")) URL.revokeObjectURL(prev);
    setModel(null, null);
    setProblem(null);
  }

  return (
    <section className="border-b border-ink-800 px-4 pb-5 pt-4">
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
        className={`mt-2.5 rounded-lg border bg-ink-900 transition ${
          dragging
            ? "border-dashed border-accent bg-accent/5"
            : uploading
              ? "border-accent-dim"
              : "border-ink-700"
        }`}
      >
        {/* What the solver meshes. */}
        <div className="px-3 py-2.5">
          <p className="text-[11px] text-fg-muted">Solver geometry</p>
          <p className="mt-0.5 truncate text-[13px] font-medium text-fg">{bareName(spec.name)}</p>
          <p className="mt-0.5 font-mono text-[11px] text-fg-muted">
            {w} × {h} × {t} mm · {parts} parts
          </p>
          <p className="mt-0.5 text-[11px] text-fg-muted">
            {uploading
              ? "Reading parts and materials from your build file — this spec is still what the solver would use."
              : extracted
                ? `Extracted from ${modelName ?? "your build file"}.`
                : "Built-in catalogue spec."}
          </p>
        </div>

        {/* What the viewer draws — said plainly, because they are not always
            the same thing. */}
        <div className="border-t border-ink-800 px-3 py-2.5">
          <p className="text-[11px] text-fg-muted">Viewer</p>
          <div className="mt-0.5 flex items-baseline gap-2">
            <p className="min-w-0 flex-1 truncate text-[12px] text-fg">
              {modelUrl ? (modelName ?? "Loaded mesh") : "iPhone 15 Pro mesh"}
            </p>
            {modelUrl && extracted ? (
              <Tag tone="pass">solver geometry</Tag>
            ) : (
              <Tag tone="warn">display only</Tag>
            )}
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-fg-muted">
            {modelUrl && extracted
              ? "The same geometry the solver meshes."
              : extracted
                ? "The solver meshes your extracted geometry above, not this mesh."
                : modelUrl
                  ? `Not meshed. The solver still reads the ${bareName(
                      spec.name,
                    )} spec above — load the .blend to make this geometry solvable.`
                  : `191 drawn parts, none of them meshed. The solver reads the ${parts}-part ${bareName(
                      spec.name,
                    )} spec above.`}
          </p>
        </div>

        <div className="flex items-center gap-2 border-t border-ink-800 px-3 py-2">
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="inline-flex items-center gap-1.5 rounded-md border border-ink-600 px-2.5 py-1.5 text-[11px] font-medium text-fg transition hover:border-accent hover:text-accent disabled:cursor-wait disabled:border-ink-700 disabled:text-fg-muted disabled:hover:border-ink-700 disabled:hover:text-fg-muted"
          >
            {uploading ? <Spinner /> : <FileIn />}
            {uploading ? "Extracting…" : dragging ? "Drop to load" : "Load build file"}
          </button>
          {modelUrl && !extracted && !uploading && (
            <button
              onClick={clearModel}
              className="ml-auto shrink-0 text-[11px] text-fg-muted transition hover:text-fg"
            >
              Remove mesh
            </button>
          )}
        </div>
      </div>

      <p className="mt-2 text-[11px] leading-relaxed text-fg-muted">
        A <span className="font-mono">.blend</span> is extracted on the backend and becomes solver
        geometry. A <span className="font-mono">.glb</span> is display only. Drop one on the card
        above or use the button.
      </p>

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
 * Solve cost for one candidate, one band.
 *
 * The solver meshes at lambda/10 taken at the top of the band, so the segment
 * count rises with frequency and the method-of-moments matrix cost rises
 * faster still. Two measured points on the backend's PyNEC path — 83 ms at
 * 2.4835 GHz (Wi-Fi 2.4) and 2007 ms at 5.85 GHz (Wi-Fi 5) — fix the exponent
 * at f^3.72. Every other band here is scaled from those two, not measured.
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

function Req({ label, value }: { label: string; value: string }) {
  return (
    <span className="whitespace-nowrap">
      <span className="text-[10px] text-fg-muted">{label} </span>
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
  // has to be asked for: this narrows the store's default selection to the
  // cheapest useful target once, using the store's own action.
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
    <section className="border-b border-ink-800 px-4 pb-5 pt-5">
      <div className="flex items-baseline justify-between">
        <SectionTitle>Target band</SectionTitle>
        <span className="text-[10px] text-fg-muted">per solve</span>
      </div>

      <div role="radiogroup" aria-label="Primary target band" className="mt-2.5 grid grid-cols-2 gap-1">
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
              title={`${b.name} · ${b.service} · ${ghz(b.f_low_ghz)}–${ghz(b.f_high_ghz)} GHz`}
              className={`flex items-center gap-1.5 rounded-md border px-2 py-1.5 text-left transition disabled:cursor-not-allowed disabled:opacity-60 ${
                isPrimary
                  ? "border-accent/60 bg-accent/10"
                  : "border-ink-700 hover:border-ink-600 hover:bg-ink-850"
              }`}
            >
              <span
                className="h-1.5 w-1.5 shrink-0 rounded-full"
                style={{ background: on ? b.color : "var(--ink-600)" }}
              />
              <span className={`truncate text-[11px] ${isPrimary ? "text-fg" : "text-fg-muted"}`}>
                {b.short}
              </span>
              <span className="ml-auto shrink-0 font-mono text-[10px] text-fg-muted">
                {fmtMs(solveMs(b))}
              </span>
            </button>
          );
        })}
      </div>

      <p className="mt-2 text-[11px] leading-relaxed text-fg-muted">
        Mesh pitch is λ/10 at the top of the band, so a solve costs about{" "}
        <span className="font-mono">f^3.7</span> — 83 ms measured at 2.4835 GHz, 2.0 s at 5.85 GHz.
      </p>

      {primary ? (
        <div className="mt-3 border-t border-ink-800 pt-3">
          <div className="flex items-baseline gap-2">
            <h3 className="min-w-0 flex-1 truncate text-[13px] font-medium text-fg">
              {primary.name}
            </h3>
            <span className="shrink-0 font-mono text-[10px] text-fg-muted">
              {ghz(primary.f_low_ghz)}–{ghz(primary.f_high_ghz)} GHz
            </span>
          </div>
          <div className="mt-1.5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <Req label="S11" value={`≤ ${primary.s11_db_max} dB`} />
            <Req label="Efficiency" value={`≥ ${Math.round(primary.efficiency_min * 100)}%`} />
            <Req label="Clearance" value={`≥ ${primary.clearance_mm} mm`} />
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
        <p className="mt-3 border-t border-ink-800 pt-3 text-[11px] leading-relaxed text-fg-muted">
          No band selected. Pick one above — Kevin needs a target before it can propose a placement.
        </p>
      )}

      <div className="mt-3 border-t border-ink-800 pt-3">
        <button
          aria-expanded={extrasOpen}
          onClick={() => setExtrasOpen((o) => !o)}
          className="flex w-full items-center gap-1.5 text-[11px] text-fg-muted transition hover:text-fg"
        >
          <Chevron open={extrasOpen} />
          <span>Also solve another band</span>
          <span className="ml-auto font-mono text-[10px]">
            {extras.length ? `+${extras.length}` : "none"}
          </span>
        </button>

        {extras.length > 0 && (
          <p className="mt-1.5 pl-[18px] text-[11px] leading-relaxed text-fg-muted">
            {extras.map((b) => b.name).join(", ")} · every candidate costs{" "}
            <span className="font-mono text-fg">{fmtMs(totalMs)}</span> across{" "}
            {enabled.length} bands.
          </p>
        )}

        {extrasOpen && (
          <>
            <ul className="mt-2 -mx-2">
              {others.map((b) => {
                const on = enabled.includes(b.id);
                return (
                  <li key={b.id}>
                    <label
                      className={`flex items-center gap-2 rounded-md px-2 py-1.5 transition ${
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
                      <span className="min-w-0 flex-1 truncate text-[11px] text-fg">{b.name}</span>
                      <span className="shrink-0 font-mono text-[10px] text-fg-muted">
                        {fmtMs(solveMs(b))}
                      </span>
                    </label>
                  </li>
                );
              })}
            </ul>
            <p className="mt-1.5 text-[11px] leading-relaxed text-fg-muted">
              Each added band is a full extra solve on every candidate the agent tries.
            </p>
          </>
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
