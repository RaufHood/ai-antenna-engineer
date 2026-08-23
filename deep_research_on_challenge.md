# Automated RF Antenna Placement via AI Agent + EM Simulation: Research & System Specification

*A grounding document for a hackathon team building software that uses an AI coding agent (Devin) to determine optimal antenna placement in a phone design (from a Blender 3D model), run electromagnetic simulations, and output engineering recommendations. Written so each teammate — 3D modeling, UI/visualization, simulation, agent integration — can extract what's relevant and begin immediately.*

## TL;DR
- **Feasible with real caveats.** A team can build an end-to-end pipeline where an AI coding agent ingests a Blender phone model plus a device-constraint spec, generates and runs open-source FDTD electromagnetic simulations (openEMS), and outputs ranked antenna-placement recommendations — **but full-fidelity FDTD of a whole phone takes tens of minutes to hours per run**, so the demo must use coarse meshes, a small candidate set, and/or surrogate models. Do not promise "thousands of configurations."
- **Recommended stack:** Blender (geometry) → glTF/STL export with per-component material tags → Three.js viewer for the UI → **openEMS** (Python, GPLv3, free, fully scriptable, with a built-in SAR post-processor) as the solver → **Devin v3 API** orchestrating a simulate–evaluate–optimize loop with structured JSON output.
- **Core RF facts to build against:** phone antennas are electrically small resonators (PIFA/IFA/monopole/loop below 6 GHz, patch arrays at mmWave); target −6 to −10 dB S11, VSWR < 2–3, >40–50% efficiency; respect keep-out zones (≥15 mm clearance at 2.4 GHz, more at sub-GHz); SAR limits are **1.6 W/kg averaged over 1 g of tissue (FCC, per 47 CFR §1.1310)** and **2.0 W/kg over 10 g (ICNIRP/CE)**.

## Key Findings
1. **openEMS is the only realistic full-wave solver for this hackathon:** free, GPLv3, Python-scriptable, handles bulk dielectrics, computes S-parameters/near+far fields/radiation patterns, and includes built-in 1g/10g SAR averaging. A community MCP server (`mcp-openems` by RFingAdam) already generates complete openEMS Python scripts from AI agents.
2. **The Devin v3 API supports the full loop needed:** upload files → create a session with a structured-output JSON schema → send follow-up messages → poll status → download agent-produced artifacts.
3. **Whole-phone FDTD is the bottleneck.** A single moderately-meshed run is roughly an hour on a quad-core CPU; brute-force sweeps of hundreds of configs are infeasible without coarse models, parallelism, or ML surrogates.
4. **Placement is normally a manual, iterative RF-engineer task;** characteristic mode analysis (CMA) is the standard "where to place / where to feed" pre-simulation technique and is a good conceptual model for the agent's candidate-generation layer.
5. **Autonomous agent design loops already work in adjacent domains** (photonics, inertial fusion, turbomachinery, chip DSE), validating the architecture — e.g., an agentic photonics loop used an MCP interface to solvers plus a GPU cluster to run hundreds of simulations per design problem (Kharel et al., *Autonomous agentic design for photonics*, arXiv:2606.00915, 2026).

## Details

### 1. Phone/Mobile Antenna Fundamentals

**How phone antennas work.** A phone antenna is a resonant conductor that converts guided RF currents into radiated EM waves. In handsets the antenna and the PCB ground plane together form the radiating system — the ground plane (chassis) is itself an essential radiator at low bands, which is why placement and clearance matter so much. Most handset antennas are "electrically small" (smaller than a quarter wavelength), which forces trade-offs between size, bandwidth, and efficiency.

**Antenna types (comparison):**

