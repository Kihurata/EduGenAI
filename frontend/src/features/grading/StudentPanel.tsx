import { useState } from "react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Table, Td, Th } from "@/components/ui/table";

import { importStudents } from "./mock";
import type { Class, ImportReport } from "./types";

function ImportDialog({ classId, onDone }: Readonly<{ classId: string; onDone: () => void }>) {
  const [text, setText] = useState("");
  const [report, setReport] = useState<ImportReport | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    const r = await importStudents(classId, text);
    setReport(r);
    setBusy(false);
    onDone();
  };

  return (
    <Dialog onOpenChange={(o) => o && setReport(null)}>
      <DialogTrigger asChild>
        <Button variant="outline">Nhập CSV</Button>
      </DialogTrigger>
      <DialogContent title="Nhập học sinh từ CSV">
        <p className="mb-2 text-sm text-muted">Cột: ma_hs,ho_ten,ngay_sinh (dòng tiêu đề không bắt buộc).</p>
        <input
          type="file"
          accept=".csv,text/csv"
          aria-label="Chọn tệp CSV"
          className="mb-2 text-sm"
          onChange={async (e) => {
            const f = e.target.files?.[0];
            if (f) setText(await f.text());
          }}
        />
        <textarea
          aria-label="Nội dung CSV"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={6}
          placeholder={"ma_hs,ho_ten,ngay_sinh\nHS010,Nguyễn Văn A,2008-01-01"}
          className="w-full rounded-sm border border-line bg-surface p-2 font-mono text-sm"
        />
        {report && (
          <div className="mt-3 text-sm" role="status">
            <p className="text-ok">Đã thêm {report.created} học sinh.</p>
            {report.errors.length > 0 && (
              <ul className="mt-1 text-bad">
                {report.errors.map((e) => (
                  <li key={e.row}>Dòng {e.row}: {e.message}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="ghost">Đóng</Button>
          </DialogClose>
          <Button onClick={run} disabled={busy || !text.trim()}>Nhập</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** Student table of one class with the CSV import action; `onChange` refreshes the parent after import. */
export function StudentPanel({ cls, onChange, withLinks }: Readonly<{ cls: Class; onChange: () => void; withLinks?: boolean }>) {
  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="font-medium">Lớp {cls.name} · {cls.students.length} học sinh</h2>
        <div className="flex gap-2">
          <ImportDialog classId={cls.id} onDone={onChange} />
          {withLinks && (
            <Link to={`/classes/${cls.id}`} className="inline-flex h-9 items-center rounded-sm border border-line bg-surface px-3 text-sm font-medium">
              Mở lớp
            </Link>
          )}
        </div>
      </div>
      {cls.students.length === 0 ? (
        <EmptyState title="Lớp chưa có học sinh" hint="Dùng “Nhập CSV” để thêm danh sách." />
      ) : (
        <Table>
          <thead>
            <tr><Th>Mã HS</Th><Th>Họ tên</Th><Th>Ngày sinh</Th></tr>
          </thead>
          <tbody>
            {cls.students.map((s) => (
              <tr key={s.code}><Td>{s.code}</Td><Td>{s.name}</Td><Td>{s.dob}</Td></tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}
