"use client";

import { useMemo } from "react";
import { useApp } from "@/lib/store";
import type { Candidate } from "@/lib/types";

/**
 * "Chosen" shows one placement per band (the agent's pick, or the best so
 * far while it runs); "All for band" shows every candidate for one band so
 * the ranking is inspectable. Until the first result lands, the proposal
 * with the best prior per band stands in, so the viewer is never empty.
 */
export function useVisibleCandidates(): Candidate[] {
  const candidates = useApp((s) => s.candidates);
  const placements = useApp((s) => s.placements);
  const viewMode = useApp((s) => s.viewMode);
  const focusBand = useApp((s) => s.focusBand);

  return useMemo(() => {
    if (viewMode === "focus" && focusBand) {
      return candidates.filter((c) => c.band_id === focusBand);
    }
    const placed = Object.values(placements);
    if (placed.length) return candidates.filter((c) => placed.includes(c.candidate_id));
    const best = new Map<string, Candidate>();
    for (const c of candidates) {
      const cur = best.get(c.band_id);
      if (!cur || c.prior > cur.prior) best.set(c.band_id, c);
    }
    return [...best.values()];
  }, [candidates, placements, viewMode, focusBand]);
}

export function useBandMap() {
  const bands = useApp((s) => s.spec.requirements.bands);
  return useMemo(() => {
    const m: Record<string, (typeof bands)[number]> = {};
    for (const b of bands) m[b.id] = b;
    return m;
  }, [bands]);
}
