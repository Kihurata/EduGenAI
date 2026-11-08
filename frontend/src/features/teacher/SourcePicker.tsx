import { Chip, type ChipTone } from "@/components/Chip";
import { cn } from "@/lib/utils";
import type { BankReview, Exam, ExamSource } from "@/types";

export const SOURCE_LABEL: Record<ExamSource, string> = {
  school: "Dữ liệu của trường",
  personal: "Bộ sưu tập cá nhân",
};

const OPTIONS: { value: ExamSource; hint: string }[] = [
  { value: "school", hint: "SGK và đề chung của trường. Duyệt xong, đề được gửi vào ngân hàng đề để quản trị viên xét chọn." },
  { value: "personal", hint: "Thêm đề mẫu bạn tự tải lên. Duyệt xong, đề được lưu vào bộ sưu tập riêng của bạn." },
];

/** Chọn nguồn dữ liệu sinh đề (radio dạng thẻ); nằm ngay trên ô tên đề và nút Sinh đề. */
export function SourcePicker({ value, onChange }: Readonly<{ value: ExamSource; onChange: (v: ExamSource) => void }>) {
  return (
    <fieldset className="w-full">
      <legend className="mb-1.5 text-xs text-muted">Nguồn dữ liệu sinh đề</legend>
      <div className="grid gap-2 sm:grid-cols-2" role="radiogroup">
        {OPTIONS.map((o) => {
          const active = value === o.value;
          return (
            <label
              key={o.value}
              className={cn(
                "flex cursor-pointer gap-2.5 rounded-sm border px-3 py-2 transition-colors",
                active ? "border-accent bg-soft" : "border-line hover:bg-soft",
              )}
            >
              <input
                type="radio"
                name="exam-source"
                value={o.value}
                checked={active}
                onChange={() => onChange(o.value)}
                className="mt-0.5 accent-[var(--color-accent)]"
              />
              <span>
                <span className={cn("block text-sm font-medium", active ? "text-ink" : "text-muted")}>{SOURCE_LABEL[o.value]}</span>
                <span className="block text-xs text-muted">{o.hint}</span>
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

export const REVIEW: Record<BankReview, { label: string; tone: ChipTone }> = {
  pending: { label: "Chờ quản trị viên xét", tone: "warn" },
  accepted: { label: "Đề chính thức", tone: "ok" },
  rejected: { label: "Không được chọn", tone: "bad" },
};

/** Đề đi đâu sau khi duyệt: chip nguồn + trạng thái xét (đề trường) hoặc "Trong bộ sưu tập" (đề cá nhân). */
export function DestinationChip({ exam }: Readonly<{ exam: Pick<Exam, "source" | "status" | "review_status"> }>) {
  if (exam.source === "personal") {
    return <Chip tone="accent">{exam.status === "approved" ? "Trong bộ sưu tập" : "Bộ sưu tập cá nhân"}</Chip>;
  }
  if (exam.review_status) return <Chip tone={REVIEW[exam.review_status].tone}>{REVIEW[exam.review_status].label}</Chip>;
  return <Chip tone="muted">Nguồn trường</Chip>;
}