| Type | Typical bands | Size/profile | Bandwidth | Pros | Cons | Phone use |
|---|---|---|---|---|---|---|
| PIFA (Planar Inverted-F) | 0.7–6 GHz | Low profile, needs volume above ground | Moderate | Compact, low SAR, less hand-detuning | Needs height/clearance | Legacy main cellular |
| IFA (Inverted-F) | 0.7–6 GHz, 2.4/5 GHz | Very thin, PCB-etched | Narrow–moderate | Cheap, integrable on PCB | Narrow bandwidth | Wi-Fi/BT, secondary |
| Monopole / loop | 0.6–6 GHz | Small footprint | Moderate | Simple, wideband variants | Needs ground plane | Main + diversity |
| Metal-frame/bezel | 0.6–6 GHz | Uses the phone's metal rim | Wide (multi-mode) | Uses existing structure, ID-friendly | Complex tuning, hand effects | Modern flagships |
| Patch / microstrip | >2 GHz, mmWave | Planar on substrate | Narrow | Directional, array-able | Narrow BW, large at low freq | mmWave elements |
| Slot | Various | Cut in ground/frame | Moderate | Integrates into metal | Design complexity | Metal-frame phones |
| Ceramic chip | 2.4/5 GHz, GNSS | Tiny SMD | Narrow | Smallest, easy assembly | Lower efficiency | Wi-Fi/BT/GPS |
| Flexible/FPC | 0.6–6 GHz | Conforms to housing | Moderate | Fits curved housing | Assembly complexity | Cellular main in slim phones |
| mmWave array (AiP) | 24–40 GHz | Module, multiple elements | Wide | Beam steering, high gain | LOS-limited, blockage | 5G FR2 |

*Real-world mmWave reference:* Qualcomm's QTM052 module integrates a phased array + transceiver + RF front-end, covers n257/n261/n260 (26.5–29.5, 27.5–28.35, 37–40 GHz), supports up to 800 MHz bandwidth, and up to four modules are placed in one phone for blockage resilience; face or edge placement give similar performance.

**Frequency bands used in phones:**

| Service | Frequency | Notes |
|---|---|---|
| Cellular low-band (LTE/5G FR1) | ~600–960 MHz (B71 600 MHz, B5 850, B8 900) | Best coverage/penetration; largest antenna & clearance |
| Cellular mid-band | ~1.7–2.7 GHz (B1, B3, B7) | Capacity/coverage balance |
| 5G NR sub-6 mid/high | 3.3–5.0 GHz (n77/n78/n79) | C-band; 100 MHz channels common |
| 5G mmWave (FR2) | 24–40 GHz (n257 26.5–29.5, n261 27.5–28.35, n260 37–40) | Phased arrays, beam steering, LOS |
| Wi-Fi | 2.4 GHz, 5 GHz, 6 GHz (Wi-Fi 6E/7) | |
| Bluetooth | 2.4 GHz ISM | Often shares Wi-Fi 2.4 antenna |
| GPS/GNSS | ~1.559–1.610 GHz (GPS L1 1575.42, GLONASS ~1602, Galileo/BeiDou) | Dedicated or shared |
| NFC | 13.56 MHz | Inductive loop, not a radiating antenna |

**Performance metrics engineers care about:**
- **S11 / return loss** — reflection at the port; engineers target **S11 ≤ −6 dB (handsets) to −10 dB**. −10 dB return loss ≈ VSWR 2:1; −20 dB ≈ 1.2:1. (A VSWR of 3 reflects ~25% of incident power.)
- **VSWR** — impedance match; < 2 acceptable, < 1.5 excellent.
- **Bandwidth** — frequency range meeting the S11 threshold.
- **Gain (dBi)** and **radiation efficiency** — handset main antennas often run 40–60% total efficiency; above 50% is good given losses.
- **Radiation pattern** — near-omnidirectional desired for cellular; directional/steerable for mmWave.
- **Isolation** (S12/S21) between antennas — target better than −10 to −15 dB for MIMO/diversity; improved via spatial separation, decoupling structures, and ground-plane current control.
- **SAR** — regulatory tissue-absorption limit (see §6).
- **Detuning** — frequency shift from hand, head, battery, enclosure; a central design risk (S11 detuning worsens as air gap to tissue shrinks).

