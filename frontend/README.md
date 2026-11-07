# EduGen Frontend (demo)

Giao diện web mỏng để chạy thử cả luồng của BE: ma trận → sinh đề → GV duyệt → xuất Word → ngân hàng đề.
React 19 + Vite + TypeScript, gọi thẳng REST API của `edugen-backend` (`/api/v1`). Công thức LaTeX hiển thị bằng KaTeX.

## Chạy trên máy

Cần Node 20+ và `uv` (cho BE).

```bash
# 1. BE dev: SQLite + RAG giả lập + tài khoản seed sẵn, không cần Postgres/marker
cd edugen-backend
uv run python scripts/dev_server.py          # http://localhost:8000 ; --reset để xoá dữ liệu

# 2. Frontend
cd frontend
npm install
npm run dev                                  # http://localhost:5173
```

Đăng nhập: `gv@nd.vn` (giáo viên) hoặc `admin@nd.vn` (admin), mật khẩu BE dev in ra console lúc chạy (lưu ở
`edugen-backend/dev_data/password.txt`; muốn tự đặt thì set `EDUGEN_DEV_PASSWORD` trước lần chạy đầu hoặc `--reset`).

- Chưa cài marker thì BE dev chỉ nhận ảnh ma trận mẫu có sẵn markdown, ví dụ
  `edugen-backend/tests/fixtures/matrices/ktgk_hk1_toan10.png`. Thêm ma trận mẫu: đặt cặp `ten.png` + `ten.md`
  vào thư mục đó (hoặc `--matrix-dir`).
- Câu hỏi đến từ RAG giả lập (`tests/fixtures/rag/ket_qua_mau.json`) nên lặp lại; chưa phải câu RAG sinh thật.
- Chạy với BE thật: đặt `VITE_API_URL` trong `.env.local` và thêm origin của frontend vào `CORS_ORIGINS` của BE.

## Các màn

| Màn | Đường dẫn | Làm gì |
|---|---|---|
| Ma trận | `/matrices` | Tải ảnh/PDF ma trận, xem trạng thái đọc |
| Chi tiết ma trận | `/matrices/:id` | Sửa ô (dạng, mức độ, số câu, mức từng ý Đ/S), lưu, xác nhận, sinh đề |
| Đề thi | `/exams` | Danh sách đề và trạng thái sinh |
| Duyệt đề | `/exams/:id` | Xem câu theo Phần I/II/III; sửa, sinh lại, xoá câu; bù ô thiếu; duyệt; tải DOCX bản HS/GV; admin nạp vào ngân hàng |
| Ngân hàng đề | `/bank` | Lọc theo lớp, tải đề; admin bật/tắt hiện cho GV, gỡ đề |

Chưa có: quản lý tài khoản GV và đề mẫu (admin) — vẫn dùng `/docs` của BE.

## Kiểm tra

```bash
npm run typecheck
npm run build
```
