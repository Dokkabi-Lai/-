"""爬虫调度：定时执行 + 手动触发 + 入库去重。"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Group, Job, get_sessionmaker
from .base import BaseSpider, SpiderResult, log_spider
from .nowcoder import NowcoderSpider
from .smawiki import SmaWikiSpider


def _to_date(val):
    """把字符串/日期转成 date 对象，None/空保持 None。"""
    if not val:
        return None
    if isinstance(val, dt.datetime):
        return val.date()
    if isinstance(val, dt.date):
        return val
    if isinstance(val, str):
        try:
            return dt.date.fromisoformat(val[:10])
        except ValueError:
            return None
    return None


SPIDERS: dict[str, type[BaseSpider]] = {
    "nowcoder": NowcoderSpider,
    "smawiki": SmaWikiSpider,
}


def _save_jobs(db: Session, items: list[dict]):
    extra_keys = {"enterprise_url"}
    seen_ids = set()  # 防止同一批次内重复
    for it in items:
        source = it.get("source", "manual")
        source_id = it.get("source_id")
        # 批次内去重
        dedup_key = f"{source}:{source_id}"
        if source_id and dedup_key in seen_ids:
            continue
        seen_ids.add(dedup_key)

        if source_id:
            existing = db.query(Job).filter_by(source=source, source_id=source_id).first()
            if existing:
                # 更新关键字段
                for k in ("company", "title", "location", "salary", "description",
                          "requirements", "url", "batch"):
                    if k in it and it[k]:
                        setattr(existing, k, it[k])
                if it.get("open_date"):
                    existing.open_date = _to_date(it["open_date"])
                if it.get("close_date"):
                    existing.close_date = _to_date(it["close_date"])
                continue
        job = Job(
            source=source,
            source_id=source_id,
            company=it.get("company", ""),
            title=it.get("title", ""),
            location=it.get("location"),
            salary=it.get("salary"),
            description=it.get("description"),
            requirements=it.get("requirements"),
            batch=it.get("batch"),
            open_date=_to_date(it.get("open_date")),
            close_date=_to_date(it.get("close_date")),
            url=it.get("url"),
            raw={k: v for k, v in it.items() if k not in extra_keys},
        )
        db.add(job)
    db.commit()


def run_spider(source: str, db: Optional[Session] = None) -> SpiderResult:
    """运行单个爬虫。"""
    spider_cls = SPIDERS.get(source)
    if not spider_cls:
        return SpiderResult(source=source, status="failed", message=f"未知源: {source}")

    own_session = False
    if db is None:
        db = get_sessionmaker()()
        own_session = True
    try:
        with spider_cls() as spider:
            result = spider.run()
            if result.status == "success" and result.items:
                _save_jobs(db, result.items)
            log_spider(db, result)
            return result
    finally:
        if own_session:
            db.close()


def run_all_spiders() -> list[SpiderResult]:
    """运行所有启用的爬虫。"""
    settings = get_settings()
    results = []
    for source, enabled in settings.spider.sources.items():
        if not enabled:
            continue
        if source not in SPIDERS:
            continue
        try:
            r = run_spider(source)
            results.append(r)
        except Exception as e:
            results.append(SpiderResult(source=source, status="failed", message=str(e)))
    return results


# ---------- 定时调度 ----------

_scheduler: Optional[BackgroundScheduler] = None


def start_scheduler():
    """启动定时任务（每日推送与飞书岗位同步）。"""
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler()

    _scheduler.add_job(
        _daily_push,
        "cron",
        hour=8,
        minute=0,
        id="daily_push",
    )
    feishu = get_settings().jobs.feishu
    if feishu.sync_enabled and feishu.app_id and feishu.app_secret:
        _scheduler.add_job(
            _sync_feishu_groups,
            "cron",
            hour=feishu.sync_hour,
            minute=feishu.sync_minute,
            id="feishu_jobs_sync",
            replace_existing=True,
        )

    _scheduler.start()


def _daily_push():
    """每日推送任务。"""
    try:
        from ..services.notify_service import push_daily_notification
        push_daily_notification()
    except Exception:
        pass  # 推送失败不影响主服务


def _sync_feishu_groups():
    """依次更新所有已启用飞书同步的群组。"""
    db = get_sessionmaker()()
    try:
        from ..services.feishu_service import sync_jobs_from_feishu
        group_ids = [
            row[0] for row in db.query(Group.id).filter(
                Group.feishu_sync_enabled.is_(True),
                Group.feishu_spreadsheet_token.isnot(None),
            ).all()
        ]
        for group_id in group_ids:
            try:
                sync_jobs_from_feishu(db=db, group_id=group_id)
            except Exception:
                db.rollback()
    except Exception:
        pass  # 同步状态由 feishu_service 记录
    finally:
        db.close()


def stop_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
