"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

/** Section heading for the inspector. */
export function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-fg-faint">
      {children}
    </h2>
  );
}

export function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 16 16"
      width={12}
      height={12}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={`shrink-0 transition-transform duration-150 ${open ? "rotate-90" : ""}`}
    >
      <path d="M6 3.5 10.5 8 6 12.5" />
    </svg>
  );
}

export function ChevronDown() {
  return (
    <svg viewBox="0 0 16 16" width={12} height={12} fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 6.5 8 10.5 12 6.5" />
    </svg>
  );
}

export function Check() {
  return (
    <svg viewBox="0 0 16 16" width={12} height={12} fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 8.5 6.5 12 13 4.5" />
    </svg>
  );
}

/**
 * A small labelled button that opens a menu beneath it, the way a model is
 * picked under a chat box. Closes on outside click and Escape. The caller
 * owns the items; `close` is handed to them for single-select menus.
 *
 * The menu is portalled to <body> and positioned from the button's rect:
 * the spec box it lives in is overflow-hidden (it has to be, to resize),
 * and a menu inside it would be clipped at the box's edge.
 */
export function Dropdown({
  label,
  title,
  ariaLabel,
  disabled,
  width = 288,
  children,
}: {
  label: React.ReactNode;
  title?: string;
  ariaLabel: string;
  disabled?: boolean;
  width?: number;
  children: (close: () => void) => React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLUListElement>(null);

  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const r = btnRef.current?.getBoundingClientRect();
      if (!r) return;
      const left = Math.min(r.left, window.innerWidth - width - 8);
      setPos({ top: r.bottom + 6, left: Math.max(8, left) });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open, width]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!btnRef.current?.contains(t) && !menuRef.current?.contains(t)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        title={title}
        className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[12px] text-fg-muted transition hover:bg-ink-850 hover:text-fg disabled:cursor-not-allowed disabled:hover:bg-transparent"
      >
        {label}
        <ChevronDown />
      </button>
      {open &&
        pos &&
        createPortal(
          <ul
            ref={menuRef}
            role="listbox"
            aria-label={ariaLabel}
            style={{ top: pos.top, left: pos.left, width }}
            className="fixed z-50 rounded-lg border border-ink-700 bg-ink-900 p-1 shadow-[0_12px_32px_rgba(0,0,0,0.5)]"
          >
            {children(() => setOpen(false))}
          </ul>,
          document.body,
        )}
    </>
  );
}

/** One row of a Dropdown: a name, an optional meta line, a check when on. */
export function MenuItem({
  on,
  onClick,
  leading,
  name,
  trailing,
  meta,
}: {
  on: boolean;
  onClick: () => void;
  leading?: React.ReactNode;
  name: React.ReactNode;
  trailing?: React.ReactNode;
  meta?: React.ReactNode;
}) {
  return (
    <li role="option" aria-selected={on}>
      <button
        type="button"
        onClick={onClick}
        className={`flex w-full flex-col rounded-md px-2.5 py-2 text-left transition ${
          on ? "bg-ink-850" : "hover:bg-ink-850"
        }`}
      >
        <span className="flex w-full items-center gap-2 text-[12.5px] text-fg">
          {leading}
          <span className="min-w-0 flex-1 truncate">{name}</span>
          {trailing && <span className="shrink-0 font-mono text-[11px] text-fg-muted">{trailing}</span>}
          <span className={`w-3 shrink-0 text-accent ${on ? "" : "invisible"}`}>
            <Check />
          </span>
        </span>
        {meta && <span className="mt-0.5 text-[11px] leading-4 text-fg-muted">{meta}</span>}
      </button>
    </li>
  );
}
