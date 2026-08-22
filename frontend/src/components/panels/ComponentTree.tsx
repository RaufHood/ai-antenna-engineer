"use client";

import { sizeOf } from "@/lib/geometry";
import { useApp } from "@/lib/store";

const EM_LABEL: Record<string, string> = {
  pec: "PEC",
  lossy_metal: "lossy metal",
  dielectric: "dielectric",
  air: "air",
};

export function ComponentTree() {
  const spec = useApp((s) => s.spec);
  const hidden = useApp((s) => s.hidden);
  const selected = useApp((s) => s.selectedComponent);
  const toggleHidden = useApp((s) => s.toggleHidden);
  const selectComponent = useApp((s) => s.selectComponent);
  const hoverComponent = useApp((s) => s.hoverComponent);
  const isolateComponent = useApp((s) => s.isolateComponent);

  return (
    <section className="border-b border-slate-800">
      <header className="flex items-center justify-between px-3 py-2">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Components
        </h2>
        <button
          onClick={() => isolateComponent(null)}
          className="text-[10px] text-slate-500 hover:text-sky-400"
        >
          show all
        </button>
      </header>

      <ul className="pb-2">
        {spec.components.map((c) => {
          const isHidden = hidden.includes(c.name);
          const isSel = selected === c.name;
          const s = sizeOf(c.bbox_mm);
          return (
            <li key={c.name}>
              <div
                onMouseEnter={() => hoverComponent(c.name)}
                onMouseLeave={() => hoverComponent(null)}
                className={`group flex cursor-pointer items-center gap-2 px-3 py-1.5 text-xs transition ${
                  isSel ? "bg-sky-500/15" : "hover:bg-slate-800/60"
                }`}
                onClick={() => selectComponent(isSel ? null : c.name)}
              >
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-sm ring-1 ring-white/20"
                  style={{ background: c.color }}
                />
                <span
                  className={`truncate ${isHidden ? "text-slate-600 line-through" : "text-slate-200"}`}
                >
                  {c.label}
                </span>
                <span className="ml-auto shrink-0 font-mono text-[9px] text-slate-500">
                  {EM_LABEL[c.em]}
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleHidden(c.name);
                  }}
                  className="shrink-0 text-[10px] text-slate-600 hover:text-sky-400"
                  title={isHidden ? "show" : "hide"}
                >
                  {isHidden ? "off" : "on"}
                </button>
              </div>
              {isSel && (
                <div className="space-y-0.5 bg-slate-900/60 px-3 py-2 font-mono text-[10px] text-slate-400">
                  <div>node: {c.name}</div>
                  <div>
                    size: {s.map((v) => v.toFixed(1)).join(" x ")} mm
                  </div>
                  <div>
                    origin: {c.bbox_mm[0].map((v) => v.toFixed(1)).join(", ")} mm
                  </div>
                  {c.em === "dielectric" && (
                    <div>
                      er {c.epsilon_r} / tan-d {c.loss_tangent}
                    </div>
                  )}
                  <button
                    onClick={() => isolateComponent(c.name)}
                    className="mt-1 rounded bg-slate-800 px-2 py-0.5 text-slate-300 hover:bg-slate-700"
                  >
                    isolate
                  </button>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
