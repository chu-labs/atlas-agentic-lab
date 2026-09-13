import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export interface PopoverItem {
  key: string;
  label: string;
  icon?: React.ReactNode;
  meta?: React.ReactNode;
  group?: string;
  onPick: () => void;
}

/**
 * A menu rendered in a portal, position: fixed, anchored to a trigger and flipped above it when
 * there is no room below. Closes on outside click, Escape or any scroll. Arrow keys move, Enter picks.
 */
export function Popover({ anchor, items, onClose }: { anchor: HTMLElement; items: PopoverItem[]; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number; up: boolean; maxHeight: number } | null>(null);
  const [active, setActive] = useState(0);

  useLayoutEffect(() => {
    const place = () => {
      const r = anchor.getBoundingClientRect();
      const M = 8; // never closer than this to a viewport edge
      const natural = ref.current?.scrollHeight ?? 320;
      const w = ref.current?.offsetWidth ?? 280;
      const below = window.innerHeight - r.bottom - 6 - M;
      const above = r.top - 6 - M;
      let up = false;
      let maxHeight = natural;
      let top: number;
      if (natural <= below) {
        top = r.bottom + 6;
      } else if (natural <= above) {
        up = true;
        top = r.top - 6 - natural;
      } else {
        // neither side fits: pin inside the viewport on the roomier side and scroll internally
        up = above > below;
        maxHeight = Math.max(120, up ? above : below);
        top = up ? Math.max(M, r.top - 6 - maxHeight) : r.bottom + 6;
      }
      top = Math.max(M, Math.min(top, window.innerHeight - M - Math.min(natural, maxHeight)));
      const left = Math.max(M, Math.min(r.left, window.innerWidth - w - M));
      setPos({ top, left, up, maxHeight });
    };
    place();
    const id = requestAnimationFrame(place);
    return () => cancelAnimationFrame(id);
  }, [anchor, items.length]);

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node) && !anchor.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        anchor.focus();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setActive((a) => (a + 1) % items.length);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActive((a) => (a - 1 + items.length) % items.length);
      } else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        items[active]?.onPick();
        onClose();
      } else if (e.key === "Tab") {
        onClose();
      }
    };
    const onScroll = (e: Event) => {
      if (ref.current && e.target instanceof Node && ref.current.contains(e.target)) return; // scrolling the menu itself
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
      className={`popover ${pos?.up ? "popover-up" : ""}`}
      role="menu"
      style={{ top: pos?.top ?? -9999, left: pos?.left ?? -9999, maxHeight: pos?.maxHeight, visibility: pos ? "visible" : "hidden" }}
      onMouseDown={(e) => e.stopPropagation()}
    >
      {items.map((it, i) => {
        const header = it.group && it.group !== lastGroup ? <div className="assign-group">{it.group}</div> : null;
        lastGroup = it.group;
        return (
          <div key={it.key}>
            {header}
            <button
              role="menuitem"
              data-idx={i}
              className={`assign-item ${i === active ? "active" : ""}`}
              onMouseEnter={() => setActive(i)}
              onClick={(e) => {
                e.stopPropagation();
                it.onPick();
                onClose();
              }}
            >
              {it.icon}
              <span>{it.label}</span>
              {it.meta}
            </button>
          </div>
        );
      })}
    </div>,
    document.body,
  );
}
