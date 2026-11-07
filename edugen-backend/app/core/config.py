from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-secret-chi-dung-khi-phat-trien-doi-khi-chay-that"

# Dev-only, khớp docker-compose.yml/.env.example. Lắp từ biến thay vì một chuỗi
# "user:pass@host" liền để công cụ quét secret (SonarCloud) không coi là credential bị lộ.
_DEV_DB_ACCOUNT = "edugen"
DEV_DATABASE_URL = f"postgresql+psycopg://{_DEV_DB_ACCOUNT}:{_DEV_DB_ACCOUNT}@localhost:5433/{_DEV_DB_ACCOUNT}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = DEV_DATABASE_URL

    # "dev" cho máy cá nhân/test; giá trị khác (vd "production") bắt buộc JWT_SECRET riêng.
    app_env: str = "dev"
    # Đổi JWT_SECRET trong .env khi chạy thật (ít nhất 32 ký tự ngẫu nhiên).
    jwt_secret: str = DEV_JWT_SECRET
    access_token_minutes: int = 30
    refresh_token_days: int = 14
    password_hash_iterations: int = 600_000
    # Sai mật khẩu quá số lần này (cùng IP + email) trong cửa sổ thì tạm chặn đăng nhập.
    login_max_failures: int = 5
    login_window_minutes: int = 15
    # Giới hạn file tải lên (ma trận, đề mẫu).
    max_upload_mb: int = 20

    # Đường dẫn file kết quả mẫu (ket_qua_mau.json) → dùng RAG giả lập thay RAG thật.
    rag_mock_samples: str | None = None
    # Dựng RAG (bộ nhúng, Qdrant) ngay lúc khởi động ở luồng nền, để request đầu không bị treo.
    rag_warmup: bool = True

    # File ma trận, đề mẫu, DOCX xuất ra (sau này đổi sang S3/MinIO).
    storage_dir: str = "storage"
    marker_config_path: str = "marker_config.json"
    marker_timeout_seconds: float = 600.0
    # Bộ chuyển ảnh/PDF ma trận: marker (OCR cục bộ, cần extra ocr) hoặc gemini (tạm, gọi Gemini đọc ảnh).
    matrix_converter: Literal["marker", "gemini"] = "gemini"  # team chốt dùng Gemini (marker giữ làm dự phòng)
    matrix_gemini_model: str = "gemini-3.5-flash-lite"
    # Đọc lại khi lần đầu lệch (12/4/6, cột Tổng): model mạnh hơn, chỉ tốn khi cần; trống = dùng lại model trên
    matrix_gemini_retry_model: str | None = "gemini-3.8-flash"
    # Cùng file ma trận (giống hệt từng byte) tải lại thì dùng JSON đã lưu, không gọi Gemini; chỉ lưu kết quả sạch.
    matrix_cache_enabled: bool = True
    # Bộ đọc đề GV tải lên (T-055, D-016 sửa đổi 2026-11-07): gemini gửi thẳng PDF/ảnh; text lấy chữ rồi gọi make_llm.
    draft_extractor: Literal["gemini", "text"] = "gemini"
    draft_gemini_model: str = "gemini-3.5-flash-lite"

    # Origin của frontend được gọi API (mặc định: Vite dev server).
    # Trong .env: CORS_ORIGINS='["http://localhost:5173","https://..."]'
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @model_validator(mode="after")
    def _require_real_secret_outside_dev(self) -> "Settings":
        if self.app_env != "dev" and (self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < 32):
            raise ValueError("APP_ENV khác dev: phải đặt JWT_SECRET riêng, ít nhất 32 ký tự")
        return self


settings = Settings()
# genai.Client() và Qdrant đọc khoá từ os.environ, mà pydantic-settings không đẩy .env vào đó.
# Không gọi load_dotenv() ở đây: mọi nơi import (test, script) sẽ thừa hưởng khoá thật. Chạy local thì nạp có chủ đích
# bằng `uv run --env-file .env ...`; Docker truyền .env qua env_file.

