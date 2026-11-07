# Tóm tắt: image Backend EduGen (T-043, bản cơ bản): Python 3.12 + uv, cài đúng phiên bản trong uv.lock (không có
# nhóm dev, không bge-m3/torch vì mặc định dùng Gemini embedding, D-011). Khi chạy: nâng schema Postgres
# (`alembic upgrade head`) rồi mở API ở cổng 8000 với 1 worker (Qdrant nhúng khoá thư mục, D-010).
FROM python:3.12-slim

# uv pinned for reproducible cloud images; bump together with the uv that writes uv.lock.
RUN pip install --no-cache-dir uv==0.11.29
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8

WORKDIR /app
# Dependencies first so a code change does not reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

# Run as an unprivileged user; /app/storage is created here so a new named volume inherits its owner.
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin edugen \
    && mkdir -p /app/storage && chown edugen:edugen /app/storage
USER edugen

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
