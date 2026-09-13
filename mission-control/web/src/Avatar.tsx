import { AVATARS } from "./avatars";

const FALLBACK_EMOJI: Record<string, string> = {
  scout: "🔭",
  forge: "⚒️",
  sentinel: "🛡️",
  conductor: "🎼",
  watchtower: "🗼",
  "mission-control": "🛰️",
};

export function avatarFor(handle: string | null | undefined): string | null {
  if (!handle) return null;
  if (AVATARS[handle]) return AVATARS[handle];
  if (handle.startsWith("teammate:")) return AVATARS["teammate:tester"] ?? null;
  return null;
}

/** Illustrated avatar (DiceBear, bundled at build time). Falls back to an emoji disc for unknown handles. */
export function Avatar({
  handle,
  size = 56,
  color,
  emoji,
  title,
  className = "",
}: {
  handle: string | null | undefined;
  size?: number;
  color?: string;
  emoji?: string;
  title?: string;
  className?: string;
}) {
  const uri = avatarFor(handle);
  if (uri) {
    return <img className={`av ${className}`} src={uri} width={size} height={size} alt="" title={title ?? handle ?? ""} style={{ width: size, height: size }} />;
  }
  const glyph = emoji ?? (handle ? FALLBACK_EMOJI[handle] : undefined) ?? "•";
  return (
    <span className={`av av-emoji ${className}`} style={{ width: size, height: size, fontSize: size * 0.5, background: color ?? "#3a4666" }} title={title ?? handle ?? ""}>
      {glyph}
    </span>
  );
}
