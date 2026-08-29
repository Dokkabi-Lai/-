"""FastAPI 主入口。

启动: uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import BASE_DIR, get_settings
from .models import init_db, get_db_backend, validate_database_config
from .services.excel_import_service import import_jobs_from_config

from .api import applications, auth, calendar, groups, home, jobs, schedules


STATIC_DIR = BASE_DIR / "app" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_database_config()
    init_db()
    import_jobs_from_config()
    yield


app = FastAPI(title="秋招投递助手", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(groups.router)
app.include_router(jobs.router)
app.include_router(applications.router)
app.include_router(calendar.router)
app.include_router(schedules.router)
app.include_router(home.router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

avatar_dir = get_settings().storage.avatar_dir
avatar_path = BASE_DIR / avatar_dir if not avatar_dir.startswith("/") else avatar_dir
app.mount("/avatars", StaticFiles(directory=str(avatar_path), check_dir=False), name="avatars")


@app.get("/")
async def index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "秋招投递助手 API 已运行，访问 /docs 查看 API。"}


@app.get("/api/health")
def health():
    from .models import Job, User, get_sessionmaker

    db = get_sessionmaker()()
    try:
        job_count = db.query(Job).count()
        user_count = db.query(User).count()
    finally:
        db.close()
    backend = get_db_backend()
    return {
        "status": "ok",
        "job_count": job_count,
        "user_count": user_count,
        "database": backend,
        "persistent": backend == "postgresql",
    }
