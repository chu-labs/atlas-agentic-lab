import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

export interface PopoverItem {
  key: string;
  label: ReactNode;
  icon?: ReactNode;
  meta?: ReactNode;
  group?: string;
  active?: boolean;
  onPick: () => void;
}

/**
 * Menu in a portal, position: fixed, anchored to a trigger, flipped above when there is no room below
 * and clamped inside the viewport. Closes on outside click, Escape or scroll. Arrows move, Enter picks.
 */
export function Popover({ anchor, items, onClose, width = 260 }: { anchor: HTMLElement; items: PopoverItem[]; onClose: () => void; width?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number; maxHeight: number } | null>(null);
  const [active, setActive] = useState(Math.max(0, items.findIndex((i) => i.active)));

  useLayoutEffect(() => {
    const place = () => {
      const r = anchor.getBoundingClientRect();
      const M = 8;
      const natural = ref.current?.scrollHeight ?? 320;
      const w = ref.current?.offsetWidth ?? width;
      const below = window.innerHeight - r.bottom - 6 - M;
      const above = r.top - 6 - M;
      let maxHeight = natural;
      let top: number;
      if (natural <= below) top = r.bottom + 6;
      else if (natural <= above) top = r.top - 6 - natural;
      else {
        const up = above > below;
        maxHeight = Math.max(120, up ? above : below);
        top = up ? Math.max(M, r.top - 6 - maxHeight) : r.bottom + 6;
      }
      top = Math.max(M, Math.min(top, window.innerHeight - M - Math.min(natural, maxHeight)));
      const left = Math.max(M, Math.min(r.left, window.innerWidth - w - M));
      setPos({ top, left, maxHeight });
    };
    place();
    const id = requestAnimationFrame(place);
    return () => cancelAnimationFrame(id);
  }, [anchor, items.length, width]);

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (ref.current?.contains(e.target as Node) || anchor.contains(e.target as Node)) return;
      onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
        anchor.focus();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setActive((a) => (a + 1) % items.length);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActive((a) => (a - 1 + items.length) % items.length);
      } else if (e.key === "Enter") {
        e.preventDefault();
        items[active]?.onPick();
        onClose();
      } else if (e.key === "Tab") onClose();
    };
    const onScroll = (e: Event) => {
      if (ref.current && e.target instanceof Node && ref.current.contains(e.target)) return;
      onClose();
    };
    document.addEventListener("mousedown", onDown, true);
    document.addEventListener("keydown", onKey, true);
    document.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll);
    return () => {
      document.removeEventListener("mousedown", onDown, true);
      document.removeEventListener("keydown", onKey, true);
      document.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onScroll);
    };
  }, [anchor, items, active, onClose]);

  useEffect(() => {
    ref.current?.querySelectorAll<HTMLElement>("[data-idx]")[active]?.scrollIntoView({ block: "nearest" });
  }, [active]);

  let lastGroup: string | undefined;
  return createPortal(
    <div
      ref={ref}
      className="popover"
      role="menu"
      style={{ top: pos?.top ?? -9999, left: pos?.left ?? -9999, maxHeight: pos?.maxHeight, width, visibility: pos ? "visible" : "hidden" }}
      onMouseDown={(e) => e.stopPropagation()}
    >
      {items.map((it, i) => {
        const header = it.group && it.group !== lastGroup ? <div className="popover-group">{it.group}</div> : null;
        lastGroup = it.group;
        return (
          <div key={it.key}>
            {header}
            <button
              type="button"
              role="menuitem"
              data-idx={i}
              className={`popover-item ${i === active ? "hover" : ""} ${it.active ? "selected" : ""}`}
              onMouseEnter={() => setActive(i)}
              onClick={(e) => {
                e.stopPropagation();
                it.onPick();
                onClose();
              }}
            >
              {it.icon}
              <span className="popover-label">{it.label}</span>
              {it.meta && <span className="popover-meta">{it.meta}</span>}
            </button>
          </div>
        );
      })}
    </div>,
    document.body,
  );
}

/** Right-hand slide-in panel with a backdrop. Escape closes. */
export function Drawer({ open, title, onClose, children, width = 520 }: { open: boolean; title: ReactNode; onClose: () => void; children: ReactNode; width?: number }) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    if (!open) {
      setShown(false);
      return;
    }
    const id = requestAnimationFrame(() => setShown(true));
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => {
      cancelAnimationFrame(id);
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);
  if (!open) return null;
  return createPortal(
    <>
      <div className={`drawer-backdrop ${shown ? "on" : ""}`} onClick={onClose} />
      <aside className={`drawer ${shown ? "on" : ""}`} role="dialog" aria-modal="true" style={{ width }}>
        <header className="drawer-head">
          <h2>{title}</h2>
          <button type="button" className="btn btn-ghost btn-icon" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>
        <div className="drawer-body">{children}</div>
      </aside>
    </>,
    document.body,
  );
}
