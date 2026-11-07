# Kết quả rà soát frontend skeleton (Q2)

> Tóm tắt: rà soát tĩnh nhánh `feat/frontend-skeleton` theo quy ước trong kế hoạch (mục 3, 4, 6) và `DESIGN.md`. Chưa chạy trình duyệt, nên các mục về giao diện là suy luận từ mã và CSS, cần xác nhận bằng ảnh chụp. Mức độ: high / medium / low.

Đếm: **high 2 · medium 8 · low 14**.

## 0. Kết luận theo từng hạng mục

| Mục | Kết quả |
|---|---|
| a) `TODO(BE)` đúng chuẩn | Gần đạt: 23 hợp đồng có đủ req / res / owner / now; 1 con trỏ thiếu hẳn (`ScansPage.tsx:33`). Các lệch còn lại ở mục 4 |
| b) Mock chỉ import trong thư mục khu vực | Đạt. `mock` chỉ được import trong `features/grading/*` và `features/admin/SourcesPage.tsx`; `@/lib/mock` dùng chung hợp lệ |
| c) Không route nào là `ComingSoon` | Gần đạt: không route nào dùng `ComingSoon`, nhưng `/sample-exams` là trang "chưa khả dụng" tương đương (mục 3) |
| d) Chữ giao diện tiếng Việt có dấu | Đạt với chuỗi cố định. Còn lọt chữ tiếng Anh qua đường lỗi mạng và trạng thái lạ (mục 12) |
| e) Một `<h1>` mỗi trang | Đạt: mỗi component trang có đúng một `<h1>`, kể cả nhánh tải/lỗi |
| f) Đủ 4 trạng thái | Phần lớn đạt; thiếu ở vài chỗ (mục 7, 15) |
| j) Luồng API thật | Không phát hiện chỗ làm hỏng: cùng endpoint, method, body so với `origin/dev`. `api.ts`, `auth.tsx`, `common.tsx`, `types.ts` không đổi |

## 1. [high] CSS cũ vẫn tác động lên giao diện mới qua các selector theo thẻ

`src/styles/index.css:6` nạp toàn bộ `src/styles.css` vào lớp `legacy`. Chỉ có `.empty` (`main.tsx:15`) còn dùng class cũ, nhưng các quy tắc theo **thẻ** vẫn áp lên mọi trang mới vì tiện ích Tailwind chỉ thắng khi trang có đặt thuộc tính đó:

- `styles.css:57-59` `a { color: var(--primary) }`: các `Link` không có class màu bị xanh `#1f5fbf`, lệch bảng màu. Thấy ở thẻ trang chủ và tiêu đề đề thi gần đây (`features/common/pages.tsx:52-62`, `74-77`; tiêu đề `<p>` kế thừa màu từ `<a>`).
- `styles.css:62-65` `h2 { font-size: 1.4rem }`: mọi `<h2 className="font-medium">` không đặt cỡ chữ to hơn `<h1 text-xl>` (1.25rem). Ví dụ `ExamReviewPage.tsx:114,189,203`, `ResultsPage.tsx:45,58,73`, `StudentPanel.tsx:78`, `ExamsPage.tsx:87`, `pages.tsx:79`. Thứ bậc tiêu đề bị đảo.
- `styles.css:378-383` `th { text-transform: uppercase; font-size: .8rem }`: tiêu đề cột `Th` bị viết hoa, trái tinh thần tối giản của DESIGN.
- `styles.css:3-47` biến màu và `color-scheme: dark` theo `prefers-color-scheme`: trên máy chế độ tối, liên kết xanh nhạt `#8ab8f8` trên nền kem gần như không đọc được, và `<select>`, thanh cuộn, ô tệp bị vẽ tối.
- `styles.css:73-77` `code`, `192-203` `input/select/textarea`, `224-236` `button`, `179-185` `label { display:flex }`, `136-143` `main`: lọt vào các phần tử mới (ví dụ `<label className="text-sm">` ở `MatricesPage.tsx:56` thành cột flex ngoài ý muốn).

