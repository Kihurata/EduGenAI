# Hướng dẫn đóng góp

## Commit message: Conventional Commits

```
<type>(<scope>): <mô tả ngắn, tiếng Anh, thì hiện tại, không viết hoa đầu, không dấu chấm cuối>

[body: vì sao thay đổi, không chỉ thay đổi gì]

[footer: Refs: #12 | Closes #12 | BREAKING CHANGE: ...]
```

| type | Dùng khi |
|---|---|
| `feat` | Thêm tính năng |
| `fix` | Sửa lỗi |
| `test` | Thêm hoặc sửa test |
| `refactor` | Đổi cấu trúc code, không đổi hành vi |
| `perf` | Tăng hiệu năng |
| `docs` | Tài liệu |
| `build` | Dependency, Docker, đóng gói |
| `ci` | GitHub Actions |
| `chore` | Việc lặt vặt khác |
| `style` | Định dạng, không đổi logic |
| `revert` | Hoàn tác commit trước |

**scope** gợi ý: `core`, `db`, `rag`, `exam`, `api`, `bank`, `export`, `frontend`, `deploy`.

Ví dụ:

```
test(rag): require manifest grade in SGK chunk heading path
feat(rag): pass manifest grade to SGK chunker

Closes #12
```

## Bật hook kiểm tra commit message

Chạy một lần sau khi clone:

```bash
git config core.hooksPath .githooks
```

CI cũng kiểm tra lại mọi commit trên push và pull request.

## Issue và nhánh

- Mỗi thay đổi gắn với một GitHub Issue; commit ghi `Refs: #N`, commit hoàn tất ghi `Closes #N`.
- Tên nhánh: `<type>/<issue>-<mo-ta>`, ví dụ `feat/12-sgk-chunker`.

## TDD

Không viết code sản phẩm khi chưa có test đỏ yêu cầu nó. Commit `test(...)` đứng trước commit `feat(...)` hoặc `fix(...)` tương ứng. LLM, embedding và OCR dùng fake trong unit test; CI không gọi API trả phí.
