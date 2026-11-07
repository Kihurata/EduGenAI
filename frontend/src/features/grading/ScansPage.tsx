import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Chip } from "@/components/Chip";
import { PrototypeBanner } from "@/components/PrototypeBanner";
import { EmptyState } from "@/components/states";
import { GRADING_STEPS, Stepper } from "@/components/Stepper";
import { Button } from "@/components/ui/button";
import { Table, Td, Th } from "@/components/ui/table";

import { getScans, nextReviewable, uploadScans } from "./mock";
import { Gate, useLoad } from "./useLoad";

const REVIEW_LABEL = { pending: "Chờ soát", confirmed: "Đã xác nhận", skipped: "Đã bỏ qua" } as const;

export function ScansPage() {
  // Poll so status changes made by the mock timers show up.
  const { data, error, loading, reload } = useLoad(getScans, [], 1000);
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  const add = async (files: FileList | null) => {
    if (!files?.length) return;
    await uploadScans(Array.from(files, (f) => f.name));
    reload();
  };
  const first = data ? nextReviewable(data) : undefined;

  return (
    <section>
      <PrototypeBanner />
      <Stepper steps={GRADING_STEPS} current={2} />
      <h1 className="mb-4 text-xl font-semibold">Tải ảnh quét</h1>
      {/* TODO(BE): POST /api/v1/scans (multipart) is called from uploadScans in mock.ts; see the note there. */}
      <div
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); void add(e.dataTransfer.files); }}
        className={`mb-6 border border-dashed px-6 py-10 text-center ${over ? "border-accent bg-soft" : "border-line"}`}
      >
        <p className="font-medium">Kéo thả ảnh hoặc PDF phiếu đã quét vào đây</p>
        <Button variant="outline" className="mt-3" onClick={() => input.current?.click()}>Chọn tệp</Button>
        <input ref={input} type="file" multiple accept="image/*,application/pdf" className="hidden" aria-label="Chọn tệp quét" onChange={(e) => { void add(e.target.files); e.target.value = ""; }} />
      </div>
      <Gate loading={loading} error={error} reload={reload} hasData={!!data} />
      {data && data.length === 0 && (
        <EmptyState title="Chưa có tệp nào" hint="Chưa có phiếu? Tạo phiếu trả lời trước.">
          <Link to="/sheets" className="text-accent underline">Đến Phiếu trả lời</Link>
        </EmptyState>
      )}
      {data && data.length > 0 && (
        <>
          <Table>
            <thead><tr><Th>Tệp</Th><Th>Trạng thái đọc</Th><Th>Soát</Th><Th /></tr></thead>
            <tbody>
              {data.map((s) => (
                <tr key={s.id}>
                  <Td>{s.fileName}</Td>
                  <Td>
                    {s.status === "reading" && <Chip tone="accent">Đang đọc…</Chip>}
                    {s.status === "received" && <Chip tone="ok">Đã nhận</Chip>}
                    {s.status === "blurry" && <Chip tone="bad">Ảnh mờ (chụp lại)</Chip>}
                  </Td>
                  <Td className="text-muted">{s.status === "received" ? REVIEW_LABEL[s.review] : "—"}</Td>
                  <Td>{s.status === "received" && <Link to={`/scans/${s.id}/review`} className="text-accent underline">Soát phiếu</Link>}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <div className="mt-4">
            <Button disabled={!first} onClick={() => first && navigate(`/scans/${first.id}/review`)}>Chấm các phiếu đã nhận</Button>
            {!first && <span className="ml-3 text-sm text-muted">Chưa có phiếu nào chờ soát.</span>}
          </div>
        </>
      )}
    </section>
  );
}
