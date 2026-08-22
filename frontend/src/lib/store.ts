"use client";

import { create } from "zustand";
import { anchors, phoneV1 } from "./device";
import { generateCandidates } from "./rf";
import type {
  AgentMessage,
  Anchor,
  BandRequirement,
  Candidate,
  DeviceSpec,
  Job,
  SimResult,
} from "./types";

export type ViewMode = "system" | "focus";
export type AgentKind = "mock" | "devin";
/** Which engine produced the run on screen. `null` until a run starts. */
export type RunSource = "backend" | "heuristic" | null;

interface AppState {
  spec: DeviceSpec;
  anchors: Anchor[];
  /** Backend device id after a .blend upload; null = the built-in Handset A. */
  deviceId: string | null;
  uploading: boolean;

  enabledBands: string[];
  focusBand: string | null;
  viewMode: ViewMode;

  explode: number;
  hidden: string[];
  selectedComponent: string | null;
  hoveredComponent: string | null;

  showKeepouts: boolean;
  showHeatmap: boolean;
  showPins: boolean;
  showIsolation: boolean;
  showLabels: boolean;
  showGrid: boolean;

  candidates: Candidate[];
  results: Record<string, SimResult>;
  jobs: Job[];
  placements: Record<string, string>;
  isolation: { a: string; b: string; db: number }[];
  selectedCandidate: string | null;

  prompt: string;
  messages: AgentMessage[];
  runId: string | null;
  running: boolean;
  planning: boolean;
  error: string | null;
  /** mock = offline heuristic agent on the backend; devin = the real one. */
  agent: AgentKind;
  source: RunSource;
  engine: string | null;
  warning: string | null;

  /** URL of a user-supplied .glb; overrides the procedural handset. */
  modelUrl: string | null;
  modelName: string | null;
  setModel: (url: string | null, name: string | null) => void;

  updateBand: (id: string, patch: Partial<BandRequirement>) => void;
  updateSar: (standard: string) => void;
  updateBoard: (patch: Partial<DeviceSpec["board"]>) => void;

  toggleBand: (id: string) => void;
  setFocusBand: (id: string | null) => void;
  setViewMode: (m: ViewMode) => void;
  setExplode: (v: number) => void;
  toggleHidden: (name: string) => void;
  isolateComponent: (name: string | null) => void;
  selectComponent: (name: string | null) => void;
  hoverComponent: (name: string | null) => void;
  toggle: (
    key:
      | "showKeepouts"
      | "showHeatmap"
      | "showPins"
      | "showIsolation"
      | "showLabels"
      | "showGrid",
  ) => void;
  selectCandidate: (id: string | null) => void;
  setPrompt: (p: string) => void;
  setAgent: (a: AgentKind) => void;
  /** Upload a .blend to the backend; the viewer switches to its device.glb. */
  uploadBlend: (blend: File, materials?: File | null) => Promise<void>;
  startRun: () => Promise<void>;
  /** Mid-run note to the agent (backend runs only). */
  sendNote: (text: string) => Promise<void>;
  poll: () => Promise<void>;
  reset: () => void;
}

const DEFAULT_BANDS = ["lte_low", "gps_l1", "wifi24", "n78"];

