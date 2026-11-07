# Danh sách điểm nối Backend (frontend skeleton)

> Tóm tắt: các hợp đồng dưới đây do Frontend **đề xuất** khi dựng skeleton (chưa phải hợp đồng đã duyệt). Backend và RAG cần xem, sửa rồi chốt (làm thành `D-###` sau) trước khi thay `mock.ts` bằng `api()`.

- Nguồn: `grep -rn "TODO(BE)" src` và `grep -rn "// API:" src` (nhánh `feat/frontend-skeleton`). Hai dòng `src/lib/mock.ts:6,8` chỉ là ví dụ trong tài liệu, không phải điểm nối.
- Tất cả đường dẫn có tiền tố `/api/v1`. Cột "Có ở BE?" đối chiếu với các router trong `edugen-backend/app/api/v1/` (auth, admin, bank, exams, matrices, sample_exams).
- "Chênh lệch" ghi chỗ FE giả định khác BE hiện có; để trống nghĩa là chưa thấy khác.

## 1. Khối 2 – Lớp, phiếu, quét, kết quả (`features/grading/`, mock: `features/grading/mock.ts`)

Owner chung: Backend (Huy/Phu). Không endpoint nào dưới đây có ở BE (BE chưa có lớp, học sinh, phiếu, quét, kết quả).

| # | Method + đường dẫn | Request | Response | Owner | File:dòng | Có ở BE? | Chênh lệch |
|---|---|---|---|---|---|---|---|
| 1 | `GET /classes` | không | `[{id, name, students:[{code,name,dob}]}]` | Backend | grading/mock.ts:37 | Không | Trả luôn danh sách học sinh trong từng lớp: nặng khi nhiều lớp, nên tách `student_count`. Tên trường `code/name/dob` khác CSV `ma_hs/ho_ten/ngay_sinh`. |
| 2 | `GET /classes/{class_id}` | không | `{id,name,students[]}` hoặc 404 | Backend | grading/mock.ts:44 | Không | |
| 3 | `POST /classes` | `{name}` | `{id,name,students:[]}` | Backend | grading/mock.ts:51 | Không | Chưa có `school_id`/`owner_id` (BE đang tách dữ liệu theo trường). |
| 4 | `POST /classes/{class_id}/students/import` (multipart CSV) | `file=ma_hs,ho_ten,ngay_sinh` | `{created, errors:[{row,message}]}` | Backend | grading/mock.ts:62 | Không | FE hiện gửi **văn bản CSV** (đọc bằng `file.text()` hoặc dán vào ô), chưa gửi tệp multipart. |
| 5 | `GET /exams?status=approved` | query `status` | `[{id,title}]` | Backend | grading/mock.ts:87 | **Có một phần**: `GET /exams` (exams.py:153) | BE **không có** bộ lọc `status`; trả `ExamOut` đầy đủ kèm `questions` (nặng). Giáo viên chỉ thấy đề của mình, admin thấy cả trường. Hiện FE dùng 3 đề giả `e1..e3`, id không khớp đề thật. |
| 6 | `GET /answer-sheets` | không | `[{id,examId,examTitle,classId,className,code}]` | Backend | grading/mock.ts:94 | Không | Tên trường camelCase, BE dùng snake_case (xem mục 4). |
| 7 | `POST /answer-sheets` | `{exam_id,class_id,versions}` | `[{id,examId,examTitle,classId,className,code}]` | Backend | grading/mock.ts:101 | Không | Request snake_case nhưng response camelCase trong cùng một comment. Giới hạn `versions` 1..4 chỉ nằm ở FE. |
| 8 | `GET /answer-sheets/{id}/pdf` | không | `application/pdf` (A4, ô đánh dấu góc, bong bóng) | Backend | grading/SheetsPage.tsx:116 | Không | Nút "Tải PDF" đang `disabled`. |
| 9 | `GET /scans` | không | `[{id,fileName,status: received/reading/blurry, review: pending/confirmed/skipped, studentName}]` | Backend | grading/mock.ts:130 | Không | FE polling 1 giây (ScansPage.tsx:17); camelCase. |
| 10 | `GET /scans/{scan_id}` | không | `{id,fileName,status,review,studentName,answers:[{q,value,confidence,flag}]}` hoặc 404 | Backend | grading/mock.ts:137 | Không | Thiếu URL ảnh quét (xem mục 5). `flag`: ok/doubtful/blank. |
| 11 | `POST /scans` (multipart ảnh) | `files[]=image/*\|pdf` | `[{id,fileName,status:"reading"}]` | Backend + OCR (Dong) | grading/mock.ts:144 (nhắc lại ở ScansPage.tsx:33) | Không | FE chỉ gửi **tên tệp** vào mock, chưa gửi nội dung. Chưa có trạng thái `ocr_failed` (DESIGN yêu cầu "lỗi"). |
| 12 | `PATCH /scans/{scan_id}/answers/{q}` | `{value:"A"\|"B"\|"C"\|"D"}` | `{q,value,confidence:1,flag:"ok"}` | Backend | grading/mock.ts:162 | Không | Chỉ Phần I trắc nghiệm A-D; Phần II/III chưa có hợp đồng. |
| 13 | `POST /scans/{scan_id}/confirm` và `POST /scans/{scan_id}/skip` | không | `{id, review}`; confirm kích hoạt chấm | Backend | grading/mock.ts:171 | Không | Hai endpoint trong một comment. Chưa nói đáp án đúng lấy từ đâu (mock dùng khóa cố định `KEY`, 12 câu). |
| 14 | `GET /results?class_id=` | query `class_id` (tùy chọn) | `{rows:[{scanId,studentName,correct,total,score}], topics:[{topic,percentCorrect}]}` | Backend | grading/mock.ts:184 | Không | `topic` là chuỗi tự do; cần khớp `topic` của ô ma trận mới tạo được đề ôn tập. |
| 15 | `GET /results/export.csv?class_id=` | query `class_id` | `text/csv` (`hoc_sinh,so_cau_dung,diem`) | Backend | grading/mock.ts:201 | Không | Hiện FE tự dựng CSV ở trình duyệt. |
| 16 | `POST /remedial-exams` | `{topics:string[]}` | `{matrix_id}` | Backend | grading/ResultsPage.tsx:77 | Không | Nút "Tạo đề ôn tập" hiện chỉ chuyển sang `/matrices`, không truyền dữ liệu. |

