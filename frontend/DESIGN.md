# EduGen frontend – DESIGN

Reference for all frontend agents (Figma MCP unavailable; wireframe: https://www.figma.com/design/av67ZI6cu82TeT6mvm5Xi9). UI text is Vietnamese with full diacritics; code and comments are English.

## Tokens (`src/styles/tokens.css`, Tailwind `@theme`)

| Utility name | Hex | Use |
|---|---|---|
| `paper` | #F7F3E8 | page background |
| `surface` | #FFFDF7 | panels, inputs, header |
| `ink` | #1B1A17 | text |
| `muted` | #6E6A5E | secondary text |
| `line` | #E3DCC8 | all borders (1px) |
| `soft` | #EFE8D6 | subtle fills, hover |
| `accent` | #243B6B | primary action, active nav |
| `ok` / `warn` / `bad` | #2F6B4F / #B7791F / #B4481E | status only |
| `son` | #B5342A | the seal and danger actions |

Use as `bg-paper text-ink border-line text-muted`. Radius 6px (`rounded-sm`), no shadows. Font: Be Vietnam Pro 400/500/600, self-hosted via `@fontsource`.

## Foundation notes

- Tailwind v4 is loaded **without preflight**; legacy `src/styles.css` is imported into the CSS layer `legacy`, below Tailwind utilities, so utilities always win over legacy rules. Legacy pages still use `.card`, `button.primary` etc. until migrated; new code uses only Tailwind + `components/ui`.
- New shell is scoped under `.app` (font, background). Import alias `@` = `src`.
- Do not edit: `app/routes.tsx`, `app/nav.ts`, `components/ui/*`, `styles/tokens.css`. Add your pages in `features/<area>/` and your route objects in `features/<area>/routes.tsx`. Need a shared component: write it to `docs/needs-shared.md`.
- Shared components: `AppShell`, `Stepper` (+ `TEACHER_STEPS`, `GRADING_STEPS`), `Chip` (tones ok/warn/bad/muted/accent), `Seal`, `EmptyState`, `ErrorState`, `ComingSoon` (in `components/states.tsx`), `MotifBackdrop`. Role guard: `guard(["admin"], <Page/>)` from `features/common/pages`.
- Mock: `src/lib/mock.ts` (`USE_MOCK`, `delay`) and the `TODO(BE)` format documented in its header. Real calls: `// API: GET /api/v1/...`.

## Minimalist rules

- One thing per screen: one primary action, one `<h1>`.
- Content first: tables and text, not decoration. The motif backdrop is the only ornament.
- Color only for status (ok/warn/bad) and the single accent; the red `son` only for the seal and destructive actions.
- Lines instead of cards: separate with 1px `line`, not boxes or shadows.
- No scroll animations, no transitions beyond hover color.
- Every data page has 4 states: loading, empty (`EmptyState` with next step), error (`ErrorState` with retry), data.
- Never a dead link: every control goes to a real route or is disabled with a reason.

## Flows

- Teacher stepper: Ma trận (`/matrices`) – Kiểm tra (`/matrices/:id`) – Sinh đề (`/exams`) – Duyệt (`/exams/:id`) – Xuất (`/exams/:id/export`).
- Grading stepper: Lớp (`/classes`) – Phiếu (`/sheets`) – Quét (`/scans`) – Soát (`/scans/:id/review`) – Kết quả (`/results`).

## Screens

1. **Tải ma trận** (`/matrices`): selects (môn, lớp, kỳ thi) + dropzone for matrix file + list of recent matrices (name, status chip, date).
2. **Kiểm tra ma trận** (`/matrices/:id`): table of cells (chủ đề, mức độ, dạng, số câu); sticky bottom totals bar: 22 câu · 12 / 4 / 6 (nhiều lựa chọn / đúng-sai / trả lời ngắn), 10 điểm; confirm button.
3. **Sinh đề** (`/exams`): exam list; selected exam shows one row per matrix cell with progress, status chip (ok/warn/bad) and retry button per failed cell; poll status.
4. **Duyệt đề** (`/exams/:id`): 3 columns: left question navigator (numbered, status color), center question with answer, right panel source citation + SymPy verification result; bottom action bar (Duyệt / Sinh lại câu / Sửa).
5. **Xuất đề** (`/exams/:id/export`): A4 preview on the left; right buttons "Bản học sinh (.docx)" and "Bản giáo viên (.docx)"; `Seal` shown once approved.
6. **Ngân hàng đề** (`/bank`): search box + class chips (10/11/12) + rows (title, môn, số câu, ngày).
7. **Nguồn tài liệu** (`/admin/sources`, admin): stat row (số nguồn, số đoạn, độ phủ) + table of sources (name, status chip, chunks) + coverage bar per môn.
8. **Quản trị** (`/admin/bank`, `/admin/teachers`): toggles (`Switch`) to show/hide exams in the bank; teacher account table (name, email, active toggle) with create dialog.
9. **Lớp và học sinh** (`/classes`, `/classes/:id`): class list; detail has student table and "Nhập CSV" (dialog) with row-level error list.
10. **Phiếu trả lời** (`/sheets`): form (đề, lớp, số câu) on the left, answer sheet preview on the right, download button.
11. **Tải ảnh quét** (`/scans`): dropzone + table of files (name, status chip: đang đọc / xong / ảnh mờ / lỗi) linking to review.
12. **Soát kết quả đọc** (`/scans/:id/review`): scan image left; right list of read answers per question with editable value; doubtful answers have a `warn` outline; confirm button.
13. **Kết quả và ôn tập** (`/results`): stat row (điểm TB, cao nhất, thấp nhất) + score table per student + weak-topic bars + review suggestion with "Tạo đề ôn tập" button to `/matrices`.

Other routes: `/` (home, 3 entries by role), `/sample-exams`, `/sample-exams/:id` (no real page yet), 403 (`Forbidden`), 404 (`NotFound`).
