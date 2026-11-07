from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.middleware import SecurityHeadersMiddleware

# Outside dev the API docs (/docs, /redoc, /openapi.json) are not published.
_dev = settings.app_env == "dev"

app = FastAPI(
    title="EduGen API",
    docs_url="/docs" if _dev else None,
    redoc_url="/redoc" if _dev else None,
    openapi_url="/openapi.json" if _dev else None,
)
app.add_middleware(SecurityHeadersMiddleware)
# Added last = outermost layer, so CORS preflight is answered first.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    # The frontend reads the DOCX file name from this header on download.
    expose_headers=["Content-Disposition"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
