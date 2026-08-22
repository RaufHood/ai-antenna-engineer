"use client";

import { create } from "zustand";
import { anchors, phoneV1 } from "./device";
import { errorFromBody } from "./httpError";
import { generateCandidates } from "./rf";
import { hydrateSpec } from "./specHydrate";
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
export type AgentMode = "mock" | "devin" | "local";

interface AppState {
  spec: DeviceSpec;
  anchors: Anchor[];

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
  truncated: boolean;
  runNote: string | null;

  deviceId: string | null;
  agentMode: AgentMode;
  uploadingDevice: boolean;

  /** URL of a user-supplied .glb; overrides the procedural handset. */
  modelUrl: string | null;
  modelName: string | null;
  setModel: (url: string | null, name: string | null) => void;
  setAgentMode: (m: AgentMode) => void;
  uploadDevice: (blend: File, materials?: File | null) => Promise<void>;
  clearDevice: () => void;

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
  truncated: false,
  runNote: null,

  deviceId: null,
  agentMode: "mock",
  uploadingDevice: false,

  modelUrl: null,
  modelName: null,
  setModel: (url, name) => set({ modelUrl: url, modelName: name }),
  setAgentMode: (m) => set({ agentMode: m }),

  uploadDevice: async (blend, materials) => {
    set({ uploadingDevice: true, error: null });
    try {
      const fd = new FormData();
      fd.append("blend", blend, blend.name);
      if (materials) fd.append("materials", materials, materials.name);
      fd.append("wait", "false");
      const res = await fetch("/api/devices", { method: "POST", body: fd });
      const body: unknown = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(errorFromBody(body, `upload failed (${res.status})`));
      }
      let snap = body as {
        device_id?: string;
        name?: string;
        status?: string;
        error?: string;
        spec?: DeviceSpec;
        anchors?: Anchor[];
      };
      if (!snap.device_id) throw new Error("device upload did not return device_id");
      const deviceId = snap.device_id;
      const started = Date.now();
      while (snap.status === "extracting") {
        if (Date.now() - started > 10 * 60 * 1000) {
          throw new Error("device extraction timed out");
        }
        await new Promise((r) => setTimeout(r, 2000));
        const poll = await fetch(`/api/devices/${encodeURIComponent(deviceId)}`);
        const polled: unknown = await poll.json().catch(() => ({}));
        if (!poll.ok) {
          throw new Error(errorFromBody(polled, "device poll failed"));
        }
        snap = polled as typeof snap;
      }
      if (snap.status && snap.status !== "ready") {
        throw new Error(snap.error || `device is ${snap.status}`);
      }
      if (!snap.device_id || !snap.spec) {
        throw new Error("device upload did not return a spec");
      }
      const spec = hydrateSpec(snap.spec);
      const nextAnchors = Array.isArray(snap.anchors) ? snap.anchors : [];
      const enabled = spec.requirements.bands
        .map((b) => b.id)
        .filter((id) => get().enabledBands.includes(id));
      const ordered = enabled.length
        ? enabled
        : spec.requirements.bands.map((b) => b.id).slice(0, 4);
      set({
        deviceId: snap.device_id,
        spec,
        anchors: nextAnchors,
        enabledBands: ordered,
        modelUrl: `/api/devices/${snap.device_id}/artifacts/device.glb`,
        modelName: snap.name || blend.name,
        candidates: generateCandidates(spec, ordered, nextAnchors),
        hidden: [],
        selectedComponent: null,
        uploadingDevice: false,
      });
    } catch (e) {
      set({
        uploadingDevice: false,
        error: e instanceof Error ? e.message : String(e),
      });
    }
  },

  clearDevice: () => {
    const enabled = get().enabledBands;
    set({
      deviceId: null,
      spec: phoneV1,
      anchors,
      modelUrl: null,
      modelName: null,
      candidates: generateCandidates(phoneV1, enabled, anchors),
      hidden: [],
      selectedComponent: null,
    });
  },

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
    set({ spec, candidates: generateCandidates(spec, get().enabledBands, get().anchors) });
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
    const ordered = get().spec.requirements.bands
      .map((b) => b.id)
      .filter((b) => next.includes(b));
    set({
      enabledBands: ordered,
      candidates: generateCandidates(get().spec, ordered, get().anchors),
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

  startRun: async () => {
    const { enabledBands, prompt, agentMode, deviceId } = get();
    if (!enabledBands.length) {
      set({ error: "Select at least one band before running." });
      return;
    }
    set({
      running: true,
      planning: true,
      error: null,
      truncated: false,
      runNote: null,
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
          agent: agentMode,
          device_id: deviceId ?? undefined,
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
      const body: unknown = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(errorFromBody(body, "run failed"));
      const runId = (body as { runId?: string }).runId;
      if (!runId) throw new Error("run did not return runId");
      set({ runId });
      await get().poll();
    } catch (e) {
      set({ running: false, planning: false, error: String(e instanceof Error ? e.message : e) });
    }
  },

  poll: async () => {
    const runId = get().runId;
    if (!runId) return;
    try {
      const res = await fetch(`/api/run?runId=${encodeURIComponent(runId)}`, {
        cache: "no-store",
      });
      const body: unknown = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = errorFromBody(body, "run snapshot unavailable");
        set({
          error: msg,
          running: res.status === 404 ? false : get().running,
          planning: res.status === 404 ? false : get().planning,
        });
        return;
      }
      const snap = body as {
        jobs: Job[];
        results: Record<string, SimResult>;
        placements: Record<string, string>;
        isolation: { a: string; b: string; db: number }[];
        candidates: Candidate[];
        planning: boolean;
        done: boolean;
        messages: AgentMessage[];
        truncated?: boolean;
        error?: string;
        rationale?: string;
      };
      const userMsg = get().messages.find((m) => m.role === "user");
      const incoming = Array.isArray(snap.messages) ? snap.messages : [];
      set({
        jobs: snap.jobs ?? [],
        results: snap.results ?? {},
        placements: snap.placements ?? {},
        isolation: snap.isolation ?? [],
        candidates:
          Array.isArray(snap.candidates) && snap.candidates.length
            ? snap.candidates
            : get().candidates,
        planning: Boolean(snap.planning),
        running: !snap.done,
        truncated: Boolean(snap.truncated),
        runNote: snap.rationale ?? get().runNote,
        error: snap.error ?? null,
        messages: userMsg
          ? [userMsg, ...incoming.filter((m) => m.role !== "user" || m.id !== userMsg.id)]
          : incoming,
        selectedCandidate:
          get().selectedCandidate ??
          (Object.values(snap.placements ?? {})[0] as string | undefined) ??
          null,
      });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    }
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
      truncated: false,
      runNote: null,
      error: null,
    }),
}));
