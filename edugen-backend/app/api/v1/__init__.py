from fastapi import APIRouter

from app.api.v1 import admin, auth, bank, exams, matrices, sample_exams, subjects, topics

router = APIRouter(prefix="/api/v1")
for module in (auth, admin, sample_exams, matrices, exams, bank, topics, subjects):
    router.include_router(module.router)
