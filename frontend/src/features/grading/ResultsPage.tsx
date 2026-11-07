import { Link } from "react-router-dom";

import { PrototypeBanner } from "@/components/PrototypeBanner";
import { EmptyState } from "@/components/states";
import { GRADING_STEPS, Stepper } from "@/components/Stepper";
import { Button } from "@/components/ui/button";
import { Table, Td, Th } from "@/components/ui/table";
import { cn } from "@/lib/utils";

import { exportCsv, getResults } from "./mock";
import { Gate, useLoad } from "./useLoad";

const Stat = ({ label, value }: Readonly<{ label: string; value: string }>) => (
  <div className="border-l border-line pl-4">
    <p className="text-sm text-muted">{label}</p>
    <p className="text-2xl font-semibold">{value}</p>
  </div>
);

export function ResultsPage() {
  const { data, error, loading, reload } = useLoad(getResults, []);
  const scores = data?.rows.map((r) => r.score) ?? [];
  const fmt = (n: number) => n.toFixed(1);
  const weak = data?.topics.filter((t) => t.percentCorrect < 50) ?? [];

  return (
    <section>
      <PrototypeBanner />
      <Stepper steps={GRADING_STEPS} current={4} />
      <h1 className="mb-4 text-xl font-semibold">Kết quả và ôn tập</h1>
      <Gate loading={loading} error={error} reload={reload} hasData={!!data} />
      {data && data.rows.length === 0 && (
        <EmptyState title="Chưa có phiếu nào được xác nhận" hint="Soát và xác nhận ít nhất một phiếu để xem kết quả.">
          <Link to="/scans" className="text-accent underline">Đến Tải ảnh quét</Link>
        </EmptyState>
      )}
      {data && data.rows.length > 0 && (
        <>
          <div className="mb-6 flex gap-8">
            <Stat label="Điểm trung bình" value={fmt(scores.reduce((a, b) => a + b, 0) / scores.length)} />
            <Stat label="Cao nhất" value={fmt(Math.max(...scores))} />
            <Stat label="Thấp nhất" value={fmt(Math.min(...scores))} />
          </div>
          <div className="grid gap-8 md:grid-cols-2">
            <div>
              <div className="mb-2 flex items-center justify-between">
                <h2 className="font-medium">Điểm từng học sinh</h2>
                <Button variant="outline" onClick={() => exportCsv(data.rows)}>Xuất bảng điểm</Button>
              </div>
              <Table>
                <thead><tr><Th>Học sinh</Th><Th>Số câu đúng</Th><Th>Điểm</Th></tr></thead>
                <tbody>
                  {data.rows.map((r) => (
                    <tr key={r.scanId}><Td>{r.studentName}</Td><Td>{r.correct}/{r.total}</Td><Td>{r.score.toFixed(1)}</Td></tr>
                  ))}
                </tbody>
              </Table>
            </div>
            <div>
              <h2 className="mb-2 font-medium">Chủ đề yếu</h2>
              <ul className="space-y-3">
                {data.topics.map((t) => (
                  <li key={t.topic} className="text-sm">
                    <div className="mb-1 flex justify-between">
                      <span>{t.topic}</span>
                      <span className={cn(t.percentCorrect < 50 ? "text-bad" : "text-muted")}>{t.percentCorrect}%</span>
                    </div>
                    <div className="h-2 bg-soft">
                      <div className={cn("h-2", t.percentCorrect < 50 ? "bg-bad" : "bg-ok")} style={{ width: `${t.percentCorrect}%` }} />
                    </div>
                  </li>
                ))}
              </ul>
              <div className="mt-6 border-t border-line pt-4">
                <h2 className="font-medium">Gợi ý ôn tập</h2>
                <p className="mb-3 mt-1 text-sm text-muted">
                  {weak.length ? `Nên ôn lại: ${weak.map((t) => t.topic).join(", ")}.` : "Chưa có chủ đề nào dưới 50%. Có thể tạo đề ôn tổng hợp."}
                </p>
                {/* TODO(BE): POST /api/v1/remedial-exams (weak topics -> matrix draft)
                    req : { topics: string[] }
                    res : { matrix_id }  (proposed contract)
                    owner: Backend (Huy/Phu) · feature: Khối 2 · now: link to /matrices, no data passed */}
                <Link to="/matrices" className="inline-flex h-9 items-center rounded-sm border border-accent bg-accent px-3 text-sm font-medium text-surface">Tạo đề ôn tập</Link>
              </div>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
