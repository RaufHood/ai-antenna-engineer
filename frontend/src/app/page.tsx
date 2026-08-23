"use client";

import { AgentPanel } from "@/components/panels/AgentPanel";
import { ComponentTree } from "@/components/panels/ComponentTree";
import { ResultsDock } from "@/components/panels/ResultsDock";
import { ViewPanel } from "@/components/panels/ViewPanel";
import { Viewport } from "@/components/viewer/Viewport";
import { DockResizer } from "@/components/panels/DockResizer";
import { useApp } from "@/lib/store";
import { useEffect } from "react";

/**
 * Three zones. Everything decided before a run — the spec, the agent, the
 * band — on the left, where a chat lives; the device in the centre; how it
 * is drawn and what it is made of on the right, where a tool keeps its
 * inspector. The inspector is for looking, not deciding, so it can be put
 * away and the conversation takes the room.
 *
 * The device is never crowded out — it is the artifact the whole tool exists
 * to change, and the evidence only makes sense against it. The dock under it
 * holds the candidate table, the S11 sweep and the gallery: those need the
 * centre's width, a 300 px rail would turn them into stamps. It appears when
 * there are results and takes no space before then.
 */
export default function Home() {
  const hasResults = useApp((s) => Object.keys(s.results).length > 0);
  const running = useApp((s) => s.running);
  const loadDefaultDevice = useApp((s) => s.loadDefaultDevice);
  const dockTab = useApp((s) => s.dockTab);
  const dockHeight = useApp((s) => s.dockHeight);
  const setDockHeight = useApp((s) => s.setDockHeight);
  const inspectorOpen = useApp((s) => s.inspectorOpen);

  // The device the solver will read, adopted before anything is asked of it.
  useEffect(() => {
    void loadDefaultDevice();
  }, [loadDefaultDevice]);

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-ink-950 text-fg">
      <div className="flex min-h-0 flex-1">
        {/* The conversation: the spec in, the agent's reasoning out. Wider
            when the inspector is away — that is the point of hiding it. */}
        <aside
          className={`shrink-0 border-r border-ink-800 ${inspectorOpen ? "w-[400px]" : "w-[520px]"}`}
        >
          <AgentPanel />
        </aside>

        {/* The device, and the evidence read against it. */}
        <main className="flex min-w-0 flex-1 flex-col">
          <div className="min-h-0 flex-1">
            <Viewport />
          </div>
          {(hasResults || running) && (
            // The gallery earns more room than a table does: these are the
            // pictures the study exists to produce, and a 280 px rail turns
            // them into stamps.
            <div
              // Automatic until the user says otherwise: a gallery wants more
              // room than a table. Once they drag, their number wins and the
              // animation is dropped — a height that eases toward the cursor
              // feels like lag, not polish.
              className={`relative shrink-0 border-t border-ink-800 ${
                dockHeight === null ? "transition-[height] duration-200" : ""
              }`}
              style={{ height: dockHeight ?? (dockTab === "evidence" ? 440 : 280) }}
            >
              <DockResizer
                height={dockHeight ?? (dockTab === "evidence" ? 440 : 280)}
                onResize={setDockHeight}
              />
              <ResultsDock />
            </div>
          )}
        </main>

        {/* The inspector: how the device is drawn, and its parts. */}
        {inspectorOpen && (
          <aside className="flex w-[300px] shrink-0 flex-col overflow-y-auto border-l border-ink-800">
            <ViewPanel />
            <ComponentTree />
          </aside>
        )}
      </div>
    </div>
  );
}
