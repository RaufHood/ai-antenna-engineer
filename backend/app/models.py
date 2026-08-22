"""Domain contracts. Pydantic mirrors of frontend/src/lib/types.ts — names and
shapes verbatim (DESIGN.md ADR-8). Units mm; origin at bottom-left-back corner
of the device; Bbox = [min_xyz, max_xyz]."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

Vec3 = tuple[float, float, float]
Bbox = tuple[Vec3, Vec3]

EmClass = Literal["pec", "lossy_metal", "dielectric", "air"]
AntennaType = Literal[
    "IFA", "PIFA", "monopole", "loop", "frame_slot", "patch_array", "ceramic_chip"
]
RegionId = Literal["bottom", "top", "left", "right"]
# Structural role of a part in the RF model. Additive to the frontend schema
# (optional field; the viewer ignores it). `ground` = the reference plane the
# solver builds the chassis from; `display`/`ground` are excluded from the
# clearance metric because the antenna volume necessarily sits above them.
ComponentRole = Literal["ground", "display", "frame", "battery", "back_cover",
                        "board", "shield", "module", "other"]


class DeviceComponent(BaseModel):
    name: str  # must match the glTF node name exported from Blender
    label: str
    em: EmClass
    epsilon_r: float | None = None
    loss_tangent: float | None = None
    bbox_mm: Bbox
    role: ComponentRole = "other"
    # provenance of the em classification: sidecar | name-heuristic | agent | canned
    em_source: str = "canned"
    sigma_s_per_m: float | None = None


class BandRequirement(BaseModel):
    id: str
    name: str
    short: str
    service: str
    f_low_ghz: float
    f_high_ghz: float
    clearance_mm: float  # minimum antenna clearance (keep-out radius)
    s11_db_max: float
    efficiency_min: float
    antenna_types: list[AntennaType]
    region_pref: dict[str, float] = Field(default_factory=dict)  # frontend hint
    color: str = ""

    @property
    def f_mid_ghz(self) -> float:
        return (self.f_low_ghz + self.f_high_ghz) / 2


class SarLimit(BaseModel):
    standard: str
    w_per_kg: float
    mass_g: float


class Requirements(BaseModel):
    bands: list[BandRequirement]
    vswr_max: float = 3.0
    isolation_db_max: float = -10.0
    sar_limit: SarLimit


class Board(BaseModel):
    size_mm: Vec3
    stackup: str = "FR4"
    epsilon_r: float = 4.4
    loss_tangent: float = 0.02


class Enclosure(BaseModel):
    back: str = "glass"
    frame: str = "aluminum"
    epsilon_r_back: float = 5.5


class DeviceSpec(BaseModel):
    device_id: str
    name: str
    board: Board
    enclosure: Enclosure
    components: list[DeviceComponent]
    requirements: Requirements


class Anchor(BaseModel):
    id: str
    label: str
    region: RegionId
    pos_mm: Vec3  # centre of the candidate antenna volume
    outward: Vec3  # outward normal along the device surface
    corner: bool


class Candidate(BaseModel):
    candidate_id: str
    anchor_id: str
    band_id: str
    antenna_type: AntennaType
    position_mm: Vec3
    feed_point_mm: Vec3
    length_mm: float
    orientation: Literal["edge", "corner", "face"]
    prior: float = 0.5  # pre-simulation heuristic score 0..1
    rationale: str = ""
    # free-form geometry parameters forwarded to the builder (e.g. meander pitch)
    params: dict[str, float] = Field(default_factory=dict)


class S11Point(BaseModel):
    f_ghz: float
    s11_db: float


class SimResult(BaseModel):
    candidate_id: str
    status: Literal["queued", "running", "complete", "failed"]
    runtime_s: float = 0.0
    s11_curve: list[S11Point] = Field(default_factory=list)
    s11_min_db: float = 0.0
    resonant_ghz: float = 0.0
    bandwidth_mhz: float = 0.0  # -6 dB bandwidth
    efficiency: float = 0.0
    peak_gain_dbi: float = 0.0
    vswr: float = 99.0
    impedance_ohm: tuple[float, float] = (0.0, 0.0)  # (R, X) at band centre
    meets_requirements: bool = False  # UI field; the agent gets §6.4 layers instead
    notes: str = ""


# ---------------------------------------------------------------- agent wire --

class SimulateRequest(BaseModel):
    action: Literal["simulate"]
    candidates: list[Candidate]


class SweepRequest(BaseModel):
    action: Literal["sweep"]
    candidate_id: str
    param: str  # e.g. "length_mm" or any Candidate.params key
    start: float = Field(alias="from")
    stop: float = Field(alias="to")
    step: float

    model_config = {"populate_by_name": True}


class WriteBuilderRequest(BaseModel):
    action: Literal["write_builder"]
    name: str
    attachment: str  # filename of the .py module the agent produced


class DoneRequest(BaseModel):
    action: Literal["done"]
    ranking: list[str]  # candidate_ids, best first
    rationale: str


class SpecComponent(BaseModel):
    """Agent's EM judgment for one extracted part (DESIGN.md §8). Any field
    left null keeps the backend's heuristic classification."""
    name: str  # blender object name (or node_path)
    em: EmClass | None = None
    role: ComponentRole | None = None
    epsilon_r: float | None = None
    note: str = ""


class SpecRequest(BaseModel):
    """First turn of an agent-side extraction: what the agent read from the
    build file and how it classifies the parts for the RF model."""
    action: Literal["spec"]
    extracted: dict = Field(default_factory=dict)  # method, n_parts, size_mm, notes
    ground: str | None = None      # part that serves as the ground reference
    components: list[SpecComponent] = Field(default_factory=list)
    summary: str = ""


AgentRequest = (SimulateRequest | SweepRequest | WriteBuilderRequest | DoneRequest
                | SpecRequest)


class RequirementDiff(BaseModel):
    """One requirement, evidence-style: target, actual, signed margin."""
    requirement: str
    target: float
    actual: float
    margin: float  # positive = passing, negative = short
    unit: str
    passing: bool


class CandidateReport(BaseModel):
    candidate_id: str
    result: SimResult
    diffs: list[RequirementDiff]
    score: float  # scalar for ranking only
    hints: list[str]  # deterministic physics arithmetic, not LLM


class IterationReport(BaseModel):
    """Backend -> agent after each simulate/sweep batch (DESIGN.md §6.4)."""
    iteration: int
    reports: list[CandidateReport]
    best_so_far: str | None  # candidate_id
    trend: str  # converging | plateaued | oscillating | first_iteration
    notes: list[str] = Field(default_factory=list)


# -------------------------------------------------------------------- events --

class EventType(str, Enum):
    stage_started = "stage_started"
    stage_progress = "stage_progress"
    agent_message = "agent_message"
    candidates_proposed = "candidates_proposed"
    sim_started = "sim_started"
    sim_result = "sim_result"
    iteration_scored = "iteration_scored"
    decision = "decision"
    artifact = "artifact"
    run_finished = "run_finished"
    error = "error"


class RunEvent(BaseModel):
    run_id: str
    seq: int
    ts: float
    stage: str
    type: EventType
    payload: dict
