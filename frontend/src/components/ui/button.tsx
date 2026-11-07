import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const variants = cva(
  "inline-flex h-9 cursor-pointer items-center justify-center gap-2 rounded-sm border px-3 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "border-accent bg-accent text-surface",
        outline: "border-line bg-surface text-ink",
        ghost: "border-transparent bg-transparent text-ink",
        danger: "border-son bg-son text-surface",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export function Button({ className, variant, ...p }: ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof variants>) {
  return <button className={cn(variants({ variant }), className)} {...p} />;
}
