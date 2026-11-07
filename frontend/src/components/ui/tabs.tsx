import { Tabs as T } from "radix-ui";

import { cn } from "@/lib/utils";

export const Tabs = T.Root;
export const TabsContent = T.Content;
export const TabsList = ({ className, ...p }: T.TabsListProps) => (
  <T.List className={cn("flex gap-4 border-b border-line", className)} {...p} />
);
export const TabsTrigger = ({ className, ...p }: T.TabsTriggerProps) => (
  <T.Trigger
    className={cn("cursor-pointer border-b-2 border-transparent pb-2 text-sm text-muted data-[state=active]:border-accent data-[state=active]:text-ink", className)}
    {...p}
  />
);
