import type { InputHTMLAttributes, SelectHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const field = "h-9 w-full rounded-sm border border-line bg-surface px-3 text-sm text-ink";

export function Input({ className, ...p }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(field, className)} {...p} />;
}

// Native select: accessible and tiny; swap for Radix Select only if a screen needs a custom menu.
export function Select({ className, ...p }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn(field, className)} {...p} />;
}
