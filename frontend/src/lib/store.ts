"use client";

import { create } from "zustand";
import { anchors, phoneV1 } from "./device";
import type {
  AgentMessage,
  Anchor,
  Candidate,
  DeviceSpec,
  Job,
  SimResult,
} from "./types";

export type ViewMode = "system" | "focus";
// Single definition: backend.ts owns it because the backend is what accepts
// these values. Two copies had already drifted apart ("replay" existed in one
// and not the other), which the compiler only caught at the call site.
export type { AgentKind } from "./backend";
import type { AgentKind, MediaArtifact } from "./backend";
export type Layer = "showKeepouts" | "showPins" | "showLabels" | "showShaded";

interface AppState {
  // ---- device
  spec: DeviceSpec;
  anchors: Anchor[];
  /** Backend device id after a .blend upload; null = the built-in Handset A. */
  deviceId: string | null;
  uploading: boolean;
  /** URL of a user-supplied .glb; overrides the procedural handset. */
  modelUrl: string | null;
  modelName: string | null;

  // ---- viewer
  enabledBands: string[];
  focusBand: string | null;
  viewMode: ViewMode;
  explode: number;
  hidden: string[];
  selectedComponent: string | null;
  hoveredComponent: string | null;
  showKeepouts: boolean;
  showPins: boolean;
  showLabels: boolean;
  /** Solid shaded surfaces over the x-ray line art. Off by default: the
   *  wireframe is what lets you see the antenna inside the phone. */
  showShaded: boolean;

  // ---- run
  prompt: string;
  /** mock = the backend's offline heuristic agent; devin = the real one. */
  agent: AgentKind;
  runId: string | null;
  running: boolean;
  planning: boolean;
  engine: string | null;
  /** The real agent died and the heuristic finished the run. Never hide this. */
  agentFellBack: boolean;
  tapeOtherDevice: boolean;
  /** Render this run's own maps, x-ray and field clip once it concludes. */
  wantMedia: boolean;
  media: MediaArtifact[];
  /** Backend stage — 'media' means the evidence is still rendering. */
  stage: string;
  /** Height the user dragged the results dock to, in px. Null means the
   *  layout picks — a table and a gallery want different room. */
  dockHeight: number | null;
  /** Which dock view is open. Lives here, not in the dock, because the
   *  layout gives the gallery more height than a table needs. */
  dockTab: "results" | "report" | "evidence";
  error: string | null;
  candidates: Candidate[];
  results: Record<string, SimResult>;
  jobs: Job[];
  placements: Record<string, string>;
  selectedCandidate: string | null;
  messages: AgentMessage[];
  /** The agent's report.md, fetched once the run has finished. */
  report: string | null;

  // ---- actions
  setModel: (url: string | null, name: string | null) => void;
  uploadBlend: (blend: File, materials?: File | null) => Promise<void>;
  toggleBand: (id: string) => void;
  setFocusBand: (id: string | null) => void;
  setViewMode: (m: ViewMode) => void;
  setExplode: (v: number) => void;
  toggleHidden: (name: string) => void;
  isolateComponent: (name: string | null) => void;
  selectComponent: (name: string | null) => void;
  hoverComponent: (name: string | null) => void;
  toggle: (key: Layer) => void;
  selectCandidate: (id: string | null) => void;
  setPrompt: (p: string) => void;
  setAgent: (a: AgentKind) => void;
  setWantMedia: (v: boolean) => void;
  setDockTab: (t: "results" | "report" | "evidence") => void;
  setDockHeight: (px: number | null) => void;
  /** Adopt the device the backend will actually solve. Runs once on mount. */
  loadDefaultDevice: () => Promise<void>;
  startRun: () => Promise<void>;
  /** Mid-run note to the agent. */
  sendNote: (text: string) => Promise<void>;
  poll: () => Promise<void>;
  reset: () => void;
}

const DEFAULT_BANDS = ["lte_low", "gps_l1", "wifi24", "n78"];

const EMPTY_RUN = {
  runId: null,
  running: false,
  planning: false,
  engine: null,
  agentFellBack: false,
  tapeOtherDevice: false,
  media: [] as MediaArtifact[],
  stage: "ingest",
  error: null,
  candidates: [] as Candidate[],
  results: {} as Record<string, SimResult>,
  jobs: [] as Job[],
  placements: {} as Record<string, string>,
  selectedCandidate: null,
  messages: [] as AgentMessage[],
  report: null,
};