Đề xuất: chuyển trang `.empty` sang `states.tsx`, rồi xóa `styles.css` (giữ riêng vài dòng `.katex-display` nếu cần). Trước mắt, bọc `@layer legacy` chỉ gồm selector theo class, hoặc xóa các quy tắc theo thẻ ở trên. Cần xác nhận bằng ảnh chụp ở chế độ sáng và tối.

## 2. [high] Chữ cảnh báo `warn` không đủ tương phản

Tính từ token (WCAG, chữ nhỏ cần ≥ 4,5:1):

| Chữ | trên `paper` #F7F3E8 | trên `surface` #FFFDF7 | trên `soft` #EFE8D6 | Kết luận |
|---|---|---|---|---|
| ink #1B1A17 | 15,70 | 17,11 | 14,24 | đạt |
| accent #243B6B | 9,90 | 10,79 | 8,98 | đạt |
| ok #2F6B4F | 5,68 | 6,19 | 5,15 | đạt |
| bad #B4481E | 4,87 | 5,31 | 4,42 | đạt trên paper/surface, **trượt trên soft** |
| son #B5342A | 5,43 | 5,92 | 4,92 | đạt |
| muted #6E6A5E | 4,87 | 5,31 | **4,42** | trượt trên soft |
| **warn #B7791F** | **3,28** | **3,58** | **2,98** | **trượt mọi nền** |

Nơi dùng `warn` làm màu chữ: `Chip` tông warn (`components/Chip.tsx:7`, chữ `text-xs`), `MatrixCheckPage.tsx:164,327`, `ExamReviewPage.tsx:226`, `ReviewPage.tsx:88` (chữ "Không chắc"). Đề xuất: đổi token `warn` thành `#8F5E18` (≥ 4,5 trên cả ba nền, 4,54 trên soft), giữ màu cũ làm viền nếu muốn. `muted` có thể chỉnh thành `#6C685C` (4,56 trên soft); `bad` trên `soft` chỉ cần để ý ở `ErrorState`/chip nằm trên hàng được chọn.

Viền ô nhập `line` #E3DCC8 trên `surface` chỉ 1,35:1 (WCAG 1.4.11 yêu cầu 3:1 cho ranh giới điều khiển): đề xuất viền riêng cho `Input/Select/textarea` khoảng `#8F8873`+ (3,48 trên surface) hoặc đậm hơn.

## 3. [medium] Ba ô chọn trên "Tải ma trận" trông dùng được nhưng không được gửi

`features/teacher/MatricesPage.tsx:56-77`: "Lớp" và "Kỳ thi" là `<Select>` bật, không có `value`/`onChange`, và không đưa vào `FormData` (dòng 35-40; đã ghi trong `TODO(BE)`). "Môn" bị `disabled` chỉ có `title`. Giáo viên chọn Lớp 10 sẽ không có tác dụng. Đề xuất: `disabled` cả hai kèm dòng chú thích "Sẽ chọn ở bước Kiểm tra", hoặc ẩn đến khi BE nhận trường.

## 4. [medium] Chuẩn `TODO(BE)`: các lệch nhỏ

- `features/grading/ScansPage.tsx:33` là con trỏ một dòng, không có req / res / owner / now, và trùng điểm nối với `grading/mock.ts:144`. Nên bỏ hoặc đổi sang `// see`.
- `grading/mock.ts:171` gộp hai endpoint (`confirm` và `skip`) vào một comment; chuẩn là mỗi điểm nối một comment.
- `grading/mock.ts:144` ghi `OCR (Dong)`: nên ghi đủ tên (Dong Quan) cho nhất quán với `admin/sources/mock.ts`.
- Hợp đồng đề xuất trộn snake_case (`exam_id`, `class_id`) với camelCase (`examTitle`, `className`, `fileName`, `studentName`, `scanId`, `percentCorrect`) trong cùng comment (`mock.ts:101-104`). BE toàn snake_case (`matrix_id`, `cells_done`). Nên đổi `types.ts` và response đề xuất sang snake_case ngay bây giờ, vì đổi sau sẽ chạm mọi trang.
- `admin/sources/mock.ts:37`: `TODO` của `GET .../ingest-status` nằm trên `finishIngest`, nhưng UI không bao giờ gọi trạng thái nạp; mock xác nhận `loaded` ngay lập tức (`SourcesPage.tsx:43-47`). Hợp đồng chưa được dùng thử.
- `admin/sources/mock.ts:59` response không có `ref` nhưng UI đọc `check.ref` (`SourcesPage.tsx` hiển thị "· TC-017").
- Thiếu điểm nối: ảnh phiếu quét thật (`ReviewPage.tsx:17` dùng ảnh giả). Xem `backend-todo.md` mục 5.

