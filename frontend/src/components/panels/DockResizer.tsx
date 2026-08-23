"use client";

import { useCallback, useEffect, useRef } from "react";

/**
 * The grab strip along the top edge of the results dock.
 *
 * How much room the evidence deserves against how much the device deserves is
 * a judgement that changes minute to minute — reading a candidate table wants
 * rows, studying a placement map wants pixels, and the app cannot know which
 * you are doing. So it stops guessing once you say.
 *
 * Pointer capture rather than window listeners: the drag keeps following the
 * cursor when it leaves the 6 px strip, which it does immediately, and it ends
 * cleanly if the pointer is lost.
 */

export const DOCK_MIN_PX = 150;
/** Leave the device more than half the window however hard you pull. */
export const DOCK_MAX_FRACTION = 0.72;

export function clampDock(px: number, viewportH: number): number {
  return Math.round(Math.min(Math.max(px, DOCK_MIN_PX), viewportH * DOCK_MAX_FRACTION));
}

export function DockResizer({
  height,
  onResize,
}: {
  height: number;
  onResize: (px: number) => void;
}) {
  const drag = useRef<{ y: number; h: number } | null>(null);

  const move = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (!drag.current) return;
      // Dragging up grows the dock, so the delta is inverted.
      onResize(clampDock(drag.current.h + (drag.current.y - e.clientY), window.innerHeight));
    },
    [onResize],
  );

  const end = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    drag.current = null;
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  }, []);

  // A drag interrupted by a tab switch or an alt-tab must not leave the whole
  // page stuck in ns-resize with text unselectable.
  useEffect(() => {
    return () => {
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, []);

  return (
    <div
      role="separator"
      aria-orientation="horizontal"
      aria-label="Resize the results panel"
      tabIndex={0}
      onPointerDown={(e) => {
        drag.current = { y: e.clientY, h: height };
        e.currentTarget.setPointerCapture(e.pointerId);
        document.body.style.cursor = "ns-resize";
        document.body.style.userSelect = "none";
      }}
      onPointerMove={move}
      onPointerUp={end}
      onPointerCancel={end}
      onKeyDown={(e) => {
        // Keyboard parity: the same handle, in 24 px steps.
        const step = e.key === "ArrowUp" ? 24 : e.key === "ArrowDown" ? -24 : 0;
        if (!step) return;
        e.preventDefault();
        onResize(clampDock(height + step, window.innerHeight));
      }}
      className="group absolute -top-[3px] left-0 right-0 z-20 flex h-[7px] cursor-ns-resize items-center justify-center focus-visible:outline-none"
    >
      {/* The strip itself stays invisible until you approach it: a permanent
          divider handle would be a line competing with the border already
          there. */}
      <span className="h-px w-14 rounded bg-transparent transition-colors group-hover:bg-ink-600 group-focus-visible:bg-accent" />
    </div>
  );
}