**Placement constraints in real phones:**
- **Keep-out zones**: a 3D copper-free/component-free volume around the antenna, treated as a **hard constraint** from the antenna datasheet — "your schematic is a suggestion; your PCB layout is the law." Rule of thumb ~15 mm clearance for 2.4 GHz; larger at sub-GHz. No ground/power plane under the radiator on any layer. Even a single grounded mounting screw inside the zone can detune the antenna and fail RF testing.
- **Ground plane**: continuous, and large enough (≥ λ/4 in the relevant dimension; ~30 mm minimum for a 2.4 GHz quarter-wave monopole/IFA). Use edge stitching vias (< λ/10 spacing) but never inside the keep-out.
- **Placement at corners/edges** gives clearance in multiple directions; multiple antennas go in separate corners for isolation.
- **Avoid** battery, LCD/screen metal, cameras, shield cans, speakers, and high-speed switching noise near the antenna.
- **Enclosure material**: plastic is RF-transparent; glass is a moderate dielectric (εr ≈ 5.5) that loads/detunes (screen assemblies are commonly modeled as a ~2 mm glass layer, εr 5.5, or as a grounded metal plate for the worst case); metal backs/frames block RF and require non-conductive "antenna lines"/slots. A metal enclosure acts simultaneously as ground plane, reflector, shield, and resonant cavity.

**How placement is chosen today.** It's a manual, iterative, experience-driven process: RF engineers pick antenna type and a corner/edge location from datasheet reference designs, use **characteristic mode analysis (CMA)** (in HFSS or CST) to understand chassis current modes and where to feed, then run full-wave simulation, tune a matching network, build, and measure in an anechoic chamber — iterating multiple times. CMA "gives physical insight of the current pattern... and helps as a first step toward achieving correct antenna placement." Tools: ANSYS HFSS, CST Studio Suite, FEKO for simulation; VNAs and chambers for measurement.

### 2. Electromagnetic Simulation for Antenna Design

**Numerical methods for Maxwell's equations:**

| Method | Domain | Best for | Notes |
|---|---|---|---|
| FDTD (Finite-Difference Time-Domain) | Time | Broadband, transient, dielectrics, SAR | One run → wideband S-params; used by openEMS, Meep, XFdtd, CST time-domain |
| MoM (Method of Moments) | Frequency | Metal antennas, wires, planar | Efficient for conductors; NEC, FEKO, Momentum |
| FEM (Finite Element Method) | Frequency | Complex geometry, resonant | HFSS, COMSOL; adaptive meshing |
| FIT (Finite Integration Technique) | Time/freq | General 3D | CST's core method |

**EM tool comparison (hackathon lens):**

| Tool | Method | License | Scriptable/API | Learning curve | Hackathon feasibility |
|---|---|---|---|---|---|
| **openEMS** | EC-FDTD | Free, **GPLv3** | **Python + Octave/Matlab** | Medium | **Best choice** — free, automatable, MCP server exists, bulk dielectrics + SAR |
| Meep | FDTD | Free, open | Python/Scheme/C++ | Medium | Great but optics-oriented |
| NEC2 / 4nec2 | MoM | Free/open | Text decks | Low–med | Wire antennas only; no bulk dielectrics |
| Sonnet Lite | MoM | Free (limited) | Limited | Medium | Planar only |
| CST Studio Suite | FIT/FEM | Commercial (expensive) | Python/VBA macros | High | License barrier; has CMA tool |
| ANSYS HFSS | FEM (+ hybrid) | Commercial (expensive) | PyAEDT/Python | High | License barrier; has CMA tool |
| FEKO | MoM/MLFMM/hybrid | Commercial | Lua/API | High | License barrier; strong for electrically large |
| Antenna Magus | Synthesis DB | Commercial | Export to solvers | Low | Design starter, not a solver |

