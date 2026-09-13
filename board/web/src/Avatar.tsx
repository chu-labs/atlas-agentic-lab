import type { UserSummary } from "./types";

export function Avatar({ user, size = 44 }: { user: UserSummary | null; size?: number }) {
  if (!user) {
    return (
      <span className="avatar avatar-empty" style={{ width: size, height: size, fontSize: size * 0.45 }} title="Unassigned">
        ?
      </span>
    );
  }
  return (
    <span
      className="avatar"
      style={{ width: size, height: size, fontSize: size * 0.52, background: user.color }}
      title={`${user.display_name}${user.kind === "agent" ? " (agent)" : ""}`}
    >
      {user.avatar}
    </span>
  );
}

export function Who({ user, size = 44, tag = true }: { user: UserSummary | null; size?: number; tag?: boolean }) {
  return (
    <span className="who">
      <Avatar user={user} size={size} />
      <span className="who-text">
        <span className="who-name">{user ? user.display_name : "Unassigned"}</span>
        {tag && user?.kind === "agent" && <span className="agent-tag">agent{user.mode ? ` · ${user.mode}` : ""}</span>}
      </span>
    </span>
  );
}
