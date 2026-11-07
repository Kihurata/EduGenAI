// Tóm tắt: trang Đề mẫu (T-050): GV tải đề Toán/Lý/Hoá (PDF, DOCX hoặc JSON), xem danh sách và trạng thái
// (đang đọc → chờ duyệt → đã gửi RAG → RAG đã học), bấm vào một đề để duyệt bản nháp.
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api";
import { Badge, ErrorBox, formatTime, useAction, usePolling } from "../common";
import { SUBJECT_LABEL, type SampleExam, type SubjectCode } from "../types";

export default function SampleExams() {
  const navigate = useNavigate();
  const [items, setItems] = useState<SampleExam[] | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [subject, setSubject] = useState<SubjectCode>("toan");
  const [grade, setGrade] = useState(12);
  const [title, setTitle] = useState("");
  const list = useAction();
  const upload = useAction();

  const load = useCallback(() => {
    void list.run(async () => setItems(await api<SampleExam[]>("/admin/sample-exams")));
  }, []);
  useEffect(load, [load]);
  usePolling(load, !!items?.some((s) => s.status === "pending" || s.status === "sent"));

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("subject", subject);
    form.append("grade", String(grade));
    form.append("title", title.trim() || file.name);
    const created = await upload.run(() => api<SampleExam>("/admin/sample-exams", { method: "POST", form }));
    if (created) navigate(`/sample-exams/${created.id}`);
  }

  return (
    <>
      <div className="page-head">
        <h1 className="text-xl font-semibold">Đề mẫu</h1>
      </div>

      <form className="card upload" onSubmit={submit}>
        <div>
          <strong>Tải đề lên</strong>
          <p className="muted">
            PDF, DOCX hoặc JSON. BE đọc đề thành bản nháp; bạn duyệt, sửa chủ đề, mức độ, đáp án rồi xác nhận thì RAG mới
            học đề này. Đề chỉ dùng trong trường của bạn.
          </p>
        </div>
        <div className="meta-row">
          <label>
            Môn
            <select value={subject} onChange={(e) => setSubject(e.target.value as SubjectCode)}>
              {Object.entries(SUBJECT_LABEL).map(([code, name]) => (
                <option key={code} value={code}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Lớp
            <select value={grade} onChange={(e) => setGrade(Number(e.target.value))}>
              {[10, 11, 12].map((g) => (
                <option key={g}>{g}</option>
              ))}
            </select>
          </label>
          <label>
            Tiêu đề
            <input value={title} placeholder="vd: Thi thử Vật lí 12 lần 1" onChange={(e) => setTitle(e.target.value)} />
          </label>
        </div>
        <input
          type="file"
          accept="application/pdf,application/json,.json,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <button type="submit" className="primary" disabled={!file || upload.busy}>
          {upload.busy ? "Đang tải…" : "Tải lên"}
        </button>
        <ErrorBox error={upload.error} />
      </form>

      <ErrorBox error={list.error} />
      {items?.length === 0 && <p className="empty">Chưa có đề mẫu nào.</p>}
      {items && items.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Tiêu đề</th>
                <th>Môn</th>
                <th>Lớp</th>
                <th>Trạng thái</th>
                <th>Lỗi cần sửa</th>
                <th>File gốc</th>
                <th>Tải lên lúc</th>
              </tr>
            </thead>
            <tbody>
              {items.map((s) => (
                <tr key={s.id}>
                  <td>
                    <Link to={`/sample-exams/${s.id}`}>{s.title}</Link>
                  </td>
                  <td>{SUBJECT_LABEL[s.subject] ?? s.subject}</td>
                  <td>{s.grade}</td>
                  <td>
                    <Badge status={s.status} />
                  </td>
                  <td>{s.draft ? s.issues.length : "—"}</td>
                  <td className="muted">{s.original_filename}</td>
                  <td className="muted">{formatTime(s.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