**Recommendation: openEMS.** It is the only free, fully Python-scriptable full-wave solver that handles bulk dielectrics (essential to model FR4, glass, battery). Per the official docs (docs.openems.de), "openEMS is licensed under the GNU General Public License, Version 3 or later" and "simulations are defined via an extensive set of Matlab/Octave or Python interfaces," with built-in near-field-to-far-field transform, 1g/10g SAR calculation, and multi-threading/SIMD/MPI support. The **`mcp-openems`** MCP server (by RFingAdam, AGPL-3.0) exposes an `openems_generate_script` tool that "creates a complete Python script" for FDTD S-parameter/radiation-pattern simulation — a direct fit for agent orchestration.

**Setting up a parametrized simulation:**
- **Geometry import**: openEMS geometry is defined in CSXCAD (primitives + polyhedra). Import Blender/CAD via STL/OBJ (mesh) or STEP (CAD). STL is simplest but lossy (triangles, no materials; Blender assumes meters if units are unset). STEP preserves solids/units/materials but needs a converter. Practical path: export each labeled Blender component as a separate STL/OBJ, then map each to an openEMS material in code.
- **Materials** (define εr and loss tangent):
  - PCB FR4: εr ≈ 4.3–4.7 (use **4.4**), tanδ ≈ 0.02 (lossy above ~4 GHz; note vendor/frequency spread of 3.9–4.8)
  - Metal (ground, frame, shields): PEC or finite-conductivity copper
  - Glass back/screen: εr ≈ 5.5
  - Plastic housing: εr ≈ 2.5–3, low loss
  - Battery: model as a lossy metal box / lossy dielectric block (conservative: treat as a PEC block for worst-case detuning)
- **Ports/feed**: lumped port at the antenna feed (typically 50 Ω); openEMS `calcPort` extracts S-parameters.
- **Mesh**: rule of thumb **λ/20** cell size at the highest frequency; refine at fine features (feed, thin traces) using the 1/3–2/3 rule; graded/smoothed mesh lines to limit cell count. openEMS does **not** auto-mesh fully — mesh lines must be specified (Python `automesh`/`SmoothMeshLines` helpers exist).
- **Boundary conditions**: MUR (simple absorbing) or PML (`PML_8`, better absorption), placed ~λ/2 from the structure; NF2FF box a few cells inside the boundary for the far-field transform. A Gaussian excitation with a center + corner frequency drives the broadband run; an end-criterion (e.g., −40 to −50 dB energy decay) stops it.

**Candidate generation & optimization:**
- **Grid search** over discrete positions (corners/edges) × antenna types × lengths — simplest, agent-friendly, embarrassingly parallel.
- **Genetic algorithms / PSO** — classic for antenna geometry; needs many evaluations (e.g., parallel PSO/FDTD for multiband patches).
- **Bayesian optimization** — sample-efficient, ideal when each sim is expensive (the hackathon case).
- **Surrogate models** — train kriging/GP/neural nets on a handful of EM runs, then optimize on the cheap surrogate; literature reports reaching global optima in as few as ~120 high-fidelity EM simulations, and surrogate-assisted searches needing only tens of true EM validations (e.g., ~44 HFSS validations after a 2000-evaluation surrogate search).

**Compute/runtime reality:**
- A single moderately-detailed openEMS antenna run is **roughly an hour on a quad-core i7**; simpler tutorial antennas run in minutes. An FDTD breast-phantom study cited ~10 hours on 8 cores. Runtime is driven by mesh density (fine features + high frequencies) and the ≥ λ/2 bounding box.
- Running "hundreds/thousands" of full-fidelity configs in a hackathon is **not feasible**. **Shortcuts:** coarse mesh (λ/10), reduced frequency band, 2D/quasi-static pre-screening, CMA to prune positions before simulating, aggressive parallelism (openEMS multithreading/MPI/GPU), and ML surrogates. Realistic demo target: **5–20 candidate configs** at coarse mesh, or a surrogate trained on ~10–30 runs.

