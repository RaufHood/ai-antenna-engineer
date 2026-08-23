"use client";

import { useApp } from "@/lib/store";
import type { BandRequirement } from "@/lib/types";
import { Dropdown, MenuItem } from "./primitives";

/**
 * Which band the study solves for — picked under the spec box beside the
 * agent, because it is decided before the run like everything else there.
 * Multi-select: every band ticked is solved on every candidate, so the
 * menu says what each one costs and requires, and the button counts the
 * extras.
 */

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

export function BandMenu({ disabled }: { disabled: boolean }) {
  const bands = useApp((s) => s.spec.requirements.bands);
  const enabled = useApp((s) => s.enabledBands);
  const toggleBand = useApp((s) => s.toggleBand);

  const on = bands.filter((b) => enabled.includes(b.id));
  const label =
    on.length === 0 ? "No band" : on.length === 1 ? on[0].short : `${on[0].short} +${on.length - 1}`;
  const totalMs = on.reduce((sum, b) => sum + solveMs(b), 0);
  const title =
    on.length === 0
      ? "Pick at least one band to solve for"
      : `${on.map((b) => b.name).join(", ")} · ${fmtMs(totalMs)} per candidate`;

  return (
    <Dropdown
      ariaLabel="Bands to solve for"
      label={
        <span className="flex items-center gap-1.5">
          {on[0] && <span className="h-1.5 w-1.5 rounded-full" style={{ background: on[0].color }} />}
          {label}
        </span>
      }
      title={title}
      disabled={disabled}
      width={336}
    >
      {() =>
        bands.map((b) => {
          const isOn = enabled.includes(b.id);
          return (
            <MenuItem
              key={b.id}
              on={isOn}
              onClick={() => toggleBand(b.id)}
              leading={<span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: b.color }} />}
              name={b.name}
              trailing={`${ghz(b.f_low_ghz)}–${ghz(b.f_high_ghz)} GHz`}
              meta={
                <>
                  S11 ≤ {b.s11_db_max} dB · η ≥ {Math.round(b.efficiency_min * 100)}% · clear ≥{" "}
                  {b.clearance_mm} mm · {fmtMs(solveMs(b))} per solve
                </>
              }
            />
          );
        })
      }
    </Dropdown>
  );
}
