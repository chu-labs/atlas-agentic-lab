import { useMemo, useState } from "react";

export interface Column<T> {
  key: string;
  title: React.ReactNode;
  render: (row: T) => React.ReactNode;
  sort?: (row: T) => string | number | null | undefined;
  align?: "left" | "right" | "center";
  width?: string;
  mono?: boolean;
  className?: string;
  defaultDesc?: boolean;
}

/** Sortable, sticky-header, zebra table. Numbers right-aligned, keys mono, rows clickable. */
export function DataTable<T>({
  rows,
  columns,
  rowKey,
  onRowClick,
  selectedKey,
  defaultSort,
  emptyText = "nothing to show",
  dense = false,
  rowClass,
  maxHeight,
}: {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  selectedKey?: string | null;
  defaultSort?: { key: string; desc?: boolean };
  emptyText?: string;
  dense?: boolean;
  rowClass?: (row: T) => string;
  maxHeight?: number | string;
}) {
  const [sort, setSort] = useState<{ key: string; desc: boolean } | null>(defaultSort ? { key: defaultSort.key, desc: !!defaultSort.desc } : null);
  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sort) return rows;
    const s = col.sort;
    return rows
      .map((r, i) => ({ r, i }))
      .sort((a, b) => {
        const x = s(a.r);
        const y = s(b.r);
        if (x == null && y == null) return a.i - b.i;
        if (x == null) return 1;
        if (y == null) return -1;
        const c = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
        return (sort.desc ? -c : c) || a.i - b.i;
      })
      .map((x) => x.r);
  }, [rows, sort, columns]);
  const toggle = (c: Column<T>) => {
    if (!c.sort) return;
    setSort((s) => (s?.key === c.key ? { key: c.key, desc: !s.desc } : { key: c.key, desc: !!c.defaultDesc }));
  };
  return (
    <div className={`dt-wrap ${dense ? "dt-dense" : ""}`} style={maxHeight != null ? { maxHeight } : undefined}>
      <table className="dt">
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                className={`${c.align ? `al-${c.align}` : ""} ${c.sort ? "sortable" : ""} ${sort?.key === c.key ? (sort.desc ? "sorted-desc" : "sorted-asc") : ""}`}
                style={c.width ? { width: c.width } : undefined}
                onClick={() => toggle(c)}
              >
                {c.title}
                {c.sort && <span className="sort-ico">{sort?.key === c.key ? (sort.desc ? "▾" : "▴") : "⇅"}</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => {
            const k = rowKey(r);
            return (
              <tr key={k} className={`${onRowClick ? "clickable" : ""} ${selectedKey === k ? "on" : ""} ${rowClass?.(r) ?? ""}`} onClick={onRowClick ? () => onRowClick(r) : undefined}>
                {columns.map((c) => (
                  <td key={c.key} className={`${c.align ? `al-${c.align}` : ""} ${c.mono ? "mono" : ""} ${c.className ?? ""}`}>
                    {c.render(r)}
                  </td>
                ))}
              </tr>
            );
          })}
          {sorted.length === 0 && (
            <tr className="dt-empty">
              <td colSpan={columns.length}>{emptyText}</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