### 3. AI Coding Agent Orchestration (Devin v3 API)

**Devin API basics.** REST API, base URL `https://api.devin.ai/v3`, Bearer auth with a service-user key (`cog_` prefix; v1 used `apk_*`). Core capabilities: Devin plans, writes/edits code, runs shell commands, reads docs/browses the web, self-heals failing code, and returns validated structured output. Usage is metered in **ACUs (Agent Compute Units)** — per Cognition's own definition, "a normalized measure of the computing resources Devin uses to complete a task, such as virtual machine time, model inference, and networking bandwidth," where "1 ACU works out to about 15 minutes of Devin actively working." ACUs are not consumed while a session sleeps; cap per session via `max_acu_limit`. (Note: Cognition's public self-serve pricing has shifted toward daily/weekly dollar quotas — Free / Pro $20 / Max $200 / Teams — so treat exact ACU prices as time-sensitive and verify against live docs.)

**Endpoint cheat sheet (verified against docs.devin.ai):**

| Purpose | Method + Path |
|---|---|
| Upload file → get URL | `POST /v1/attachments` (multipart form field **`file`**; returns the attachment URL as a plain string) |
| Create session | `POST /v3/organizations/{org_id}/sessions` — body `{prompt (required), attachment_urls[], repos[], max_acu_limit, structured_output_schema, structured_output_required, devin_mode}` |
| Follow-up message | `POST /v3/organizations/{org_id}/sessions/{devin_id}/messages` — `{"message": "..."}` (auto-resumes a suspended session) |
| Poll messages/events | `GET /v3/organizations/{org_id}/sessions/{devin_id}/messages` (cursor-paginated; items have `source: devin|user`) |
| Poll status | `GET /v3/organizations/{org_id}/sessions/{devin_id}` (read `status`, `status_detail`, `structured_output`, `acus_consumed`) |
| List output artifacts | `GET /v3/organizations/{org_id}/sessions/{devin_id}/attachments` (each item: `attachment_id`, `name`, `url`, `source`, `content_type`; filter `source == "devin"`) |
| Download artifact | HTTP GET the `url` field of each attachment (pre-signed URL; no separate download endpoint) |

**Key mechanics for the build:**
- **Files IN:** upload via `POST /v1/attachments` to get a URL, then either pass URLs in `attachment_urls[]` on create-session **or** embed them in the prompt using the exact literal format **`ATTACHMENT:"{file_url}"`** — all caps, singular, on its own line (the plural `ATTACHMENTS:` is NOT recognized). Alternatively link a GitHub repo via the `repos[]` array. `devin_id` = `session_id` with the `devin-` prefix.
- **Status enum:** `new, claimed, running, exit, error, suspended, resuming`. Poll until `status` ∈ `(exit, error, suspended)` or `status_detail == "finished"`. `status_detail` while running: `working, waiting_for_user, waiting_for_approval, finished`.
- **Files OUT / results:** the cleanest machine-readable path is **structured output** — define a JSON Schema (Draft 7, ≤ 64 KB, self-contained) at create-time via `structured_output_schema`; Devin validates and updates `structured_output` as it works (tell it to update "whenever something relevant happens"). Generated files (openEMS scripts, result plots, the final report) come back through the attachments endpoint. Handle both a bare-array and an `{"items":[...]}` wrapper on the attachments response, as the docs are inconsistent.