export const useApp = create<AppState>((set, get) => ({
  spec: phoneV1,
  anchors,
  deviceId: null,
  uploading: false,
  modelUrl: null,
  modelName: null,

  enabledBands: DEFAULT_BANDS,
  focusBand: null,
  viewMode: "system",
  explode: 0,
  hidden: [],
  selectedComponent: null,
  hoveredComponent: null,
  showKeepouts: true,
  showPins: true,
  showLabels: true,
  showShaded: false,

  prompt:
    "Where should the antennas be placed in this phone? Pick the type, target band and expected performance for each, and respect the keep-out limits.",
  agent: "mock",
  // On by default: the maps and the field clip are the evidence an RF
  // engineer would actually hand to a mechanical one, and they cost a few
  // seconds after the study has already finished and reported.
  wantMedia: true,
  dockTab: "results" as const,
  dockHeight: null as number | null,
  ...EMPTY_RUN,

  setModel: (url, name) => set({ modelUrl: url, modelName: name }),

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
      set({
        deviceId: body.deviceId,
        spec,
        anchors: body.anchors,
        enabledBands: get().enabledBands.filter((id) =>
          spec.requirements.bands.some((b) => b.id === id),
        ),
        hidden: [],
        selectedComponent: null,
        modelUrl: body.glbUrl,
        modelName: blend.name,
        ...EMPTY_RUN,
      });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    } finally {
      set({ uploading: false });
    }
  },

  toggleBand: (id) => {
    const next = get().enabledBands.includes(id)
      ? get().enabledBands.filter((b) => b !== id)
      : [...get().enabledBands, id];
    const ordered = get()
      .spec.requirements.bands.map((b) => b.id)
      .filter((b) => next.includes(b));
    const focus = get().focusBand;
    set({
      enabledBands: ordered,
      focusBand: focus && ordered.includes(focus) ? focus : null,
    });
  },

  setFocusBand: (id) => set({ focusBand: id, viewMode: id ? "focus" : "system" }),
  setViewMode: (m) =>
    set({
      viewMode: m,
      focusBand: m === "focus" ? (get().focusBand ?? get().enabledBands[0] ?? null) : null,
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
  setWantMedia: (v) => set({ wantMedia: v }),
  setDockTab: (t) => set({ dockTab: t }),
  setDockHeight: (px) => set({ dockHeight: px }),
  setAgent: (a) => set({ agent: a }),

  loadDefaultDevice: async () => {
    // Until this lands the panel shows the built-in spec, which is a different
    // phone from the one the solver reads. Adopt the real one before the first
    // run so nothing on screen describes geometry nobody is solving.
    if (get().deviceId) return;                 // an uploaded device wins
    try {
      const bands = get().enabledBands.join(",");
      const res = await fetch(`/api/device?bands=${encodeURIComponent(bands)}`, {
        cache: "no-store",
      });
      if (!res.ok) return;
      const body = await res.json();
      if (body.fallback || !body.spec) return;  // backend down; keep the built-in
      const spec: DeviceSpec = body.spec;
      set({
        spec,
        anchors: body.anchors ?? get().anchors,
        enabledBands: get().enabledBands.filter((id) =>
          spec.requirements.bands.some((b) => b.id === id),
        ),
      });
    } catch {
      /* offline: the built-in spec stays, and the panel says which it is */
    }
  },

  startRun: async () => {
    const { enabledBands, prompt, agent, deviceId, wantMedia } = get();
    if (!enabledBands.length) {
      set({ error: "Select at least one band before running." });
      return;
    }
    set({
      ...EMPTY_RUN,
      running: true,
      planning: true,
      messages: [{ id: "u0", role: "user", kind: "text", text: prompt, ts: Date.now() }],
    });
    try {
      const res = await fetch("/api/run", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ prompt, bands: enabledBands, agent, deviceId, media: wantMedia }),
      });
      if (!res.ok) throw new Error((await res.json()).error ?? "run failed");
      const { runId } = await res.json();
      set({ runId });
      await get().poll();
    } catch (e) {
      set({ running: false, planning: false, error: e instanceof Error ? e.message : String(e) });
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
    // The user's prompt is local; the backend echoes only mid-run notes.
    const userMsg = get().messages.find((m) => m.id === "u0");
    const placements: Record<string, string> = snap.placements ?? {};
    const done = !!snap.done;
    set({
      jobs: snap.jobs ?? [],
      results: snap.results ?? {},
      placements,
      candidates: snap.candidates ?? [],
      anchors: snap.anchors?.length ? snap.anchors : get().anchors,
      planning: !!snap.planning,
      running: !done,
      engine: snap.engine ?? get().engine,
      agentFellBack: !!snap.agentFellBack,
      tapeOtherDevice: !!snap.tapeOtherDevice,
      media: snap.media ?? [],
      stage: snap.stage ?? "ingest",
      messages: [...(userMsg ? [userMsg] : []), ...(snap.messages ?? [])],
      error: snap.status === "failed" ? "run failed — see the agent feed" : get().error,
      selectedCandidate:
        get().selectedCandidate ?? (Object.values(placements)[0] as string | undefined) ?? null,
    });
    if (done && !get().report && (snap.artifacts ?? []).includes("report.md")) {
      const r = await fetch(`/api/run?runId=${runId}&artifact=report.md`);
      if (r.ok) set({ report: await r.text() });
    }
  },

  reset: () => set({ ...EMPTY_RUN }),
}));
