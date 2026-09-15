/** A card with a header row: title, count chip, right-aligned actions. Body fills; no empty padding. */
export function Panel({
  title,
  count,
  sub,
  actions,
  children,
  className = "",
  span,
  scroll = false,
}: {
  title: React.ReactNode;
  count?: number | string;
  sub?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  span?: number;
  scroll?: boolean;
}) {
  return (
    <section className={`panel ${className}`} style={span ? { gridColumn: `span ${span}` } : undefined}>
      <header className="panel-head">
        <span className="panel-h">{title}</span>
        {count != null && <span className="count">{count}</span>}
        {sub && <span className="panel-s">{sub}</span>}
        {actions && <span className="panel-actions">{actions}</span>}
      </header>
      <div className={`panel-body ${scroll ? "panel-scroll" : ""}`}>{children}</div>
    </section>
  );
}

export function EmptyLine({ children }: { children: React.ReactNode }) {
  return <div className="empty-line">{children}</div>;
}
