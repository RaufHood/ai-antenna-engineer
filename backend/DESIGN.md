# AI Antenna Engineer — Backend & Agent Design

> **Living document.** This is the working technical spec for the backend + agent
> workstream. Update it as decisions change; append to the Decision Log (§13)
> rather than rewriting history. Contracts here are binding for code; prose is
> guidance.

Devin is an AI software engineer. We are building an **AI antenna engineer**:
give it a phone build file (`.blend`) and a technical spec, and it decides
**what antenna type, what shape/dimensions, and where** — validated by
electromagnetic simulation, iterating until *it* judges the design good enough.

Reference test case:

> "Integrate a 2.4 GHz antenna into this iPhone given this build file.
> Find the best position; decide which shape and type is best."

---

## 1. System overview

```
┌────────────┐   REST + WS    ┌──────────────────────┐   HTTPS (v3 REST)   ┌─────────────┐
│  Frontend   │◄──────────────►│   Backend (FastAPI)  │◄───────────────────►│  Devin API  │
│  (Next.js)  │  events/steps  │                      │  sessions/messages  │             │
└────────────┘                │  ┌────────────────┐  │  attachments        │  Devin VM   │
                              │  │ Orchestrator    │  │                     │  - clones   │
      .blend + prompt ───────►│  │ (state machine) │  │                     │    our repo │
                              │  └───────┬────────┘  │                     │  - runs our │
                              │          ▼           │                     │    skills   │
                              │  ┌────────────────┐  │                     │    (bpy     │
                              │  │ Sim pool        │  │                     │    extract, │
                              │  │ (PyNEC, procs)  │  │                     │    builder  │
                              │  └────────────────┘  │                     │    author)  │
                              └──────────────────────┘                     └─────────────┘
```

Division of labour (**ADR-1**): **Devin owns judgment, the backend owns
execution.** Devin does the engineering reasoning — geometry understanding,
proposing placements/types/dimensions, interpreting simulation evidence,
deciding convergence. The backend does everything that must be fast and
deterministic — running sims, scoring, diffing against requirements, event
fan-out. The escape hatch that makes this a *software*-engineer story: the
agent may **write new solver code** (NEC geometry builders) when the built-in
library can't express the shape it wants (§7.4).

### Target repo layout

```
backend/
  DESIGN.md              this file
  pyproject.toml
  app/
    main.py              FastAPI app, CORS, lifespan
    api/                 routes: runs, ws, artifacts, health
    runs/
      orchestrator.py    state machine (§5) incl. EXTRACT stage + spec cross-check
      devices.py         device lifecycle: ingest → extract → classify → anchors
      events.py          append-only event log, seq numbers, WS fan-out
      store.py           in-memory run + device registries
    agent/
      port.py            AgentPort protocol (§4.1) + RunContext
      devin.py           Devin v3 client + session driver
      mock.py            heuristic stand-in, same interface
      protocol.py        wire-message parse/render (§6.3)
      prompts.py         playbook text, schemas
    geometry/
      spec.py            canned phone_v1, anchors + clearance derived from any spec
      classify.py        geometry.json → DeviceSpec (EmClass, roles, ground, ambiguities)
      bands.py           band catalogue (mirror of frontend device.ts)
      extract.py         backend runner for tools/extract_blend.py (bpy interpreter, cache)
    sim/
      oracle.py          PyNEC wrapper: chassis wire-grid + antenna on top
      builders/          monopole.py ifa.py meander.py loop.py + agent-authored
      calibrate.py       acceptance gate for builders (§7.4)
      score.py           requirement diffs, scalar score, hint generation
      pool.py            ProcessPoolExecutor (PyNEC = C ext → processes)
  scripts/
    dev_run.py           no-HTTP end-to-end driver
tools/
  extract_blend.py       SHARED bpy extraction script (§8) — run by Devin AND backend
  make_phone_blend.py    synthetic handset fixture generator (asset convention)
data/phone_synth_v1/     fixture .blend + materials.json
.agents/skills/
  blend-extract/SKILL.md
  nec-builder/SKILL.md   (M3)
```

---

## 2. Architecture decisions (ADR summary)

