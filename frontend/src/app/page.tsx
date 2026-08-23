"use client";

import { AgentPanel } from "@/components/panels/AgentPanel";
import { ComponentTree } from "@/components/panels/ComponentTree";
import { ResultsDock } from "@/components/panels/ResultsDock";
import { SpecPanel } from "@/components/panels/SpecPanel";
import { TopBar } from "@/components/panels/TopBar";
import { Viewport } from "@/components/viewer/Viewport";
import { DockResizer } from "@/components/panels/DockResizer";
import { useApp } from "@/lib/store";
import { useEffect } from "react";

/**
 * Three zones, ordered the way the work actually flows: what you asked for,
 * the device it happens inside, what came back.
 *
 * The device is the centre and it is never crowded out — it is the artifact
 * the whole tool exists to change, and the evidence only makes sense against
 * it. The dock underneath holds results, so it appears when there are results
 * and takes no space before then; an empty panel with placeholder text is a
 * third of the screen spent saying "nothing here yet".
 */
export default function Home() {
  const hasResults = useApp((s) => Object.keys(s.results).length > 0);
  const running = useApp((s) => s.running);
  const loadDefaultDevice = useApp((s) => s.loadDefaultDevice);
  const dockTab = useApp((s) => s.dockTab);
  const dockHeight = useApp((s) => s.dockHeight);
  const setDockHeight = useApp((s) => s.setDockHeight);

  // The device the solver will read, adopted before anything is asked of it.
  useEffect(() => {
    void loadDefaultDevice();
  }, [loadDefaultDevice]);

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-ink-950 text-fg">
      <TopBar />

      <div className="flex min-h-0 flex-1">
        {/* The brief: what this engineer is asking for. */}
        <aside className="flex w-[300px] shrink-0 flex-col overflow-y-auto border-r border-ink-800">
          <SpecPanel />
          <ComponentTree />
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

        {/* The agent's work. */}
        <aside className="w-[380px] shrink-0 border-l border-ink-800">
          <AgentPanel />
        </aside>
      </div>
    </div>
  );
}