## 2. Admin – Nguồn tài liệu và độ phủ (`features/admin/sources/`, mock: `features/admin/sources/mock.ts`)

Owner: Backend (Huy/Phu) + RAG (Dong Quan). Không endpoint nào có ở BE dưới tên `/admin/sources`.

| # | Method + đường dẫn | Request | Response | Owner | File:dòng | Có ở BE? | Chênh lệch |
|---|---|---|---|---|---|---|---|
| 17 | `GET /admin/sources` | không | `[{id,name,kind:"sgk"\|"de",subject,grade,official,status:"loaded"\|"loading"\|"pending"\|"failed"}]` | Backend + RAG | admin/sources/mock.ts:13 | Không (gần nhất: `GET /admin/sample-exams`, sample_exams.py:94) | `status` của FE (`loaded/loading/pending/failed`) khác `IngestStatus` của BE (`pending/sent/ingested/failed`). `subject` FE là chữ hiển thị ("Toán", "Lý"...), BE dùng mã môn (`subject.code`). DESIGN.md nhắc cột "số đoạn" nhưng response chưa có `chunks`. |
| 18 | `POST /admin/sources` (multipart) | `file=<pdf\|json\|yaml>`, `manifest={name,kind,subject,grade,official}` | `Source` (status `pending`) | Backend + RAG | admin/sources/mock.ts:19 | Không (gần nhất: `POST /admin/sample-exams`, sample_exams.py:56: `file`, `title`, `grade`, subject; nhận pdf/docx) | Trùng chức năng với đề mẫu khi `kind="de"`: cần quyết định gộp hay giữ hai nơi. FE mới chỉ truyền `filename`, không gửi tệp. |
| 19 | `POST /admin/sources/{id}/ingest` | không | `{id,status:"loading"}` (202, chạy nền) | Backend + RAG | admin/sources/mock.ts:29 | Không (đề mẫu và ngân hàng tự gửi RAG bằng background task) | Mock trả cả `Source`, không phải `{id,status}`. |
| 20 | `GET /admin/sources/{id}/ingest-status` | không | `{id,status,chunks,error?}` | Backend + RAG | admin/sources/mock.ts:37 | Không | **UI không hề gọi** hàm này: mock `finishIngest` chốt `loaded` ngay sau `startIngest`. Chưa có polling trạng thái. |
| 21 | `GET /admin/sources/coverage` | không | `{covered,total}` | RAG (Dong Quan) | admin/sources/mock.ts:50 | Không | Chỉ tổng, chưa theo môn (DESIGN.md mô tả "thanh độ phủ từng môn"). Mock cố định `total = 4*14`. |
| 22 | `POST /admin/sources/coverage/check` | không | `{ok,missing}` | RAG (Dong Quan) | admin/sources/mock.ts:59 | Không | UI đọc thêm trường `ref` ("TC-017") mà response trong comment **không** có (types.ts `CoverageCheck.ref`). |

## 3. Giáo viên – Ma trận (`features/teacher/`, dùng API thật)