| # | Decision | Why | Rejected alternative |
|---|----------|-----|----------------------|
| 1 | Agent = judgment, backend = execution | Devin turn ≈ 1–3 min; a PyNEC solve ≈ ms. Loop must be few agent turns × many sims per turn | Devin runs sims in its VM (opaque, slow, non-deterministic at demo time) |
| 2 | Geometry extraction **agent-side via Skill**, backend fallback | It's genuine agent work ("read the build file"); skill + shared script keeps one code path | Backend-only extraction (less agent story); agent-only (no demo insurance) |
| 3 | PyNEC (MoM) as in-loop oracle | Calibrated in `rf/validate_dipole.py`; ms per solve at ~160 segments. openEMS = minutes–hours | openEMS in the loop (kills iteration); openEMS optional as final confirmation |
| 4 | Progress = poll Devin messages, re-broadcast on our WS | Devin has **no webhooks**; docs recommend 10–30 s polling | Waiting on structured_output (updates on Devin's schedule, can't force) |
| 5 | **Agent decides convergence**; orchestrator enforces only the simulation gate | Judging "good enough" from rich results IS the engineering task | Orchestrator-owned `max_iterations` (moves judgment into our code) |
| 6 | Wire protocol = fenced JSON in messages; `structured_output` only as final report | Messages are immediate and per-turn; structured_output is a notepad we can't force | structured_output as the iteration handshake |
| 7 | One long-lived session per run | Suspended sessions burn no ACUs; context accumulates; messages auto-resume | Session per iteration (context loss, create overhead, ACU waste) |
| 8 | Mirror `frontend/src/lib/types.ts` verbatim into Pydantic | It already encodes the research-doc schemas; three workstreams code against it | Inventing a second schema |

### The simulation gate (the one hard rule)

> A `done` from the agent whose recommended candidate has **no simulation on
> record is not accepted**. The orchestrator simulates it and replies with the
> results. Analogy: you don't merge on "the tests would probably pass."

