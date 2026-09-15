import { AVATARS } from "../avatars";
import type { UserSummary } from "../types";

/** DiceBear face when the handle is known at build time; initials on the user's colour otherwise. */
export function Avatar({ user, size = 24, className = "" }: { user: UserSummary | null | undefined; size?: number; className?: string }) {
  const style = { width: size, height: size };
  if (!user) {
    return <span className={`avatar avatar-empty ${className}`} style={style} title="Unassigned" aria-label="Unassigned" />;
  }
  const src = AVATARS[user.handle];
  const title = `${user.display_name}${user.kind === "agent" ? ` · agent` : ""}`;
  if (src) return <img className={`avatar ${className}`} style={style} src={src} alt={title} title={title} draggable={false} />;
  return (
    <span className={`avatar avatar-initials ${className}`} style={{ ...style, background: user.color, fontSize: size * 0.42 }} title={title}>
      {user.display_name.slice(0, 2).toUpperCase()}
    </span>
  );
}

export function AgentTag({ user, className = "" }: { user: UserSummary | null | undefined; className?: string }) {
  if (!user || user.kind !== "agent") return null;
  return <span className={`agent-tag ${className}`}>agent{user.mode ? ` · ${user.mode}` : ""}</span>;
}

export function Who({ user, size = 24, tag = false }: { user: UserSummary | null | undefined; size?: number; tag?: boolean }) {
  return (
    <span className="who">
      <Avatar user={user} size={size} />
      <span className="who-text">
        <span className="who-name">{user ? user.display_name : "Unassigned"}</span>
        {tag && <AgentTag user={user} />}
      </span>
    </span>
  );
}
