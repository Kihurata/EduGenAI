import { PrototypeBanner } from "@/components/PrototypeBanner";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ErrorState } from "@/components/states";
import { GRADING_STEPS, Stepper } from "@/components/Stepper";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import { fixAnswer, getScan, getScans, nextReviewable, QUESTION_COUNT, setReview } from "./mock";
import type { Letter, OcrAnswer } from "./types";
import { Gate, useLoad } from "./useLoad";

const flagCls = { ok: "border-line", doubtful: "border-warn", blank: "border-bad" } as const;
const flagText = { ok: "", doubtful: "Không chắc", blank: "Bỏ trống" } as const;

/** Placeholder for the scanned image: a bubble grid, filled where an answer was read. */
function ScanImage({ answers }: Readonly<{ answers: OcrAnswer[] }>) {
  return (
    <div className="aspect-[210/297] w-full max-w-xs border border-line bg-soft p-4 overflow-hidden" role="img" aria-label="Ảnh phiếu quét (minh hoạ)">
      <div className="grid grid-cols-2 gap-x-2 gap-y-2">
        {answers.map((a) => (
          <div key={a.q} className="flex items-center gap-1 text-[10px]">
            <span className="w-4 text-right text-muted">{a.q}</span>
            {["A", "B", "C", "D"].map((l) => (
              <span key={l} className={cn("h-3.5 w-3.5 rounded-full border border-ink", a.value === l && "bg-ink")} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export function ReviewPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { data, error, loading, reload } = useLoad(() => getScan(id), [id]);
  const [busy, setBusy] = useState(false);

  const finish = async (review: "confirmed" | "skipped") => {
    setBusy(true);
    await setReview(id, review);
    const next = nextReviewable(await getScans(), id);
    setBusy(false);
    navigate(next ? `/scans/${next.id}/review` : "/results");
  };
  const fix = async (q: number, v: Letter) => {
    await fixAnswer(id, q, v);
    reload();
  };

  return (
    <section>
      <PrototypeBanner />
      <Stepper steps={GRADING_STEPS} current={3} />
      <h1 className="mb-4 text-xl font-semibold">Soát kết quả đọc{data ? ` · ${data.studentName}` : ""}</h1>
      <Gate loading={loading} error={error} reload={reload} hasData={!!data} />
      {!loading && !error && !data && (
        <>
          <ErrorState message="Không tìm thấy phiếu quét này." />
          <p className="mt-3 text-center"><Link to="/scans" className="text-accent underline">Về Tải ảnh quét</Link></p>
        </>
      )}
      {data && data.status !== "received" && (
        <ErrorState message="Phiếu này chưa đọc xong hoặc ảnh bị mờ, chưa thể soát." />
      )}
      {data && data.status !== "received" && (
        <p className="mt-3 text-center"><Link to="/scans" className="text-accent underline">Về Tải ảnh quét</Link></p>
      )}
      {data && data.status === "received" && (
        <>
          <div className="grid gap-8 md:grid-cols-[20rem_1fr]">
            <ScanImage answers={data.answers} />
            <ul>
              {data.answers.slice(0, QUESTION_COUNT).map((a) => (
                <li key={a.q} className={cn("mb-1 flex items-center gap-3 border px-3 py-1.5 text-sm", flagCls[a.flag])}>
                  <span className="w-14 text-muted">Câu {a.q}</span>
                  <Select
                    aria-label={`Đáp án câu ${a.q}`}
                    className="h-8 w-24"
                    value={a.value ?? ""}
                    onChange={(e) => void fix(a.q, e.target.value as Letter)}
                  >
                    <option value="" disabled>—</option>
                    {["A", "B", "C", "D"].map((l) => <option key={l} value={l}>{l}</option>)}
                  </Select>
                  <span className="text-muted">{Math.round(a.confidence * 100)}%</span>
                  <span className={cn("text-xs", a.flag === "blank" ? "text-bad" : "text-warn")}>{flagText[a.flag]}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="mt-6 flex items-center gap-3">
            <Button disabled={busy} onClick={() => void finish("confirmed")}>Xác nhận phiếu</Button>
            <Button variant="outline" disabled={busy} onClick={() => void finish("skipped")}>Bỏ qua phiếu</Button>
            <Link to="/scans" className="text-sm text-accent underline">Về danh sách quét</Link>
          </div>
        </>
      )}
    </section>
  );
}