Everything else about pacing is the agent's call. Crash barriers only:
`max_acu_limit` (Devin-enforced) and a wall-clock backstop. Tripping a barrier
never fails the run — it emits `run_finished{truncated: true}` with best-so-far.
**The agent is told its budget in the prompt** ("~N minutes, X ACUs, you must
simulate before concluding — spend it as you judge") so it self-paces. For the
demo we state a tight budget (~8 min) so the run has a watchable arc; the
number is config, not architecture.

---

## 3. Devin v3 API usage

Base `https://api.devin.ai/v3`, auth `Authorization: Bearer cog_…` (service
user). Verified against live docs 2026-08-22.

| Purpose | Endpoint |
|---|---|
| Upload file → URL | `POST /v3/organizations/{org}/attachments` (multipart, field `file`) |
| Create session | `POST /v3/organizations/{org}/sessions` |
| Follow-up message (auto-resumes) | `POST …/sessions/{id}/messages` |
| Poll messages | `GET …/sessions/{id}/messages?after={cursor}&first=100` |
| Poll status / structured_output | `GET …/sessions/{id}` |
| List / download artifacts | `GET …/sessions/{id}/attachments` → pre-signed URLs |

Session status: `new → claimed → running → exit|error|suspended|resuming`;
`status_detail ∈ working | waiting_for_user | waiting_for_approval | finished`.

### Feature usage matrix — earn your place

| Devin feature | Use? | Rationale |
|---|---|---|
| Sessions + messages | ✅ core | The iteration loop |
| Attachments (both directions) | ✅ core | `.blend` in; geometry.json, report.md, builder `.py` out |
| `structured_output_schema` | ✅ final report only | Validated machine-readable result; NOT the handshake (ADR-6) |
| `repos: []` | ✅ | Clone our repo into the VM → skills + shared scripts discovered |
| **Skills** (`.agents/skills/*/SKILL.md`) | ✅ | Open Agent Skills standard; procedural instructions + bundled scripts (§4.2) |
| Playbook (`playbook_id`) | ✅ | Versioned RF ground rules + protocol spec, out of the per-run prompt |
| `max_acu_limit`, `devin_mode`, `title`, `tags` | ✅ | Budget barrier; mode default `normal` (measure before optimizing); traceability |
| `session_secrets` | ✅ if needed | Only if the VM must call back into our API |
| Blueprints/snapshots | ❌ for now | VM + `pip install bpy` at session start is fast enough; revisit only if install time hurts |
| MCP | ❌ | Org-admin UI config only, needs public HTTPS endpoint — wrong critical path for a hackathon |
| Managed Devins / workflows | ❌ | Single-session loop is sufficient; parallel children add failure modes, not quality |
| Knowledge notes | ❌ | Playbook covers it; one mechanism, not two |

Rate-limit posture: ≥30 s between messages to a session (documented on adjacent
APIs; assume it applies), poll at 10–30 s with exponential backoff on 429,
**one consolidated results message per iteration** — never per-sim messages.

**Live-API findings (2026-08-22, verified against a real session):**
- Messages list `end_cursor` is **inclusive of the last item** — polling with
  `after=end_cursor` re-delivers the newest message every time. Without
  message-id dedupe the loop re-executes stale actions and the whole
  conversation runs out of phase (observed live; Devin recovered gracefully,
  our orchestrator did not converge). Adapter now dedupes on `event_id`.
- Response shape is flat: `{items, end_cursor, has_next_page, total}` (no
  `page_info` wrapper).
- Session termination (DELETE) is async — status stays `running` briefly.
- A closing message that reads like a question elicits another reply; the
  close message must state "no further reply is needed".
- Devin quality note: with the §6.4 evidence layers it did real engineering —
  tie-broke electrically identical candidates by clearance, targeted
  resonance moves, and flagged our replayed-evidence bug ("sweep returned
  unchanged records") before we found it.

### 4.1 AgentPort (the seam)

Everything agent-facing goes through one interface so Devin can be swapped for
a local heuristic mock (demo insurance, offline dev):

```python
class AgentPort(Protocol):
    async def start(self, ctx: RunContext) -> None      # open session, deliver spec+budget
    async def next_action(self, report: IterationReport | None) -> AgentRequest
    async def narrate(self) -> list[str]                # drain human-readable commentary
    async def close(self, reason: str) -> None
```

(Finalized in implementation: request/response instead of an event iterator —
the orchestrator drives, the adapter hides Devin's async message polling.)

`mock.py` implements the same protocol using the heuristic scorer (port of the
frontend's `scorePoint`) — it proposes, "reads" results, refines once, accepts.
**M0 runs entirely on the mock** (§11).

### 4.2 Skills we ship in the repo

Skills are `SKILL.md` files at `.agents/skills/<name>/`, auto-discovered when
Devin clones the repo. They inject procedure into context; Devin's own VM shell
executes any bundled scripts. They are *not* a tool-calling mechanism — that's
fine, we need procedures.

- **`blend-extract`** — "Given a `.blend` attachment: `pip install bpy`, run
  `python tools/extract_blend.py <file> --out geometry.json`, sanity-check
  units/bboxes, return geometry.json as an attachment + summary in a message."
  The script is the same one the backend fallback runs (§8) — one code path.
- **`nec-builder`** — how to author a new antenna geometry builder: module
  contract (`build(ctx, params) -> feed_tag`), NEC segment rules (junctions at
  segment endpoints only, segment length λ/20–λ/10, wire radius), and the
  calibration harness it must pass before we load it (§7.4).

### 4.3 Session lifecycle

```
POST /runs (blend, prompt, bands)
  └► upload .blend → attachment URL
  └► create session:
        prompt   = task + budget + protocol pointer + spec/band targets
        repos    = [RaufHood/challenge]      → skills available
        attachment_urls = [blend_url]
        playbook_id, structured_output_schema, max_acu_limit, title, tags
  └► poll messages (cursor) ──► parse fenced JSON ──► orchestrator
        agent sleeps between our replies (no ACU burn); message auto-resumes
  └► on DONE (gate-checked): request report → structured_output + attachments
```

---

## 5. Run state machine

```
INGEST ──► EXTRACT ──► SPEC ──► AGENT LOOP ──► REPORT
                                (see below)

            ┌───────────────────────────────────┐
            │  PROPOSE / REFINE      (Devin)    │◄──┐
            │            ▼                      │   │
            │  SIMULATE / SWEEP      (backend)  │   │ "not good enough —
            │            ▼                      │   │  here's what I'd change"
            │  SCORE + DIAGNOSE      (backend)  │   │
            │            ▼                      │   │
            │  EVALUATE              (Devin)    │───┘
            └────────────┬──────────────────────┘
                         │ done (simulation gate passed)
                         ▼
                       REPORT
```

| Stage | Actor | Emits | Exit |
|---|---|---|---|
| INGEST | backend | `stage_started`, artifact refs | file stored, run registered |
| INGEST→EXTRACT (device) | backend | `POST /devices` is synchronous: geometry.json, glb, STLs | device `ready` |
| EXTRACT (run, `extract=agent`) | Devin (skill / inlined script) + backend cross-check | `stage_started{backend_extraction}`, `decision{spec accepted, crosscheck, overrides}` | `spec` action or timeout → brief sent |
| SPEC | backend | `artifact(device_spec{source, ambiguities})` | DeviceSpec + anchors final |
| AGENT LOOP | both | `agent_message`, `candidates_proposed`, `sim_started/​sim_result` per sim, `iteration_scored`, `decision` | agent `done` + gate |
| REPORT | both | `artifact(report.md)`, `run_finished` | structured_output stored |

Every event lands in an append-only per-run log with a monotonic `seq`; the WS
replays from `?since=seq` on reconnect. A dropped socket must never kill a demo.

---

## 6. Contracts

### 6.1 Domain types

Pydantic mirrors of `frontend/src/lib/types.ts` — **names and shapes verbatim**:
`DeviceSpec`, `DeviceComponent` (`EmClass = pec|lossy_metal|dielectric|air`),
`BandRequirement`, `Anchor`, `Candidate`, `SimResult`, `Job`. Units mm; origin
at bottom-left-back of device; `Bbox = [min_xyz, max_xyz]`.

Adopted from the frontend's heuristic layer (good ideas, keep):
- **Anchors** — named discrete perimeter positions with outward normals and a
  `corner` flag. The agent reasons over anchor IDs + local offsets, not free
  floats. Constrains the search space and makes rationales legible.
- **ScoreBreakdown** — named components (`clearance/openness/ground/preference`
  + `clearance_mm`, `blocker`) rather than one opaque scalar. Feeds §6.4.
- Placements map + pairwise isolation matrix as the multi-band output shape.

### 6.2 Event envelope (backend → frontend WS)

```json
{ "run_id": "r_x", "seq": 41, "ts": 1766400000.1, "stage": "agent_loop",
  "type": "sim_result", "payload": { } }
```

`type ∈ stage_started | stage_progress | agent_message | candidates_proposed |
sim_started | sim_result | iteration_scored | decision | artifact |
run_finished | error`

### 6.3 Agent wire protocol (fenced JSON inside Devin messages)

Agent → backend, one block per turn:

```json
{ "action": "simulate", "candidates": [ /* Candidate[] ≤ ~30 */ ] }
{ "action": "sweep",    "candidate_id": "c007", "param": "length_mm",
  "from": 24, "to": 34, "step": 1 }
{ "action": "write_builder", "name": "meander_ifa",
  "attachment": "meander_ifa.py", "params_doc": { } }
{ "action": "done", "ranking": ["c012", "c007"], "rationale": "…" }
{ "action": "spec", "extracted": {"method": "skill|script|failed", "n_parts": 15,
  "size_mm": [71.6, 147.6, 7.8]}, "ground": "pcb.ground_pour__copper",
  "components": [{"name": "…", "em": "lossy_metal", "role": "battery"}],
  "summary": "…" }        // first turn of an agent-side extraction only (§8)
```

`sweep` is the leverage move: sims cost ms, agent turns cost minutes — a
30-point sweep in one turn replaces ten guess-iterate turns.

Malformed JSON → one corrective message quoting the schema; second failure →
flag on the run, third → fall back to `mock` to finish (never fail empty).

### 6.4 IterationReport (backend → agent) — evidence, not verdicts

Results are not pass/fail; the agent reasons over them. Four layers, mirroring
what makes a good test failure useful (the diff, not the word "FAILED"):

| Layer | Content |
|---|---|
| **raw** | full S11 curve, resonant f, −6/−10 dB bandwidth vs band edges, efficiency, gain, VSWR, isolation matrix |
| **diff** | per requirement: target, actual, signed margin — "S11 @ 2400 MHz = −4.1 dB, need ≤ −6, **short 1.9 dB**; 2483 edge passes +3.2 dB" |
| **trend** | score + margins vs best of each previous iteration: converging / plateaued / oscillating |
| **hint** | deterministic physics arithmetic: "resonance 2.62 GHz vs 2.44 → arm ~7 % short"; "bandwidth collapsed when anchor moved 4 mm toward battery → clearance-limited" |

`meets_requirements: bool` stays in `SimResult` for the frontend UI; it is not
the agent's decision input.

---

## 7. Simulation subsystem — EXTERNAL BOUNDARY

**Simulation is the sim workstream's subsystem, not ours** (team decision,
2026-08-22). Our contract with it is exactly one callable, run inside our
process pool:

```
solve(spec: DeviceSpec, band: BandRequirement, cand: Candidate) -> SimResult
```

`SIM_SOLVER=module:function` (default `app.sim.oracle:solve`) selects the
implementation — the sim team plugs their engine in without touching backend
code. Everything below describes the **bundled reference implementation**: it
exists so the loop runs end-to-end before/without their engine (same role the
mock agent plays for Devin) and as the executable definition of the contract.

### 7.0 Adapter to the sim team's entry point (2026-08-22)

Their contract (`rf/run_simulation.py`, branch `feat/simulation`) is
`run_simulation(config: dict) -> dict` with `config = {candidate, band,
device, sim}` (types.ts shapes) and a `SimResult`-shaped dict back.
`app/sim/rf_adapter.py` maps our seam onto it — select with
`SIM_SOLVER=app.sim.rf_adapter:solve`, tune with `SIM_OPTS='{"mesh_res":
"coarse","boundary":"MUR","freq_points":21}'`. Mapping decisions:
- their `Candidate` dataclass rejects unknown keys → only types.ts fields
  are forwarded; our `params.height_mm` becomes `feed_point_mm.z` (their IFA
  reads the pin height from it);
- `device.manifest_path` → the device's `geometry.json` (same manifest shape
  their `blend_loader` writes; `DeviceSpec.geometry_path` carries it),
  `device.board.size_mm` = device outline, `device.components` = our
  classified list for their step 6;
- their result has no input impedance → ours stays `(0, 0)` and the scorer
  skips the impedance hints (bandwidth/resonance/clearance hints still work);
- import/solver errors (no openEMS on this machine) → `SimResult{failed,
  notes}` per candidate, never a crashed run. The adapter is verified against
  a stubbed `run_simulation` (`scripts/selftest.py`); against their real
  solver only once it runs on a shared machine (Windows-only wheels today;
  minutes per solve — the loop's batch size must drop accordingly).

### 7.1 Reference oracle

PyNEC (NEC-2 MoM). Chassis = wire-grid lattice built edge-by-edge between
nodes (junctions only at segment endpoints — see `rf/bench_scaling.py`), the
antenna built by a **builder** on top, lumped feed, impedance → S11 vs 50 Ω.
Numbers that make the loop possible: λ @ 2.44 GHz ≈ 122.9 mm, λ/4 ≈ 30.7 mm;
iPhone chassis at λ/10 grid ≈ 13×7 nodes ≈ 160 segments → **milliseconds per
solve** (O(N³) MoM; grid density is the feasibility knob).

Frequency sweep per candidate: ~21 points across band ± guard → S11 curve.
Efficiency/gain from NEC radiated/input power where meaningful; label derived
values honestly in the report.

### 7.2 Known physics limits (stated, not hidden)

- NEC has no bulk dielectrics → glass back, display, battery modeled as PEC
  plates (worst-case detuning). Results are directional, not certification-grade.
- λ/4 = 30.7 mm straight monopole does not fit an iPhone edge → the interesting
  answers are IFA / meander / loop / frame-slot. If the agent proposes a 31 mm
  straight monopole, the spec was underconstrained — feed it that hint.

### 7.3 Scoring & diagnosis

`score.py` computes the §6.4 diff/trend/hint layers. Scalar score = weighted
requirement margins (for ranking/UI only). Hints are arithmetic, not LLM:
resonance offset → length scale factor; bandwidth vs clearance correlation;
isolation vs separation-in-λ.

### 7.4 Agent-authored builders (the wow beat) — re-scoped

Depends on solver internals, which are now the sim team's domain: hot-loading
agent-written geometry modules must target THEIR engine, so this feature needs
their buy-in (M3 coordination point). Until then the orchestrator answers
`write_builder` with a protocol note listing available builders. Original
concept below, kept for that conversation:

When the agent wants a shape the library lacks, it authors a module in its VM
(guided by the `nec-builder` skill), returns it as an attachment; the backend
runs `calibrate.py` on it **before** it's loadable:

1. module imports cleanly in a subprocess sandbox, exposes the contract
2. builds a known reference case; impedance within tolerance of textbook value
3. segment-count sanity (no runaway meshes)

Pass → hot-load into `builders/`, tell the agent it's available. Fail → the
calibration diff goes back as feedback. This is "AI software engineer does
antenna engineering," 30 seconds of demo.

### 7.5 Execution

`ProcessPoolExecutor` (PyNEC is a C extension; process isolation also contains
solver crashes). Batch ≤ ~30 candidates or one sweep per request; every result
emits `sim_result` on the WS the moment it lands.

---

## 8. Geometry ingestion — M2, live-verified 2026-08-22

**Facts vs judgment.** `tools/extract_blend.py` (bpy) produces *facts*:
every mesh object's world bbox in a canonical frame (mm; x width, y height,
z thickness; origin at the min corner), material key, `eps_r` /
`sigma_S_per_m`, triangle count. It never decides what a part *is* for the
RF model. `classify.py` adds the *judgment* heuristically (EmClass from
sigma/eps, structural `role` from names, ground-plane choice) and lists every
ambiguity. The agent can override any of it (the `spec` action, §6.3).

**Asset convention (shared with the sim workstream, `data/*/materials.json`):**
object name `<node_path>__<material_key>`, custom props `node_path` /
`material_key`, sidecar `material_vocabulary_used[key] = {eps_r, sigma}` plus
`material_gaps` (the author's own caveats). Without a sidecar the script falls
back to Blender material / object names and a small built-in vocabulary, and
says so (`em_source`). `geometry.json` is a **superset of the sim team's
`device.json` manifest** (`parts[].{node_path, material_key, eps_r,
sigma_S_per_m, bbox_mm, stl_path…}`) so `rf/run_simulation.py:load_device`
reads it unchanged; STLs per part go to `parts/`.

**Frame normalisation is explicit.** Units are resolved sidecar → scene
`unit_settings` → extent heuristic (a handset is 50–300 mm), axes permuted so
the longest extent is y and the shortest z (proper rotation only), then name
votes (display ⇒ high z, camera ⇒ high y, USB/speaker ⇒ low y) fix the two
remaining 180° ambiguities. Everything applied is reported under `frame`.
Verified on fixtures: a canonical, a standing-metre-scaled and an upside-down
synthetic phone all normalise to identical bboxes; the sim team's 757k-tri
Blender-5.2 axe asset extracts in 5 s (sidecar, custom props, 2.8 MB
decimated glb).

**Two runners, one script (ADR-2).**
- *Agent-side (default, `extract=agent`)*: the session is created with the
  `.blend` (+ sidecar) as `attachment_urls`; the prompt asks Devin to run the
  script — via the `blend-extract` skill when `DEVIN_REPO` is set, otherwise
  the script is **inlined in the prompt** (the repo is private; this removes
  the GitHub-integration dependency) — and reply with a `spec` action
  (extraction digest, ground choice, classification overrides, layout
  summary). The backend has *already* run the same script at `POST /devices`
  (it needs the glb for the viewer regardless); it cross-checks size and part
  count, merges the agent's overrides, emits a `decision{spec accepted,
  crosscheck, overrides}` event, and sends the design brief (spec, anchors,
  requirements). Timeout (`EXTRACT_TIMEOUT_S`, 600) or a `failed` method ⇒
  backend classification stands and the run proceeds. The design-loop wall
  clock starts *after* the brief.
- *Backend-only (`extract=backend`)*: spec is final before the session; the
  create prompt carries everything (M1 behaviour). Use for tight demos.

**Device lifecycle / HTTP:** `POST /devices` (multipart `blend`, optional
`materials`) → extraction → `{device_id, spec, anchors, ambiguities,
artifacts}`; `GET /devices/{id}/artifacts/{device.glb|geometry.json|
materials.json|parts/*.stl}`; `POST /runs {device_id, bands, agent,
extract}`. Devices are content-addressed (`dev_<sha256[:10]>`), cached under
`backend/var/devices/`. No `device_id` ⇒ canned `phone_v1` (regression
baseline). Requirements are not in the `.blend`: `bands.py` mirrors the
frontend band catalogue; the run's `bands[]` selects.

**Fixture:** `tools/make_phone_blend.py` generates a 15-part synthetic handset
in the asset convention (`data/phone_synth_v1/`), with `--standing
--metres --upside-down` variants for normalisation tests. Replace with the
real iPhone `.blend` when it lands — nothing downstream changes.

---

## 9. Backend HTTP/WS surface

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/runs` | multipart: `blend`, `prompt`, `bands[]`, overrides → `{run_id}` |
| `GET` | `/runs/{id}` | full snapshot (shape compatible with frontend `RunSnapshot`) |
| `WS` | `/runs/{id}/events?since={seq}` | live events, replayable |
| `POST` | `/runs/{id}/messages` | user mid-run feedback → rides with the next evidence message (no extra agent turn) |
| `GET` | `/runs/{id}/artifacts/{name}` | `report.md`, `run.json`, `s11_<cid>.csv` (rendered on demand) |
| `GET` | `/runs` | list runs |
| `POST` | `/devices` | multipart `.blend` (+ `materials.json`) → extraction → spec/anchors/artifacts (§8) |
| `GET` | `/devices/{id}`, `/devices/{id}/artifacts/{name}` | snapshot; `device.glb`, `geometry.json`, `materials.json`, `parts/*.stl` |
| `GET` | `/healthz` | liveness |

Store: in-memory dict + append-only event lists. No DB for a 36 h hackathon;
`store.py` is the interface if that changes.

---

## 10. Failure modes

| Failure | Response |
|---|---|
| Devin API down / slow | `AgentPort` → `mock.py`; demo runs end-to-end regardless |
| Malformed agent JSON | corrective message ×2 → mock fallback (§6.3) |
| 429 / rate limit | exponential backoff; consolidated messages by design |
| Agent-side extraction fails | backend fallback runner, same script |
| Solver crash / NaN | process isolation; candidate marked `failed` + reason in next report |
| WS drop | event replay via `?since=` |
| ACU/wall-clock barrier | `run_finished{truncated: true}` + best-so-far, never empty |

---

## 11. Build order

Rule: **always demoable** — every milestone ends in a run that completes.

- **M0 — walking skeleton: DONE 2026-08-22.** `POST /runs` → mock agent →
  reference sims → WS events (contiguous seq + replay verified) → report.
  Result on canned spec: IFA @ right edge, L=31.2 mm, −17.7 dB, all pass.
- **M1 — Devin wired: LIVE-VERIFIED 2026-08-22** (run #3: 3 iterations,
  32 sims, clean `done` through the gate; final IFA @ e_r6 L=31.25 mm gap
  5.5 mm, S11 −21.5 dB, VSWR 1.24, full band < −10 dB; structured_output
  populated; 0.0 ACUs billed across all three test sessions). `DevinAgent` (v3 sessions/messages/polling, 429 backoff, ≥30 s send
  spacing, fenced-JSON parse with 2 corrective retries, session-end → forced
  best-so-far done). Devin is the DEFAULT agent; `agent="mock"` explicit
  fallback. Playbook deferred: protocol text ships in the create prompt for
  now (playbook_id is config once org access exists).
- **M2 — geometry: LIVE-VERIFIED 2026-08-22** (§8). `tools/extract_blend.py` +
  `blend-extract` skill + `classify.py`; `POST /devices` → spec/anchors/glb;
  agent-side extraction turn with backend cross-check and fallback; anchors
  and the reference solver's ground plane derived from the real spec (role
  field). Fixture generator stands in for the missing iPhone `.blend`.
  Live run (synthetic phone, `extract=agent`, script inlined): Devin
  installed bpy and ran the script in its VM (~2 min), returned a `spec`
  with four unprompted layout observations (oversized ground pour, unslotted
  rails, full-face shield, battery block), cross-check agreed (15 parts /
  size), 1 override applied (display shield → `shield`, correct), then
  3 iterations / 46 sims → monopole @ top-right corner, L 27.75 mm, h 4 mm,
  S11 −24.3 dB, VSWR 1.21, with a tolerance analysis in the rationale.
  ~5 min wall clock end to end; structured_output populated. Bug found and
  fixed from that run: a re-roled full-face sheet must not count as a
  clearance obstacle (now excluded by footprint ≥ 50 % of the device).
- **M3 — depth:** sweep action ✅ (M0), hint layer ✅ (M0), per-candidate
  band resolution for multi-band runs ✅ (2026-08-22; no isolation matrix —
  scope decision pending), `nec-builder` skill + `write_builder` calibration
  gate ❌ **not built** (needs the sim team's engine, §7.4; the orchestrator
  answers `write_builder` with a protocol note).
- **M4 — polish:** `report.md` / `run.json` / S11 CSV artifacts ✅, agent
  structured_output captured as `agent_report` artifact ✅, mid-run user
  messages ✅, mock fallback when the agent channel dies before any
  simulation ✅ (all 2026-08-22, covered by `scripts/selftest.py`).
  ❌ not built: openEMS single-shot confirmation of the winner (belongs to
  the sim engine via `rf_adapter`), Devin playbook (`playbook_id`, config
  once org access exists), session termination on close (left alive for
  inspection; `DEVIN_TERMINATE_ON_CLOSE=1` to delete).

---

## 12. Open questions

1. ~~Devin credentials~~ — resolved (service user, v3). Open: does the org's
   GitHub integration see `RaufHood/challenge` (private)? Until confirmed,
   `DEVIN_REPO` stays unset and the extraction script is inlined (§8).
2. **Demo scope: single-band (Wi-Fi 2.4) vs multi-band** — test prompt says
   2.4 GHz; frontend models multi-band + isolation. Recommend: build
   single-band, keep contracts multi-band-shaped (they already are).
3. Which iPhone `.blend` asset; object naming quality decides how much
   classification pain §8 absorbs. The synthetic fixture follows the sim
   team's `materials.json` convention — if the real asset does too,
   classification is exact; if not, the name heuristics + agent overrides
   carry it.
4. Entire capture is mandatory for submission — hooks are repo-committed, but
   each teammate must `entire login` locally.

## 13. Decision log

- **2026-08-22 (integration pass)** (a) Sim seam adapted to the sim team's
  actual `run_simulation(config)` contract via `rf_adapter` (§7.0) — our
  `solve()` seam stays; the adapter is the only file that knows their shape.
  (b) Real asset landed on `feat/simulation` (`data/apple_iphone_15_pro/`,
  191 parts, 235k polys, sidecar dialect `materials.{key}`): extractor now
  reads both sidecar dialects; classification on it found three real-world
  gaps, fixed: a thick rail named "substructure" was chosen as ground over
  the midplate sheet (sheet-likeness now wins), sub-4 mm screws dominated the
  clearance metric (excluded), and a 191-component spec is 50 KB — over the
  Devin message cap — so the design brief lists RF-relevant parts only
  (≥ 5 mm, non-air, ≤ 80, ground first; the rest summarised). (c) User
  mid-run messages are folded into the next evidence message rather than
  sent as their own turn: no rate-limit exposure, no extra ACU, and the agent
  sees them exactly when it can act. (d) Agent's structured_output is an
  addendum artifact after `run_finished`, never a gate on it (it lands on
  Devin's schedule, ~30–60 s after `done`). (e) Multi-band: each candidate is
  simulated/scored against its own `band_id`; isolation is still out of scope.

- **2026-08-22 (M2)** (a) Extraction split into facts (script) vs judgment
  (classify + agent `spec` action) — the agent "reads the build file" AND the
  backend always has the same geometry for the viewer/cross-check; neither
  waits on the other. (b) `geometry.json` made a superset of the sim team's
  `device.json` manifest (their `feat/simulation` branch, `backend/load_blend.py`)
  rather than a second format — one extraction for both workstreams; to
  raise with them: retire `backend/load_blend.py` in favour of
  `tools/extract_blend.py`, and note `backend/requirements.txt`(bpy) collides
  with our uv project — bpy needs Python 3.11, so the backend runs it in a
  subprocess (`BPY_PYTHON` / `BLENDER` / ephemeral `uv run --with bpy`).
  (c) Optional `role` / `em_source` fields added to `DeviceComponent` and
  `region_pref`/`color` to `BandRequirement` — additive to the frontend
  schema (ADR-8 kept: names/shapes verbatim, extras optional). (d) Repo is
  private → script inlined in the Devin prompt unless `DEVIN_REPO` is set.
  (e) Frontend glb: exported with `export_yup=False` in the canonical frame
  so node names and coordinates match `spec.components[].bbox_mm` directly.

- **2026-08-22 (build)** M0 shipped; M1 code shipped. Changes while building:
  (a) **Sim demoted to an external boundary** — user direction: sim is another
  teammate's workstream; we integrate via the single `solve()` contract +
  `SIM_SOLVER` env seam; our PyNEC oracle stays as bundled reference.
  (b) `write_builder` re-scoped pending sim-team buy-in (§7.4).
  (c) AgentPort finalized as request/response (`next_action`), not an event
  iterator. (d) Physics lesson locked into the reference builders: arms must
  run in the clearance strip BESIDE the plane, not above it (image-current
  cancellation ruins R); IFA topology is short-at-end, feed inboard.
  (e) Reference solver perf: ~105 ms per 21-point sweep → sweeps of 10–30
  variants per agent turn are the intended currency.
- **2026-08-22** Initial design. Agent-side extraction via skill (user
  directive); convergence owned by the agent with a hard simulation gate (user
  directive — orchestrator caps dropped); results delivered as evidence layers
  (raw/diff/trend/hint), not pass/fail; PyNEC in-loop, openEMS demoted to
  optional confirmation; Devin feature set chosen by the §3 earn-your-place
  matrix — blueprints, MCP, managed Devins, knowledge explicitly not used.
