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

## Chạy test

```bash
cd edugen-backend
uv run pytest -q                      # unit + integration, dùng fake, không tốn tiền API
uv run pytest --list-suites           # các bộ test theo chức năng (tests/features.yaml)
uv run pytest --suite F-03            # chỉ một chức năng
uv run --env-file .env pytest -m acceptance   # luồng đầy đủ với mô hình thật
uv run --env-file .env pytest -m eval         # đo chất lượng so với ngưỡng trên bộ dữ liệu vàng
```

- Test `acceptance` và `eval` bị loại khỏi lần chạy mặc định; chúng cần khóa API và chỉ mục Qdrant thật, và tự bỏ qua khi thiếu dữ liệu sách.
- Chạy từ rẻ lên đắt và dừng khi tầng rẻ đã đỏ: test dùng fake, truy xuất Qdrant cục bộ, đo recall chỉ truy xuất, rồi mới đến gọi mô hình với vài ô mẫu. Không chạy cả đề hay nạp lại sách bằng Gemini chỉ để kiểm tra.
- Thêm file test mới thì thêm vào `tests/features.yaml`; `tests/test_features_map.py` kiểm tra bản đồ luôn khớp với code.
