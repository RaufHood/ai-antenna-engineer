"use client";

import { create } from "zustand";
import { anchors, phoneV1 } from "./device";
import { generateCandidates } from "./rf";
import type {
  AgentMessage,
  BandRequirement,
  Candidate,
  DeviceSpec,
  Job,
  SimResult,
} from "./types";

export type ViewMode = "system" | "focus";

interface AppState {
  spec: DeviceSpec;
  anchors: typeof anchors;

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
  startRun: () => Promise<void>;
  poll: () => Promise<void>;
  reset: () => void;
}

const DEFAULT_BANDS = ["lte_low", "gps_l1", "wifi24", "n78"];

export const useApp = create<AppState>((set, get) => ({
  spec: phoneV1,
  anchors,

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
    const ordered = phoneV1.requirements.bands
      .map((b) => b.id)
      .filter((b) => next.includes(b));
    set({
      enabledBands: ordered,
      candidates: generateCandidates(phoneV1, ordered),
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
        ? phoneV1.components.map((c) => c.name).filter((n) => n !== name)
        : [],
      selectedComponent: name,
    }),
  selectComponent: (name) => set({ selectedComponent: name }),
  hoverComponent: (name) => set({ hoveredComponent: name }),
  toggle: (key) => set({ [key]: !get()[key] } as Partial<AppState>),
  selectCandidate: (id) => set({ selectedCandidate: id }),
  setPrompt: (p) => set({ prompt: p }),

  startRun: async () => {
    const { enabledBands, prompt } = get();
    if (!enabledBands.length) {
      set({ error: "Select at least one band before running." });
      return;
    }
    set({
      running: true,
      planning: true,
      error: null,
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
      const { runId } = await res.json();
      set({ runId });
      await get().poll();
    } catch (e) {
      set({ running: false, planning: false, error: String(e) });
    }
  },

  poll: async () => {
    const runId = get().runId;
    if (!runId) return;
    const res = await fetch(`/api/run?runId=${runId}`);
    if (!res.ok) {
      set({ running: false, error: "run snapshot unavailable" });
      return;
    }
    const snap = await res.json();
    const userMsg = get().messages.find((m) => m.role === "user");
    set({
      jobs: snap.jobs,
      results: snap.results,
      placements: snap.placements,
      isolation: snap.isolation,
      candidates: snap.candidates,
      planning: snap.planning,
      running: !snap.done,
      messages: userMsg ? [userMsg, ...snap.messages] : snap.messages,
      selectedCandidate:
        get().selectedCandidate ??
        (Object.values(snap.placements)[0] as string | undefined) ??
        null,
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
    }),
}));
