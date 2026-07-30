"""FastAPI 主入口。

启动: uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import BASE_DIR, get_settings
from .models import init_db
from .spiders.scheduler import start_scheduler, stop_scheduler

from .api import applications, auth, calendar, home, jobs, match, notify, resume, schedules, spider


STATIC_DIR = BASE_DIR / "app" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    init_db()
    start_scheduler()
    yield
    # 关闭
    stop_scheduler()


app = FastAPI(title="求职助手", lifespan=lifespan)

# 注册 API 路由
app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(resume.router)
app.include_router(applications.router)
app.include_router(match.router)
app.include_router(spider.router)
app.include_router(calendar.router)
app.include_router(schedules.router)
app.include_router(notify.router)
app.include_router(home.router)

# 静态资源
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    """返回前端单页。"""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "求职助手 API 已运行，前端待添加。访问 /docs 查看 API。"}


@app.get("/api/health")
def health():
    settings = get_settings()
    return {
        "status": "ok",
        "llm_provider": settings.llm.provider,
        "llm_configured": bool(settings.llm_provider_config().api_key),
    }