| # | Method + đường dẫn | Request | Response | Owner | File:dòng | Có ở BE? | Chênh lệch |
|---|---|---|---|---|---|---|---|
| 23 | `POST /matrices` nhận thêm `subject`, `grade`, `exam_type` | file + `subject=toan\|ly\|hoa\|sinh`, `grade=10\|11\|12`, `exam_type=string` | `{id,status}` (không đổi) | Backend (Huy/Phu) | teacher/MatricesPage.tsx:35 | **Có** (matrices.py:122) nhưng chỉ nhận `file` | BE bỏ qua các trường thêm. Ba ô chọn trên màn "Tải ma trận" hiện **không được gửi** (xem review-findings, mục 3). Mã `exam_type` chưa định nghĩa (`thpt`, `hk` trong UI). |

## 4. Các lời gọi đã có thật (`// API:`), đối chiếu với BE

Tất cả khớp method, đường dẫn và thân request với router hiện có (đã đối chiếu với `origin/dev:frontend/src/pages/*`, không đổi hợp đồng).

| Method + đường dẫn | File:dòng | Có ở BE? |
|---|---|---|
| `GET /exams` | common/pages.tsx:32, teacher/ExamsPage.tsx:21, admin/BankPage.tsx:141 | Có (exams.py:153) |
| `GET /exams/{id}` | teacher/ExamReviewPage.tsx:32, teacher/ExamExportPage.tsx:23 | Có (exams.py:162) |
| `GET /exams/{id}/export?variant=student\|teacher` | teacher/ExamExportPage.tsx:57 | Có (exams.py:167) |
| `POST /exams` | teacher/MatrixCheckPage.tsx:140 | Có (exams.py:130) |
| `POST /exams/{id}/cells/{cell_id}/fill` | teacher/ExamReviewPage.tsx:72, teacher/ExamsPage.tsx:31 | Có (exams.py:250) |
| `POST /exams/{id}/approve` | teacher/ExamReviewPage.tsx:77 | Có (exams.py:265) |
| `PUT /exams/{id}/questions/{qid}` | teacher/QuestionPanel.tsx:50 | Có (exams.py:203) |
| `DELETE /exams/{id}/questions/{qid}` | teacher/QuestionPanel.tsx:34 | Có (exams.py:219) |
| `POST /exams/{id}/questions/{qid}/regenerate` | teacher/QuestionPanel.tsx:39 | Có (exams.py:239) |
| `GET /matrices` | teacher/MatricesPage.tsx:23 | Có (matrices.py:150) |
| `POST /matrices` (multipart) | teacher/MatricesPage.tsx:34 | Có (matrices.py:122) |
| `GET /matrices/{id}` | teacher/MatrixCheckPage.tsx:58, teacher/lib.tsx:63 | Có (matrices.py:158) |
| `PUT /matrices/{id}/cells` | teacher/MatrixCheckPage.tsx:122 | Có (matrices.py:163) |
| `POST /matrices/{id}/confirm` | teacher/MatrixCheckPage.tsx:134 | Có (matrices.py:174) |
| `GET /bank[?grade=]` | teacher/BankPage.tsx:22, admin/BankPage.tsx:19 | Có (bank.py:117) |
| `GET /bank/{id}/export?variant=...` | teacher/BankPage.tsx:71 | Có (bank.py:149) |
| `POST /bank {exam_id,is_visible}` | admin/BankPage.tsx:158 | Có (bank.py:91) |
| `PATCH /bank/{id} {is_visible}` | admin/BankPage.tsx:38 | Có (bank.py:156) |
| `DELETE /bank/{id}` | admin/BankPage.tsx:45 | Có (bank.py:169) |
| `GET /admin/teachers` | admin/TeachersPage.tsx:14 | Có (admin.py:33) |
| `POST /admin/teachers {email,password,full_name}` | admin/TeachersPage.tsx:142 | Có (admin.py:19) |
| `PATCH /admin/teachers/{id} {is_active?,password?}` | admin/TeachersPage.tsx:20 | Có (admin.py:43; BE còn nhận `full_name`) |

Chưa có chỗ nào trong FE dùng: `GET /bank/{id}`, `/auth/change-password`, `/auth/logout-all`, và toàn bộ `/admin/sample-exams` (trang Đề mẫu ở FE đang là placeholder dù BE đã có, chỉ admin dùng được).

## 5. Điểm nối còn thiếu (FE cần nhưng chưa có `TODO(BE)`)

- `GET /scans/{scan_id}/image`: màn Soát đang vẽ ảnh giả (`ReviewPage.tsx:17`), cần URL ảnh thật để đối chiếu.
- `GET /admin/sources/{id}` (hoặc dùng danh sách): nút "Xem" trong `SourcesPage.tsx:143` chỉ hiện lại dòng đã có.
- Đáp án đúng và số câu của đề để chấm (mock cố định `KEY`, `QUESTION_COUNT = 12`): cần nằm trong response của phiếu hoặc kết quả.
