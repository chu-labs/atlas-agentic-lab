import { useMemo, useState, type ReactNode } from "react";

export type Column<T> = {
  key: string;
  title: ReactNode;
  width?: string;
  align?: "left" | "right" | "center";
  mono?: boolean;
  sortValue?: (row: T) => string | number | null;
  render: (row: T) => ReactNode;
};

export type Sort = { key: string; dir: "asc" | "desc" };

/** Dense sortable table: 32px rows, sticky header, right-aligned numerics. */
export function DataTable<T>({
  rows,
  columns,
  rowKey,
  initialSort,
  onRowClick,
  empty = "Nothing to show",
  className = "",
}: {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  initialSort?: Sort;
  onRowClick?: (row: T) => void;
  empty?: ReactNode;
  className?: string;
}) {
  const [sort, setSort] = useState<Sort | null>(initialSort ?? null);
  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sortValue) return rows;
    const sv = col.sortValue;
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const va = sv(a);
      const vb = sv(b);
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
      return String(va).localeCompare(String(vb), undefined, { numeric: true }) * dir;
    });
  }, [rows, sort, columns]);

  const toggle = (c: Column<T>) => {
    if (!c.sortValue) return;
    setSort((s) => (s?.key === c.key ? { key: c.key, dir: s.dir === "asc" ? "desc" : "asc" } : { key: c.key, dir: "asc" }));
  };

  return (
    <div className={`datatable-wrap ${className}`}>
      <table className="datatable">
        <colgroup>
          {columns.map((c) => (
            <col key={c.key} style={{ width: c.width }} />
          ))}
        </colgroup>
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                className={`${c.align ? `align-${c.align}` : ""} ${c.sortValue ? "sortable" : ""} ${sort?.key === c.key ? `sorted-${sort.dir}` : ""}`}
                onClick={() => toggle(c)}
                aria-sort={sort?.key === c.key ? (sort.dir === "asc" ? "ascending" : "descending") : undefined}
              >
                <span>{c.title}</span>
                {c.sortValue && <span className="sort-ind">{sort?.key === c.key ? (sort.dir === "asc" ? "▲" : "▼") : "⇅"}</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.length === 0 && (
            <tr>
              <td className="empty" colSpan={columns.length}>
                {empty}
              </td>
            </tr>
          )}
          {sorted.map((r) => (
            <tr key={rowKey(r)} className={onRowClick ? "clickable" : ""} onClick={onRowClick ? () => onRowClick(r) : undefined}>
              {columns.map((c) => (
                <td key={c.key} className={`${c.align ? `align-${c.align}` : ""} ${c.mono ? "mono" : ""}`}>
                  {c.render(r)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
