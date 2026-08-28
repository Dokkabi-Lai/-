"""推送相关接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..models import User
from .deps import require_admin
from ..services.notify_service import (
    push_daily_notification,
    send_macos_notification,
    sync_deadlines_to_calendar,
    sync_schedules_to_calendar,
)

router = APIRouter(prefix="/api/notify", tags=["notify"])


@router.post("/test")
def test_notification(user: User = Depends(require_admin)):
    """发送测试通知。"""
    ok = send_macos_notification("WLB大作战", "通知测试成功！", "如果你看到了这条通知，说明配置正常")
    return {"ok": ok}


@router.post("/daily")
def daily_push(user: User = Depends(require_admin)):
    """手动触发每日推送。"""
    ok = push_daily_notification()
    return {"ok": ok}


@router.post("/sync-calendar")
def sync_calendar(user: User = Depends(require_admin)):
    """同步日程和 DDL 到 macOS 系统日历。"""
    sch = sync_schedules_to_calendar()
    dl = sync_deadlines_to_calendar()
    return {
        "schedules": sch,
        "deadlines": dl,
        "message": "已同步到系统日历（首次使用需授权自动化权限）",
    }
