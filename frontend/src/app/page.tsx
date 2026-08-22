import { AgentPanel } from "@/components/panels/AgentPanel";
import { ComponentTree } from "@/components/panels/ComponentTree";
import { ResultsDock } from "@/components/panels/ResultsDock";
import { SpecPanel } from "@/components/panels/SpecPanel";
import { TopBar } from "@/components/panels/TopBar";
import { Viewport } from "@/components/viewer/Viewport";

export default function Home() {
  return (
    <div className="flex h-screen flex-col overflow-hidden bg-slate-950 text-slate-200">
      <TopBar />
      <div className="flex min-h-0 flex-1">
        <aside className="w-72 shrink-0 overflow-y-auto border-r border-slate-800/80">
          <SpecPanel />
          <ComponentTree />
        </aside>

        <main className="flex min-w-0 flex-1 flex-col">
          <div className="min-h-0 flex-1">
            <Viewport />
          </div>
          <div className="h-[290px] shrink-0 border-t border-slate-800/80">
            <ResultsDock />
          </div>
        </main>

        <aside className="w-[360px] shrink-0 border-l border-slate-800/80">
          <AgentPanel />
        </aside>
      </div>
    </div>
  );
}
