import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1_router
from app.core.config import settings
from app.core.middleware import SecurityHeadersMiddleware
from app.services import rag_client

# Ngoài môi trường dev không công khai tài liệu API (/docs, /redoc, /openapi.json).
_dev = settings.app_env == "dev"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Dựng RAG ở luồng nền: /health lên ngay, request sinh đề đầu tiên không phải chờ nạp bộ nhúng.
    if settings.rag_warmup:
        threading.Thread(target=rag_client.warm_up, name="rag-warmup", daemon=True).start()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="EduGen API",
    docs_url="/docs" if _dev else None,
    redoc_url="/redoc" if _dev else None,
    openapi_url="/openapi.json" if _dev else None,
)
app.add_middleware(SecurityHeadersMiddleware)
# Thêm sau cùng = lớp ngoài cùng, để preflight CORS được xử lý trước.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    # Frontend đọc tên file DOCX từ header này khi tải về.
    expose_headers=["Content-Disposition"],
)
app.include_router(v1_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
