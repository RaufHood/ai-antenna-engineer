"use client";

import { useMemo } from "react";
import { useApp } from "@/lib/store";
import type { Candidate } from "@/lib/types";

/**
 * System view shows the chosen placement per band; focus view shows every
 * candidate for the focused band so the ranking is inspectable.
 */
export function useVisibleCandidates(): Candidate[] {
  const candidates = useApp((s) => s.candidates);
  const placements = useApp((s) => s.placements);
  const enabledBands = useApp((s) => s.enabledBands);
  const viewMode = useApp((s) => s.viewMode);
  const focusBand = useApp((s) => s.focusBand);

  return useMemo(() => {
    if (viewMode === "focus" && focusBand) {
      return candidates.filter((c) => c.band_id === focusBand);
    }
    const placed = Object.values(placements);
    if (placed.length) {
      return candidates.filter((c) => placed.includes(c.candidate_id));
    }
    // Before a run, preview the best prior per band.
    return enabledBands
      .map((b) =>
        candidates
          .filter((c) => c.band_id === b)
          .sort((x, y) => y.prior - x.prior)[0],
      )
      .filter(Boolean);
  }, [candidates, placements, enabledBands, viewMode, focusBand]);
}

export function useBandColor() {
  const bands = useApp((s) => s.spec.requirements.bands);
  return useMemo(() => {
    const m: Record<string, string> = {};
    for (const b of bands) m[b.id] = b.color;
    return m;
  }, [bands]);
}

export function useBandMap() {
  const bands = useApp((s) => s.spec.requirements.bands);
  return useMemo(() => {
    const m: Record<string, (typeof bands)[number]> = {};
    for (const b of bands) m[b.id] = b;
    return m;
  }, [bands]);
}