## 5. [medium] Cờ `VITE_USE_MOCK` không có tác dụng

`lib/mock.ts:15` xuất `USE_MOCK` nhưng không nơi nào đọc nó (grep chỉ thấy khai báo). Các trang gọi `getX()` trong `mock.ts` vô điều kiện, nên `VITE_USE_MOCK=false` không đổi gì, trái kế hoạch mục 3. Hoặc xóa cờ và comment (nếu quyết định "mock luôn bật cho Khối 2"), hoặc cho mỗi `getX()` rẽ nhánh sang `api()` khi cờ tắt. Câu hỏi 2 ở mục 7 của kế hoạch vẫn chưa được chốt.

## 6. [medium] Trang Đề mẫu là placeholder dù BE đã có endpoint

`features/common/SampleExams.tsx` hiển thị "Chức năng đề mẫu chưa khả dụng" cho cả `/sample-exams` và `/sample-exams/:id`, trong khi kế hoạch mục 2 xếp là "thật (đã có)" và BE đã có `/admin/sample-exams` (`sample_exams.py:56,94,107`). Menu "Đề mẫu" (`app/nav.ts:16`) hiện cho cả giáo viên, nhưng BE chỉ cho admin. Hệ quả: một mục menu dẫn tới trang "chưa có", vi phạm "không có link chết" ở tinh thần. Đề xuất: cho `roles: ["admin"]` và ghi rõ trong comment khi nào thay (sau khi T-050 được merge).

## 7. [medium] Xử lý lỗi bất đồng bộ chưa có `try/catch`, nút kẹt trạng thái bận

Các hàm sau gọi hàm mock và không bắt lỗi. Với mock hiện chưa lỗi, nhưng khi thay bằng `api()` sẽ gây "unhandled rejection", nút kẹt `busy=true` hoặc im lặng: `ClassesPage.tsx:19`, `SheetsPage.tsx:62-68` (`busy` không bao giờ reset khi lỗi), `StudentPanel.tsx:17-23`, `ScansPage.tsx:22-26`, `ReviewPage.tsx:41-52` (`finish`, `fix`), `SourcesPage.tsx:43,48,181` (`ingest`, `runCheck`, `submit`). Teacher/admin cũ dùng `useAction`/`run` bắt lỗi tốt; nên dùng chung cho khu vực mới.

## 8. [medium] Admin vào "Ngân hàng đề" ở menu chính thấy bản dành cho giáo viên

`app/nav.ts:15` trỏ `/bank` cho cả hai vai trò. Admin thấy `teacher/BankPage` (không có công tắc Hiện, nạp, gỡ), muốn quản lý phải đi `/admin/bank` qua `AdminNav` (chỉ hiện sau khi vào một trang admin). Cũng vì thế, câu hướng dẫn rỗng ở `admin/BankPage.tsx:66` ("Mở một đề đã duyệt và bấm Nạp vào ngân hàng đề") đã lỗi thời: nút nằm ngay trong trang, còn nút cũ trong màn Duyệt đề đã bỏ (so với `ExamDetail.tsx` cũ ở `origin/dev`, chức năng nạp chuyển hẳn sang `/admin/bank`; đây là thay đổi hành vi có chủ đích nhưng nên nêu trong PR). Đề xuất: với admin, `/bank` chuyển hướng sang `/admin/bank`, hoặc thêm mục menu admin riêng; sửa câu hướng dẫn.