export const useApp = create<AppState>((set, get) => ({
  spec: phoneV1,
  anchors,
  deviceId: null,
  uploading: false,

  enabledBands: DEFAULT_BANDS,
  focusBand: null,
  viewMode: "system",

  explode: 0,
  hidden: [],
  selectedComponent: null,
  hoveredComponent: null,

  showKeepouts: true,
  showHeatmap: false,
  showPins: true,
  showIsolation: true,
  showLabels: true,
  showGrid: true,

  candidates: generateCandidates(phoneV1, DEFAULT_BANDS),
  results: {},
  jobs: [],
  placements: {},
  isolation: [],
  selectedCandidate: null,

  prompt:
    "Where should the antennas be placed in this phone? Pick the type, target band and expected performance for each, and respect the keep-out and SAR limits.",
  messages: [],
  runId: null,
  running: false,
  planning: false,
  error: null,
  agent: "mock",
  source: null,
  engine: null,
  warning: null,

  modelUrl: null,
  modelName: null,
  setModel: (url, name) => set({ modelUrl: url, modelName: name }),

  updateBand: (id, patch) => {
    const spec: DeviceSpec = {
      ...get().spec,
      requirements: {
        ...get().spec.requirements,
        bands: get().spec.requirements.bands.map((b) =>
          b.id === id ? { ...b, ...patch } : b,
        ),
      },
    };
    set({ spec, candidates: generateCandidates(spec, get().enabledBands) });
  },

  updateSar: (standard) => {
    const preset =
      standard === "ICNIRP"
        ? { standard: "ICNIRP", w_per_kg: 2.0, mass_g: 10 }
        : { standard: "FCC", w_per_kg: 1.6, mass_g: 1 };
    set({
      spec: {
        ...get().spec,
        requirements: { ...get().spec.requirements, sar_limit: preset },
      },
    });
  },

  updateBoard: (patch) =>
    set({ spec: { ...get().spec, board: { ...get().spec.board, ...patch } } }),

  toggleBand: (id) => {
    const next = get().enabledBands.includes(id)
      ? get().enabledBands.filter((b) => b !== id)
      : [...get().enabledBands, id];
    const spec = get().spec;
    const ordered = spec.requirements.bands
      .map((b) => b.id)
      .filter((b) => next.includes(b));
    set({
      enabledBands: ordered,
      // preview pins before a run; a backend run replaces them with its own
      candidates: get().deviceId ? [] : generateCandidates(spec, ordered),
      focusBand: get().focusBand && ordered.includes(get().focusBand!) ? get().focusBand : null,
    });
  },

  setFocusBand: (id) =>
    set({ focusBand: id, viewMode: id ? "focus" : "system" }),
  setViewMode: (m) =>
    set({
      viewMode: m,
      focusBand:
        m === "focus" ? (get().focusBand ?? get().enabledBands[0] ?? null) : null,
    }),
  setExplode: (v) => set({ explode: v }),
  toggleHidden: (name) =>
    set({
      hidden: get().hidden.includes(name)
        ? get().hidden.filter((n) => n !== name)
        : [...get().hidden, name],
    }),
  isolateComponent: (name) =>
    set({
      hidden: name
        ? get().spec.components.map((c) => c.name).filter((n) => n !== name)
        : [],
      selectedComponent: name,
    }),
  selectComponent: (name) => set({ selectedComponent: name }),
  hoverComponent: (name) => set({ hoveredComponent: name }),
  toggle: (key) => set({ [key]: !get()[key] } as Partial<AppState>),
  selectCandidate: (id) => set({ selectedCandidate: id }),
  setPrompt: (p) => set({ prompt: p }),
  setAgent: (a) => set({ agent: a }),

  uploadBlend: async (blend, materials) => {
    const form = new FormData();
    form.append("blend", blend, blend.name);
    if (materials) form.append("materials", materials, materials.name);
    set({ uploading: true, error: null });
    try {
      const res = await fetch("/api/device", { method: "POST", body: form });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? `upload failed (${res.status})`);
      const spec: DeviceSpec = body.spec;
      const enabled = get().enabledBands.filter((id) =>
        spec.requirements.bands.some((b) => b.id === id),
      );
      set({
        deviceId: body.deviceId,
        spec,
        anchors: body.anchors,
        enabledBands: enabled,
        candidates: [],
        hidden: [],
        selectedComponent: null,
        modelUrl: body.glbUrl,
        modelName: blend.name,
      });
      get().reset();
    } catch (e) {
      set({ error: String(e instanceof Error ? e.message : e) });
    } finally {
      set({ uploading: false });
    }
  },

  startRun: async () => {
    const { enabledBands, prompt, agent, deviceId } = get();
    if (!enabledBands.length) {
      set({ error: "Select at least one band before running." });
      return;
    }
    set({
      running: true,
      planning: true,
      error: null,
      warning: null,
      source: null,
      engine: null,
      results: {},
      jobs: [],
      placements: {},
      isolation: [],
      messages: [
        {
          id: "u0",
          role: "user",
          kind: "text",
          text: prompt,
          ts: Date.now(),
        },
      ],
    });
    try {
      const res = await fetch("/api/run", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          prompt,
          bands: enabledBands,
          agent,
          deviceId,
          overrides: {
            sar_limit: get().spec.requirements.sar_limit,
            bands: Object.fromEntries(
              get().spec.requirements.bands.map((b) => [
                b.id,
                {
                  clearance_mm: b.clearance_mm,
                  s11_db_max: b.s11_db_max,
                  efficiency_min: b.efficiency_min,
                },
              ]),
            ),
          },
        }),
      });
      if (!res.ok) throw new Error((await res.json()).error ?? "run failed");
      const { runId, source, warning } = await res.json();
      set({
        runId,
        source: source ?? null,
        warning: warning ?? null,
        messages: warning
          ? [
              ...get().messages,
              { id: "w0", role: "agent", kind: "step", text: `Warning: ${warning}`, ts: Date.now() },
            ]
          : get().messages,
      });
      await get().poll();
    } catch (e) {
      set({ running: false, planning: false, error: String(e) });
    }
  },

  sendNote: async (text) => {
    const runId = get().runId;
    if (!runId || !text.trim()) return;
    const res = await fetch("/api/run", {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ runId, text }),
    });
    if (!res.ok) {
      set({ error: (await res.json()).error ?? "note not delivered" });
      return;
    }
    set({ error: null });
    await get().poll();
  },

  poll: async () => {
    const runId = get().runId;
    if (!runId) return;
    const res = await fetch(`/api/run?runId=${runId}`);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      set({ running: false, error: body.error ?? "run snapshot unavailable" });
      return;
    }
    const snap = await res.json();
    // The user's prompt is local; backend runs echo only mid-run notes.
    const userMsg = get().messages.find((m) => m.id === "u0");
    const warn = get().messages.find((m) => m.id === "w0");
    const head = [userMsg, warn].filter(Boolean) as AgentMessage[];
    const placements: Record<string, string> = snap.placements ?? {};
    set({
      jobs: snap.jobs ?? [],
      results: snap.results ?? {},
      placements,
      isolation: snap.isolation ?? [],
      candidates: snap.candidates ?? [],
      planning: !!snap.planning,
      running: !snap.done,
      source: snap.source ?? get().source,
      engine: snap.engine ?? get().engine,
      messages: [...head, ...(snap.messages ?? [])],
      error: snap.status === "failed" ? "run failed — see the agent feed" : get().error,
      selectedCandidate:
        get().selectedCandidate ?? (Object.values(placements)[0] as string | undefined) ?? null,
    });
  },

  reset: () =>
    set({
      runId: null,
      running: false,
      planning: false,
      jobs: [],
      results: {},
      placements: {},
      isolation: [],
      messages: [],
      selectedCandidate: null,
      source: null,
      engine: null,
      warning: null,
      error: null,
      candidates: get().deviceId ? [] : generateCandidates(get().spec, get().enabledBands),
    }),
}));
