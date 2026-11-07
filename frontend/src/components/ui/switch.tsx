import { Switch as S } from "radix-ui";

import { cn } from "@/lib/utils";

export function Switch({ className, ...p }: S.SwitchProps) {
  return (
    <S.Root
      className={cn("h-5 w-9 cursor-pointer rounded-full border border-line bg-soft data-[state=checked]:bg-ok", className)}
      {...p}
    >
      <S.Thumb className="block h-4 w-4 translate-x-0.5 rounded-full bg-surface data-[state=checked]:translate-x-[18px]" />
    </S.Root>
  );
}
