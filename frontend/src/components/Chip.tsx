import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

const tones = {
  ok: "border-ok text-ok",
  warn: "border-warn text-warn",
  bad: "border-bad text-bad",
  muted: "border-line text-muted",
  accent: "border-accent text-accent",
};

export type ChipTone = keyof typeof tones;

export function Chip({ tone = "muted", children }: Readonly<{ tone?: ChipTone; children: ReactNode }>) {
  return <span className={cn("inline-flex items-center rounded-sm border px-2 py-0.5 text-xs font-medium", tones[tone])}>{children}</span>;
}