**Agentic loop architecture (simulate–evaluate–optimize):**
1. **Orchestrator** (your code, or Devin itself) reads the device-constraint spec + Blender export.
2. **Candidate generation**: agent proposes N placements/types (grid or CMA-informed).
3. **Simulation tool**: agent writes/edits an openEMS Python script per candidate and runs it in its VM (or calls an exposed simulator tool / `mcp-openems`).
4. **Evaluation**: agent parses S11/efficiency/pattern, checks against requirements, updates structured output.
5. **Iterate**: agent selects next candidates (Bayesian/surrogate) until an ACU/time budget or the acceptance thresholds are met.
6. **Report**: agent emits the final ranked recommendation + artifacts.

Define tool-calling interfaces cleanly: `run_simulation(config) -> results.json`, `read_geometry(file) -> parts[]`, and `check_keepout(config) -> bool`. MCP servers (openEMS) are the natural integration surface.

**Precedent.** Autonomous agent design loops are demonstrated in photonics (Kharel et al., arXiv:2606.00915 — "a model context protocol (MCP) interface for tighter agent integration with the simulation tools (Tidy3D, PhotonForge), an in-house GPU cluster that lets the agent run hundreds of simulations per design problem"), inertial-fusion multiphysics (arXiv:2510.17830), turbomachinery aerodynamics (TurboAgent), and chip design-space exploration (gem5 Co-Pilot) — all validating an LLM-driven perceive–reason–act loop over a scriptable solver.

### 4. 3D Model / Blender Integration

**Representing components for EM.** Model PCB, ground plane, enclosure, battery, camera, and the antenna candidate region as **separate, named Blender objects/collections**, each assigned a material that maps to EM properties (εr, tanδ, conductivity). Keep meshes watertight and low-poly (EM meshing re-discretizes anyway; excessive triangles slow import). Set Blender scene units explicitly to **mm**, since STL carries no unit metadata (Blender assumes meters otherwise).

**Export formats:**
- **STL** — simplest; triangles only, one object per file recommended (batch-export add-ons exist); no materials → map materials by filename in code.
- **OBJ** — carries material *names* via an accompanying MTL file, useful for labeling.
- **glTF/GLB** — best for the UI viewer (below); packs meshes + PBR materials into one file.
- **STEP** — preserves solids/units/materials; importing to Blender needs an add-on (Cascadio/glTF pipeline, or SimLab which preserves materials). Good for CAD interchange but heavier; STEP export from Blender is generally not supported (mesh → B-Rep is lossy).