## 9. [medium] Trích dẫn nguồn hiện thô

`ExamReviewPage.tsx:196`: khi trích dẫn không phải chuỗi thì hiện `JSON.stringify(c)`. Nguyên tắc dự án là mỗi câu hỏi phải có nguồn đọc được; nếu BE trả đối tượng, giáo viên sẽ thấy JSON thô. Cần xác nhận hình dạng `citations` từ RAG rồi định dạng (tên tài liệu, trang/bài).

## 10. [medium] Nhãn cho điều khiển trong bảng ma trận

`MatrixCheckPage.tsx:224-290`: các `Input/Select` trong từng hàng (chủ đề, nội dung, dạng, mức độ, số câu, năng lực, mức từng ý đúng-sai) chỉ có tiêu đề cột bằng mắt, không có `aria-label`, nên trình đọc màn hình đọc "ô nhập" không rõ. Thêm `aria-label={`Chủ đề, ô ${i + 1}`}` và tương tự. Ngoài ra `MatricesPage.tsx:79-97`: vùng thả tệp là `<label>` bọc `<input className="sr-only">`, nhưng khi focus bằng phím không có dấu hiệu nhìn thấy; thêm `focus-within:` viền accent.

## Mục low

12. **Chữ tiếng Anh lọt qua đường lỗi.** `teacher/lib.tsx:30-34` (`errText`) trả `error.message` thô: lỗi mạng của `fetch` là "Failed to fetch" (English). `STATUS[status] ?? status` (`teacher/lib.tsx:29`, `pages.tsx:49`, `common.tsx:76`) hiện nguyên enum nếu BE thêm trạng thái mới. Gợi ý: bọc `fetch` trong `api.ts` để ném `ApiError` tiếng Việt khi `TypeError`. Phần còn lại: chuỗi cố định đều tiếng Việt có dấu; các từ như CSV, PDF, RAG, SymPy, OCR, Email, EduGen là thuật ngữ/tên riêng.
13. **Thống nhất chính tả.** "Xoá/Huỷ" (`QuestionPanel.tsx:135,140,247`, `MatrixCheckPage.tsx:299`, `common.tsx:161`) so với "Hủy/Khóa" (admin: `BankPage.tsx:199`, `shared.tsx:74`, `TeachersPage.tsx:71,88`). Chọn một kiểu (kiểu mới: hủy, xóa, khóa).
14. **Nhãn menu lệch.** Menu chính ghi "Tài khoản" (`nav.ts:19`), `AdminNav` ghi "Giáo viên" (`admin/shared.tsx:12`), tiêu đề trang là "Giáo viên".
15. **Thiếu trạng thái.** `SheetsPage` không xử lý khi `exams.data` rỗng (ô chọn đề trống, không báo, `SheetsPage.tsx:83-88`); `MatrixCheckPage` không có trạng thái rỗng khi ma trận đọc ra 0 ô (`cells.length === 0`, dòng 177); `teacher/BankPage.tsx:48` bỏ lỗi khi tải lại sau đổi lớp (chỉ báo lỗi khi `!items`) và không có chỉ báo tải lại; `grading/useLoad.tsx` giữ dữ liệu cũ khi lỗi nên `Gate` vừa hiện lỗi vừa hiện bảng cũ.
16. **Dữ liệu cũ khi đổi lựa chọn.** `teacher/lib.tsx:63-74` (`useMatrixCells`) không xóa `cells` khi `matrixId` đổi/mất, nên `ExamsPage` ghép ô của ma trận trước với lượt chạy của đề mới trong thoáng chốc. `grading/useLoad.tsx` cũng không hủy yêu cầu cũ khi `id` đổi (có thể ghi đè bằng phản hồi trễ).
17. **Nút dùng để điều hướng.** `ScansPage.tsx:70` (nút "Chấm các phiếu đã nhận" gọi `navigate`) và `pages.tsx:93-94` (404/403) nên là `<Link>` để mở tab mới và đọc đúng vai trò. Các `<Link>` giả nút (`ClassesPage.tsx:89`, `ExamReviewPage.tsx:242`) là đúng.
18. **`aria-label` trên `div` không có `role`.** `SheetsPage.tsx:18` (`aria-label` trên `div` bị bỏ qua); các nút tab mã đề ở `SheetsPage.tsx:107-110` thiếu `role="tab"/aria-selected`; `ReviewPage` chọn lỗi chỉ bằng màu viền.
19. **Dialog đọc tiêu đề hai lần.** `components/ui/dialog.tsx:13` dùng `Description` chỉ lặp lại `title` (`sr-only`). Bỏ `Description` và đặt `aria-describedby={undefined}` hoặc truyền mô tả thật.
20. **Liên kết chỉ khác màu.** Nhiều `text-accent` không gạch chân (`ExamsPage.tsx:78`, `ExamReviewPage.tsx:90,102`, `MatricesPage.tsx:112`); chấp nhận được vì accent đủ tương phản và nằm trong ngữ cảnh điều hướng, nhưng nên thống nhất.
21. **Lặp mã.** Bản đồ trạng thái ở trang chủ (`pages.tsx:18-24`) lặp `teacher/lib.tsx:9-25` và lệch tông ("Đang sinh": accent so với muted); `errText` có hai bản (`admin/shared.tsx:26`, `teacher/lib.tsx:30`); ba cách tải dữ liệu (`useAction` ở teacher, `useLoad` ở `admin/shared.tsx:28`, `useLoad` ở `grading/useLoad.tsx`).
22. **`ErrorBoundary` không tự phục hồi khi đổi route** (`ErrorBoundary.tsx`): sau một lỗi, chỉ tải lại trang mới thoát. Có thể thêm `key={location.pathname}`.
23. **`routes.tsx` phụ thuộc thứ tự mảng** (`app/routes.tsx:11-12`): `home` là phần tử đầu và `notFound` là phần tử cuối của `commonRoutes`; thêm route chung mới có thể phá âm thầm. Tách `home`/`notFound` thành export riêng.
24. **`main.tsx:15`** dùng class cũ `empty` cho trạng thái tải khi khởi động; dùng `Loading` và cho đúng bố cục.
25. **Giả lập `ExamsPage` khi ô chưa có lượt chạy.** `ExamsPage.tsx:70`: ô không có `run` mà đề không còn `generating` hiện "Lỗi" nhưng không có nút thử lại (cần `need > 0` trong `run`).

