"use client";

import { sizeOf } from "@/lib/geometry";
import { useApp } from "@/lib/store";
import { SectionTitle } from "./SpecPanel";

const EM_LABEL: Record<string, string> = {
  pec: "PEC",
  lossy_metal: "lossy metal",
  dielectric: "dielectric",
  air: "air",
};

/** The device's parts as the solver sees them: hover/select/hide drive the viewer. */
export function ComponentTree() {
  const components = useApp((s) => s.spec.components);
  const hidden = useApp((s) => s.hidden);
  const selected = useApp((s) => s.selectedComponent);
  const toggleHidden = useApp((s) => s.toggleHidden);
  const selectComponent = useApp((s) => s.selectComponent);
  const hoverComponent = useApp((s) => s.hoverComponent);
  const isolateComponent = useApp((s) => s.isolateComponent);

  return (
    <section className="px-4 py-3">
      <div className="mb-2 flex items-center justify-between">
        <SectionTitle>Components</SectionTitle>
        {hidden.length > 0 && (
          <button
            onClick={() => isolateComponent(null)}
            className="text-[11px] text-sky-400 hover:text-sky-300"
          >
            show all
          </button>
        )}
      </div>

      <ul className="-mx-2">
        {components.map((c) => {
          const isHidden = hidden.includes(c.name);
          const isSel = selected === c.name;
          const s = sizeOf(c.bbox_mm);
          return (
            <li key={c.name}>
              <div
                onMouseEnter={() => hoverComponent(c.name)}
                onMouseLeave={() => hoverComponent(null)}
                onClick={() => selectComponent(isSel ? null : c.name)}
                className={`group flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-xs transition ${
                  isSel ? "bg-sky-500/10" : "hover:bg-slate-800/50"
                }`}
              >
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-sm ring-1 ring-white/15"
                  style={{ background: c.color, opacity: isHidden ? 0.3 : 1 }}
                />
                <span className={`truncate ${isHidden ? "text-slate-600" : "text-slate-200"}`}>
                  {c.label}
                </span>
                <span className="ml-auto shrink-0 font-mono text-[9px] text-slate-600">
                  {EM_LABEL[c.em]}
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleHidden(c.name);
                  }}
                  className={`w-7 shrink-0 text-right text-[10px] transition ${
                    isHidden
                      ? "text-slate-600 hover:text-slate-300"
                      : "text-slate-700 opacity-0 hover:text-slate-300 group-hover:opacity-100"
                  }`}
                  title={isHidden ? "show" : "hide"}
                >
                  {isHidden ? "show" : "hide"}
                </button>
              </div>
              {isSel && (
                <div className="mx-2 mb-1 space-y-0.5 rounded-md bg-slate-900/60 px-2.5 py-2 font-mono text-[10px] text-slate-400">
                  <div>
                    <span className="text-slate-600">node </span>
                    {c.name}
                  </div>
                  <div>
                    <span className="text-slate-600">size </span>
                    {s.map((v) => v.toFixed(1)).join(" × ")} mm
                  </div>
                  <div>
                    <span className="text-slate-600">origin </span>
                    {c.bbox_mm[0].map((v) => v.toFixed(1)).join(", ")} mm
                  </div>
                  {c.em === "dielectric" && (
                    <div>
                      <span className="text-slate-600">εr </span>
                      {c.epsilon_r}
                      <span className="text-slate-600"> · tan δ </span>
                      {c.loss_tangent}
                    </div>
                  )}
                  <button
                    onClick={() => isolateComponent(c.name)}
                    className="mt-1 text-sky-400 hover:text-sky-300"
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
