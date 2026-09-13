import { marked } from "marked";

marked.setOptions({ gfm: true, breaks: true });

export function render(md: string | null | undefined): string {
  if (!md) return "";
  return marked.parse(md, { async: false }) as string;
}