## Mã chết và di sản

(Đối chiếu mục g và i.)

**Import từ mã cũ (nên chuyển dần):**

- `@/common` (`src/common.tsx`): `useAction`, `usePolling`, `formatTime`, `MathText` được dùng ở `common/Login.tsx`, `pages.tsx`, `teacher/*` (7 file). Chuyển thành `lib/hooks.ts`, `lib/format.ts`, `components/MathText.tsx`.
- `@/api` (`src/api.ts`): `api`, `download`, `ApiError` ở 12 file; chuyển thành `lib/api.ts`.
- `@/auth` (`src/auth.tsx`) và `@/types` (`src/types.ts`): `features/common/auth.tsx`, `lib/types.ts`. Các tệp này **không đổi** so với `origin/dev`, nên chuyển bằng `git mv` để không làm nhiễu diff.

**Chưa dùng ở đâu:**

- `common.tsx`: `Badge` (75), `ErrorBox` (79), `ConfirmButton` (135-165), cùng `STATUS_LABEL`/`STATUS_TONE` (37-72). Hết tham chiếu (grep chỉ thấy định nghĩa). `MathText`, `useAction`, `usePolling`, `formatTime` vẫn dùng.
- `src/styles.css` (651 dòng): chỉ `.empty` được dùng; các lớp `.card`, `.badge`, `.notice`, `.question`, `.options`, `.upload`, `.toolbar`... không còn xuất hiện trong `.tsx` nào. Nhưng nhiều quy tắc theo thẻ vẫn gây hại (mục 1).
- `components/ui/tabs.tsx`: không file nào import.
- `lucide-react` trong `package.json`: không file nào import.
- `components/Stepper.tsx:35` `TEACHER_STEPS`: thay bằng `teacherSteps()` trong `teacher/lib.tsx`.
- `components/states.tsx:29` `ComingSoon`: không route nào dùng; DESIGN.md vẫn liệt kê.
- `lib/mock.ts:15` `USE_MOCK`: không ai đọc (mục 5).
- Thư mục rỗng `src/pages/` (git không theo dõi), và `docs/needs-shared.md` không tồn tại (không agent nào cần).

