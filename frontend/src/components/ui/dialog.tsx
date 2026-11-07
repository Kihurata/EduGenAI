import { Dialog as D } from "radix-ui";
import type { ReactNode } from "react";

export const Dialog = D.Root;
export const DialogTrigger = D.Trigger;
export const DialogClose = D.Close;

export function DialogContent({ title, children }: Readonly<{ title: string; children: ReactNode }>) {
  return (
    <D.Portal>
      <D.Overlay className="fixed inset-0 z-40 bg-ink/30" />
      <D.Content className="fixed left-1/2 top-1/2 z-50 w-[min(32rem,92vw)] -translate-x-1/2 -translate-y-1/2 rounded-sm border border-line bg-surface p-5 font-sans text-ink">
        <D.Title className="mb-3 text-base font-semibold">{title}</D.Title>
        <D.Description className="sr-only">{title}</D.Description>
        {children}
      </D.Content>
    </D.Portal>
  );
}
