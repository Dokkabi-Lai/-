"""FastAPI 主入口。

启动: uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import BASE_DIR, get_settings
from .models import init_db
from .services.excel_import_service import import_jobs_from_config
from .spiders.scheduler import start_scheduler, stop_scheduler

from .api import applications, auth, calendar, groups, home, jobs, notify, schedules


STATIC_DIR = BASE_DIR / "app" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    feishu = get_settings().jobs.feishu
    if not (feishu.app_id and feishu.app_secret and feishu.spreadsheet_token):
        import_jobs_from_config()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="秋招投递助手", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(groups.router)
app.include_router(jobs.router)
app.include_router(applications.router)
app.include_router(calendar.router)
app.include_router(schedules.router)
app.include_router(notify.router)
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
    from .models import Job, get_sessionmaker

    db = get_sessionmaker()()
    try:
        job_count = db.query(Job).count()
    finally:
        db.close()
    return {"status": "ok", "job_count": job_count}
