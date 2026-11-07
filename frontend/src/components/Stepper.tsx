import { Link } from "react-router-dom";

import { cn } from "@/lib/utils";

export interface Step {
  label: string;
  to?: string;
}

/** `current` is a 0-based index; earlier steps are shown as done. A step with `to` is a link. */
export function Stepper({ steps, current }: Readonly<{ steps: Step[]; current: number }>) {
  return (
    <ol className="mb-6 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm" aria-label="Các bước">
      {steps.map((s, i) => {
        const cls = cn(i === current ? "font-semibold text-accent" : i < current ? "text-ok" : "text-muted");
        return (
          <li key={s.label} className="flex items-center gap-2" aria-current={i === current ? "step" : undefined}>
            <span className={cn("flex h-5 w-5 items-center justify-center rounded-full border text-xs", i === current ? "border-accent" : "border-line")}>
              {i + 1}
            </span>
            {s.to ? <Link to={s.to} className={cls}>{s.label}</Link> : <span className={cls}>{s.label}</span>}
            {i < steps.length - 1 && <span className="h-px w-6 bg-line" />}
          </li>
        );
      })}
    </ol>
  );
}

export const TEACHER_STEPS: Step[] = [
  { label: "Ma trận", to: "/matrices" },
  { label: "Kiểm tra" },
  { label: "Sinh đề", to: "/exams" },
  { label: "Duyệt" },
  { label: "Xuất" },
];

export const GRADING_STEPS: Step[] = [
  { label: "Lớp", to: "/classes" },
  { label: "Phiếu", to: "/sheets" },
  { label: "Quét", to: "/scans" },
  { label: "Soát" },
  { label: "Kết quả", to: "/results" },
];