**UI visualization with ray tracing + labeled components.** Export glTF/GLB from Blender → render in a **Three.js WebGL viewer** (`GLTFLoader`). For ray tracing, use a Three.js GPU path-tracing renderer (e.g., erichlof's THREE.js-PathTracing-Renderer, which supports glTF models with PBR albedo/emissive/metallic-roughness/normal maps). Use the Three.js **raycaster** for click-to-select/label components (map mesh `name` → component labels/textures/keep-out overlays). Alternative: script Blender's Python API (`bpy`) to render labeled Cycles/EEVEE images and embed them. USD is an option for richer scene interchange.

### 5. Software Architecture & Specifications

**System architecture (in words):**
- **Input layer**: device-constraint spec (JSON), Blender model export (glTF for UI; STL/OBJ per-part for sim), requirements (bands, targets, regulatory).
- **Analysis layer**: parse geometry, detect keep-out zones and metal/ground regions, identify candidate placement surfaces.
- **Candidate generation layer**: enumerate {position, antenna type, dimensions} — grid or CMA-informed.
- **Simulation orchestration layer** (agent-driven): Devin writes/runs openEMS per candidate, parses results.
- **Ranking/optimization layer**: score candidates against requirements; Bayesian/surrogate loop.
- **Output/reporting layer**: ranked recommendations + rationale + artifacts, surfaced in the UI.

**Data schemas (proposed contracts between teammates):**

*Device constraint spec:*
```json
{
  "device_id": "phone_v1",
  "board": {"size_mm": [150, 70, 8], "stackup": "FR4", "epsilon_r": 4.4, "loss_tangent": 0.02},
  "enclosure": {"back": "glass", "frame": "aluminum", "epsilon_r_back": 5.5},
  "components": [
    {"name": "battery", "type": "lossy_metal", "bbox_mm": [[10,10,0],[80,60,4]]},
    {"name": "camera",  "type": "metal",       "bbox_mm": [[120,50,0],[145,68,5]]}
  ],
  "keepout_zones": [{"bbox_mm": [[0,0,0],[15,70,8]]}],
  "requirements": {
    "bands": [{"name":"n78","f_low_ghz":3.3,"f_high_ghz":3.8}],
    "s11_db_max": -6.0, "efficiency_min": 0.5, "vswr_max": 3.0,
    "sar_limit": {"standard":"FCC","w_per_kg":1.6,"mass_g":1}
  }
}
```

*Candidate configuration:*
```json
{"candidate_id":"c001","position_mm":[5,35,4],"antenna_type":"IFA",
 "orientation":"edge","length_mm":26,"feed_point_mm":[5,33,4],"target_band":"n78"}
```

*Simulation result:*
```json
{"candidate_id":"c001","status":"complete","runtime_s":2400,
 "s11_db":{"3.3":-4.1,"3.5":-11.2,"3.8":-6.0},
 "resonant_ghz":3.52,"bandwidth_mhz":180,"efficiency":0.57,"peak_gain_dbi":2.6,
 "meets_requirements":true,"notes":"−10 dB BW covers n78 mid"}
```

This last object is also a good shape for Devin's `structured_output_schema` so results return machine-readable.

**Sample end-to-end agent interaction.** User asks: *"Where should the antenna go in this phone, what type, what frequency, and what's the expected performance?"* The agent should:
1. Read the constraint spec + geometry; summarize board size, metal/keep-out regions, target bands.
2. Reason from RF principles: pick antenna type by band (IFA/monopole for sub-6, patch array for mmWave) and candidate corners/edges with maximum clearance.
3. Generate candidates; write an openEMS script per candidate.
4. Run coarse simulations (parallel where possible); parse S11/efficiency.
5. Rank; if none meet requirements, adjust length/matching and re-run (bounded by the ACU budget).
6. Emit structured output + a human-readable report.

**Final engineering report contents:**
- Recommended antenna position (coordinates/region) + type + target band(s).
- Required keep-out region (3D volume).
- Matching-network starting values (e.g., an L/C π-network seed derived from the simulated port impedance).
- Simulation results summary (S11 plot data, efficiency, gain, radiation pattern, resonance/bandwidth).
- Design rationale (why this position/type; CMA/clearance reasoning).
- Comparison against requirements (pass/fail per metric) and ranked runner-up options.
- Risks/caveats (hand/head detuning, SAR exposure, fabrication tolerance).

### 6. Regulatory and Practical Constraints
- **SAR limits**: **FCC/ISED (US/Canada): 1.6 W/kg averaged over 1 g** of tissue — per the FCC RF-safety guidance ("The safe limit for a mobile phone user is an SAR of 1.6 watts per kg (1.6 W/kg), averaged over one gram of tissue") and codified in **47 CFR §1.1310**. **CE/ICNIRP (EU): 2.0 W/kg averaged over 10 g** (ICNIRP 2020 retains the ICNIRP 1998 value, averaged over a 10-g cubic region). **Extremity limit: 4 W/kg over 10 g** (hands, wrists, feet, ankles, pinnae — 47 CFR §1.1310). FCC's 1-g averaging is functionally stricter than the EU's 10-g averaging. The **combined SAR** of simultaneous transmitters at the same body location must stay under the limit.
- **Testing/exemptions**: portable devices with antennas within **20 cm of the body** must demonstrate SAR compliance via standardized phantom testing (FCC OET **KDB 447498**); low-power devices may be categorically excluded, but thresholds are tight (especially Bluetooth at close body separation). SAR testing commonly runs several thousand dollars and can force a redesign, so it belongs in the input spec from day one.
- **Certification basics**: FCC equipment authorization (US), CE/RED (EU), ISED (Canada); mmWave has additional regional rules. EIRP and MPE (maximum permissible exposure) limits also apply.
- **As an input parameter**, "regulatory constraints" should include: target markets, applicable SAR standard + averaging mass, body-separation distance, simultaneous-transmission scenarios, and per-band EIRP limits.

## Recommendations
**Stage 0 — Scope the demo (hour 0–2).** Fix ONE target band (e.g., n78 3.3–3.8 GHz or Wi-Fi 2.4 GHz) and ONE antenna type (IFA or monopole) to bound the problem. Freeze the JSON schemas above as the contracts between teammates so all four workstreams proceed in parallel immediately.

**Stage 1 — Parallel workstreams.**
- *3D modeler*: build the phone as separate named components (PCB, ground, battery, camera, enclosure, antenna-region), units in mm; export glTF (UI) + per-part STL (sim). Ship a fixture STL early so the sim person can start.
- *UI/viz*: Three.js + `GLTFLoader` viewer, raycaster click-to-label, optional GPU path tracer; overlay keep-out zones and candidate positions.
- *Sim*: get openEMS running an IFA/patch-on-ground-plane tutorial first; wrap it as `run_simulation(config) -> result.json`; validate against a known result before integrating.
- *Agent*: stand up the Devin v3 flow (upload → create with `structured_output_schema` → poll → download artifacts); test with a trivial "generate and run an openEMS script" task and confirm the `ATTACHMENT:"{url}"` format works.

**Stage 2 — Integrate the loop (mid-hackathon).** Wire candidate generation (grid of 5–20 positions) → agent runs coarse openEMS (λ/10 mesh, single band) → rank by S11/efficiency → structured output → UI. Keep each sim under ~5–10 min by coarsening the mesh and shrinking the box.

**Stage 3 — If time permits.** Add a surrogate model (GP over a handful of runs) or Bayesian optimization to cut simulation count; add SAR post-processing (openEMS built-in); seed a matching network from the simulated impedance.

**Benchmarks that change the plan:** if a single coarse sim exceeds ~10 min, cut mesh resolution or candidate count, or switch to a 2D/quasi-static pre-screen; if openEMS setup stalls past hour 4, fall back to NEC2 for a wire-monopole proof, or feed pre-computed results to the agent/UI so the demo still shows the full pipeline end to end.

## Caveats
- **Runtime is the dominant risk.** Full-wave FDTD of a whole phone is slow; the demo must use coarse models, few candidates, or surrogates.
- **Geometry fidelity vs. speed.** Highly detailed Blender meshes slow EM import/meshing; simplify to RF-relevant conductors and bulk dielectrics.
- **Material values are approximate.** FR4 εr varies 3.9–4.8 with frequency/vendor; battery/screen models are simplifications. Results are directional, not certification-grade.
- **openEMS has no full auto-mesher** and a not-fully-complete Python interface for some features — budget setup time.
- **Devin specifics may shift.** API pricing/ACU rates and some endpoint response wrappers are in flux; verify against live docs and handle both bare-array and `{"items":[...]}` attachment responses. Concurrent-session caps and rate limits (HTTP 429) apply — back off and retry.
- **Simulation ≠ measurement.** Real hand/head detuning and SAR require physical testing; the tool guides design, it does not replace the anechoic chamber or certification lab.
- **Source quality note.** Primary RF facts (openEMS behavior, Devin docs, FCC/ICNIRP SAR limits, mmWave module specs, agent-loop precedents) are drawn from authoritative sources (openEMS/Devin official docs, FCC/eCFR, IEEE/arXiv, Qualcomm/Microwave Journal). Some tool-comparison and PCB-guideline details come from vendor blogs and buyer's guides and are lower-authority — corroborate before making irreversible design decisions.