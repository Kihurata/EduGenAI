# EduGenAI

Hệ thống AI hỗ trợ giáo viên THPT sinh đề và chấm bài các môn Toán, Lý, Hóa, Sinh theo định dạng của Bộ GD&ĐT.

*AI system that helps Vietnamese high-school teachers generate and grade exams (Math, Physics, Chemistry, Biology) in the official Ministry of Education format.*

## Tính năng chính

- **Sinh đề**: nạp tài liệu nguồn (SGK, đề tham khảo), chia đoạn, nhúng vector vào Qdrant; lập ma trận đề; sinh câu hỏi bằng RAG có trích nguồn; kiểm tra đáp án số bằng SymPy; giáo viên duyệt; xuất Word/PDF; ngân hàng câu hỏi.
- **Chấm bài và học lại**: quản lý lớp, phiếu trả lời, chấm bằng scan/OCR, kết quả và gợi ý ôn tập.

## Cấu trúc repo

| Thư mục | Nội dung |
|---|---|
| `edugen-backend/` | Backend FastAPI: xác thực, ma trận, RAG sinh đề, ngân hàng câu hỏi, xuất DOCX |
| `frontend/` | Frontend React + Vite |
| `deploy/` | Docker Compose cho môi trường production |

Các thư mục sẽ được bổ sung dần theo từng mốc phát triển.

## Quy ước đóng góp

Xem [CONTRIBUTING.md](CONTRIBUTING.md): commit theo [Conventional Commits](https://www.conventionalcommits.org/), mỗi thay đổi gắn với một GitHub Issue, viết test trước code (TDD).