## Kiểm tra bàn phím và hộp thoại (mục h)

- Hộp thoại: tất cả dùng `DialogContent title=...` nên đều có tiêu đề (đạt). Hộp thoại xóa trong `QuestionPanel` là xác nhận tại chỗ, không phải Dialog; chấp nhận được nhưng khác với admin.
- Nút so với liên kết: điều hướng nội bộ dùng `Link`/`NavLink` (đạt) ngoại trừ mục 17.
- Nhãn ô nhập: Login, Admin (qua `Field`), Classes, Scans, StudentPanel, Sheets đều có nhãn hoặc `aria-label`; thiếu ở bảng ma trận (mục 10). Công tắc `Switch` có `aria-label` hoặc nằm trong `<label>` (đạt).
- Dấu focus: không có quy tắc nào xóa outline (đạt, dùng mặc định trình duyệt); riêng vùng thả tệp mục 10.

## Luồng API thật (mục j)

So `origin/dev:frontend/src/pages/{Exams,ExamDetail,Matrices,MatrixDetail,Bank,QuestionCard}.tsx` với trang mới:

- Cùng endpoint, method và body cho: `GET /exams`, `GET /exams/{id}`, `POST /exams/{id}/cells/{cell}/fill`, `POST /exams/{id}/approve`, `PUT/DELETE/POST regenerate` câu hỏi, `GET/POST /matrices`, `GET /matrices/{id}`, `PUT /matrices/{id}/cells` (cùng `{cells,name,grade}`), `POST /matrices/{id}/confirm`, `POST /exams` (`{matrix_id,duration_minutes,title}`), `GET /bank?grade=`, `GET /bank/{id}/export?variant=`.
- Khác biệt hành vi (có chủ đích, cần nêu trong PR): (1) nạp đề vào ngân hàng chuyển từ màn chi tiết đề sang `/admin/bank`; (2) quản lý ngân hàng (bật/tắt, gỡ) chuyển khỏi `/bank` (mục 8); (3) ô tìm kiếm tên đề ở `/bank` lọc phía máy khách; (4) xuất file Word chuyển sang trang `/exams/:id/export` (cùng URL tải, tên tệp mặc định cũ).
- Không phát hiện chỗ làm hỏng luồng. Mọi hành động ghi vẫn đi qua `useAction`/`run` nên lỗi từ BE vẫn hiện.

## Top 5

1. [high] CSS cũ theo thẻ còn tác động giao diện mới (liên kết xanh, `h2` to hơn `h1`, tiêu đề bảng viết hoa, chế độ tối).
2. [high] `warn` #B7791F trượt tương phản ở mọi nền (3,28-3,58); `muted` trượt trên `soft`; viền ô nhập 1,35:1.
3. [medium] Hợp đồng đề xuất Khối 2 trộn camelCase/snake_case và trạng thái nguồn khác `IngestStatus` của BE; sửa trước khi BE bám theo.
4. [medium] Cờ `VITE_USE_MOCK` không có tác dụng; hàm bất đồng bộ không bắt lỗi, nút kẹt bận khi thay `api()`.
5. [medium] Trang Đề mẫu là placeholder, menu hiện cho giáo viên; "Tải ma trận" có hai ô chọn không được gửi.
