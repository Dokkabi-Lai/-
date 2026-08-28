"""秋招岗位相关接口。"""
from __future__ import annotations

import datetime as dt
import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from ..models import Application, Group, Job, JobMark, User, get_db
from ..services.group_service import is_platform_admin
from .deps import get_current_group, get_current_user, require_group_owner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobOut(BaseModel):
    id: int
    source: str
    company: str
    title: str
    location: Optional[str] = None
    salary: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    open_date: Optional[str] = None
    close_date: Optional[str] = None
    url: Optional[str] = None
    referrer_code: Optional[str] = None
    favorited: bool = False

    class Config:
        from_attributes = True


class JobCreate(BaseModel):
    company: str
    title: str
    company_type: Optional[str] = None
    batch: Optional[str] = None
    location: Optional[str] = None
    salary: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    open_date: Optional[str] = None
    close_date: Optional[str] = None
    close_date_text: Optional[str] = None
    apply_rule: Optional[str] = None
    url: Optional[str] = None
    referrer_code: Optional[str] = None


def _marks_map(db: Session, user_id: int) -> dict[int, JobMark]:
    rows = db.query(JobMark).filter(JobMark.user_id == user_id).all()
    return {m.job_id: m for m in rows}


def _get_mark(db: Session, user_id: int, job_id: int) -> JobMark:
    mark = db.query(JobMark).filter_by(user_id=user_id, job_id=job_id).first()
    if not mark:
        mark = JobMark(user_id=user_id, job_id=job_id, passed=False, favorited=False)
        db.add(mark)
        db.flush()
    return mark


def _serialize(job: Job, applied: bool = False, mark: JobMark | None = None) -> dict:
    return {
        "id": job.id,
        "source": job.source,
        "company": job.company,
        "title": job.title,
        "company_type": job.company_type,
        "location": job.location,
        "salary": job.salary,
        "description": job.description,
        "requirements": job.requirements,
        "batch": job.batch,
        "open_date": job.open_date.isoformat() if job.open_date else None,
        "close_date": job.close_date.isoformat() if job.close_date else None,
        "close_date_text": job.close_date_text,
        "apply_rule": job.apply_rule,
        "url": job.url,
        "referrer_code": job.referrer_code,
        "favorited": bool(mark.favorited) if mark else False,
        "passed": bool(mark.passed) if mark else False,
        "applied": applied,
        "is_active": job.is_active is not False,
        "created_by_id": job.created_by_id,
        "group_id": job.group_id,
    }


@router.get("")
def list_jobs(
    keyword: Optional[str] = None,
    location: Optional[str] = None,
    batch: Optional[str] = None,
    company_type: Optional[str] = None,
    favorited: Optional[bool] = None,
    only_open: bool = False,
    source: Optional[str] = None,
    hide_passed: bool = True,
    applied: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    applied_ids = {
        r[0]
        for r in db.query(Application.job_id).filter(
            Application.user_id == user.id,
            Application.job_id.isnot(None),
        ).all()
        if r[0]
    }
    marks = _marks_map(db, user.id)
    q = db.query(Job).filter(Job.group_id == group.id, Job.is_active.is_not(False))
    if hide_passed:
        passed_ids = [jid for jid, m in marks.items() if m.passed]
        if passed_ids:
            q = q.filter(~Job.id.in_(passed_ids))
    if keyword:
        q = q.filter(or_(
            Job.company.contains(keyword),
            Job.title.contains(keyword),
            Job.description.contains(keyword),
        ))
    if location:
        q = q.filter(Job.location.contains(location))
    if batch:
        q = q.filter(Job.batch == batch)
    if company_type:
        q = q.filter(Job.company_type == company_type)
    if source:
        q = q.filter(Job.source == source)
    if favorited is not None:
        fav_ids = [jid for jid, m in marks.items() if m.favorited]
        if favorited:
            q = q.filter(Job.id.in_(fav_ids or [-1]))
        elif fav_ids:
            q = q.filter(~Job.id.in_(fav_ids))
    if only_open:
        today = dt.date.today()
        q = q.filter(or_(Job.close_date == None, Job.close_date >= today))
    if applied == "applied" and applied_ids:
        q = q.filter(Job.id.in_(applied_ids))
    elif applied == "applied":
        q = q.filter(Job.id == -1)
    elif applied == "unapplied" and applied_ids:
        q = q.filter(~Job.id.in_(applied_ids))
    total = q.count()
    rows = q.order_by(desc(Job.created_at)).offset(offset).limit(limit).all()
    return {"total": total, "items": [_serialize(j, j.id in applied_ids, marks.get(j.id)) for j in rows]}


@router.get("/batches/list")
def list_batches(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    """获取所有可用批次列表"""
    from sqlalchemy import func
    rows = db.query(Job.batch, func.count(Job.id)).filter(
        Job.group_id == group.id, Job.batch.isnot(None), Job.is_active.is_not(False)
    ).group_by(Job.batch).all()
    return [{"batch": b, "count": c} for b, c in rows]


@router.get("/company-types/list")
def list_company_types(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    from sqlalchemy import func
    rows = db.query(Job.company_type, func.count(Job.id)).filter(
        Job.group_id == group.id, Job.company_type.isnot(None), Job.is_active.is_not(False)
    ).group_by(Job.company_type).all()
    return [{"company_type": t, "count": c} for t, c in rows]


@router.get("/import/status")
def import_status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    from ..services.excel_import_service import import_status as _status

    result = _status(db, group_id=group.id)
    result["can_manage"] = True
    result["can_sync"] = bool(is_platform_admin(user) or group.owner_id == user.id)
    return result


@router.post("/import/reload")
def reload_from_excel(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(require_group_owner),
):
    """从最近一次上传或配置的 Excel 重新导入岗位。"""
    from ..services.excel_import_service import import_jobs_from_excel

    try:
        result = import_jobs_from_excel(db=db, group_id=group.id, created_by_id=user.id)
        return {"message": "导入完成", **result}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"导入失败: {e}")


@router.post("/import/upload")
async def upload_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(require_group_owner),
):
    """上传 Excel / CSV 覆盖岗位库（推荐每天更新用这个）。"""
    from ..services.excel_import_service import import_jobs_from_bytes

    name = (file.filename or "").lower()
    if not name.endswith((".xlsx", ".xls")):
        raise HTTPException(400, "请上传 .xlsx 表格（飞书：文件 → 下载为 Excel）")
    content = await file.read()
    if not content:
        raise HTTPException(400, "文件是空的")
    try:
        result = import_jobs_from_bytes(
            content, save_as_latest=True, db=db, group_id=group.id, created_by_id=user.id
        )
        return {"message": "上传并导入完成", **result}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"导入失败: {e}")


@router.post("/import/feishu")
def import_from_feishu(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(require_group_owner),
):
    """从飞书电子表格同步岗位。"""
    from ..services.feishu_service import sync_jobs_from_feishu

    try:
        result = sync_jobs_from_feishu(db=db, group_id=group.id)
        return {"message": "飞书同步完成", **result}
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"飞书同步失败: {e}")


@router.post("/import/rows")
def import_rows(
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    """接收类 Excel 网格提交的固定字段岗位。"""
    from ..services.excel_import_service import import_job_items, parse_value_rows

    rows = body.get("rows") or []
    if not isinstance(rows, list) or not rows:
        raise HTTPException(400, "请至少填写一行岗位")
    if len(rows) > 300:
        raise HTTPException(400, "单次最多导入 300 行")
    keys = [
        "company", "company_type", "batch", "location", "title", "description",
        "url", "open_date", "close_date", "apply_rule", "referrer_code", "recorded_at",
    ]
    headers = [
        "公司", "公司类型", "批次", "BASE", "岗位", "岗位JD",
        "投递链接", "开始日期", "截止日期", "投递机制", "内推码", "记录时间",
    ]
    values = []
    errors = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append({"row": index, "message": "行格式不正确"})
            continue
        company = str(row.get("company") or "").strip()
        title = str(row.get("title") or "").strip()
        if not company or not title:
            errors.append({"row": index, "message": "公司和岗位为必填项"})
            continue
        values.append([row.get(key) for key in keys])
    items = parse_value_rows(headers, values)
    if not items:
        raise HTTPException(400, {"message": "没有可导入的岗位", "errors": errors})
    result = import_job_items(
        items,
        db=db,
        source_label="manual",
        group_id=group.id,
        created_by_id=user.id,
    )
    return {"message": "岗位已加入群组", **result, "errors": errors}


@router.get("/{job_id}")
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    job = db.query(Job).filter(Job.id == job_id, Job.group_id == group.id).first()
    if not job:
        raise HTTPException(404, "岗位不存在")
    applied = db.query(Application).filter(
        Application.user_id == user.id, Application.job_id == job_id
    ).first() is not None
    return _serialize(job, applied, _marks_map(db, user.id).get(job.id))


@router.post("")
def add_job(
    data: JobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    job = Job(
        source="manual",
        source_id=f"g{group.id}-manual-{dt.datetime.now().timestamp()}-{user.id}",
        group_id=group.id,
        created_by_id=user.id,
        company=data.company,
        title=data.title,
        company_type=data.company_type,
        batch=data.batch,
        location=data.location,
        salary=data.salary,
        description=data.description,
        requirements=data.requirements,
        open_date=dt.date.fromisoformat(data.open_date) if data.open_date else None,
        close_date=dt.date.fromisoformat(data.close_date) if data.close_date else None,
        close_date_text=data.close_date_text,
        apply_rule=data.apply_rule,
        url=data.url,
        referrer_code=data.referrer_code,
    )
    db.add(job)
    db.commit()
    return _serialize(job)


@router.post("/{job_id}/favorite")
def toggle_favorite(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    job = db.query(Job).filter(Job.id == job_id, Job.group_id == group.id).first()
    if not job:
        raise HTTPException(404, "岗位不存在")
    mark = _get_mark(db, user.id, job_id)
    mark.favorited = not mark.favorited
    db.commit()
    return {"favorited": mark.favorited}


@router.delete("/{job_id}")
def delete_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    job = db.query(Job).filter(Job.id == job_id, Job.group_id == group.id).first()
    if not job:
        raise HTTPException(404, "岗位不存在")
    if not is_platform_admin(user) and group.owner_id != user.id and job.created_by_id != user.id:
        raise HTTPException(403, "只能下架自己添加的岗位")
    job.is_active = False
    db.commit()
    return {"ok": True}


@router.post("/pass-company")
def pass_company(
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    company = body.get("company", "").strip()
    if not company:
        raise HTTPException(400, "company 不能为空")
    jobs = db.query(Job).filter(Job.group_id == group.id, Job.company == company).all()
    if not jobs:
        raise HTTPException(404, "没有找到该公司岗位")
    marks = _marks_map(db, user.id)
    all_passed = bool(jobs) and all(marks.get(j.id) and marks[j.id].passed for j in jobs)
    new_val = not all_passed
    for j in jobs:
        mark = _get_mark(db, user.id, j.id)
        mark.passed = new_val
    db.commit()
    return {"company": company, "passed": new_val, "count": len(jobs)}


@router.post("/{job_id}/pass")
def toggle_pass(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    job = db.query(Job).filter(Job.id == job_id, Job.group_id == group.id).first()
    if not job:
        raise HTTPException(404, "岗位不存在")
    mark = _get_mark(db, user.id, job_id)
    mark.passed = not mark.passed
    db.commit()
    return {"passed": mark.passed}


# ---------- 抓取 JD ----------

# 需要移除的 HTML 标签（导航、脚本、页脚等无关内容）
_STRIP_TAGS = {"script", "style", "nav", "footer", "header", "aside", "noscript", "iframe", "svg", "img", "form"}

# 常见 JD 关键词，用于从页面中定位正文段落
_JD_KEYWORDS = re.compile(
    r"(岗位|职位|职责|要求|描述|任职|资格|条件|说明|工作内容|招聘|薪资|待遇|福利|"
    r"job|description|requirement|responsibility|qualification|duty)",
    re.IGNORECASE,
)


def _extract_text_from_html(html: str) -> str:
    """用 BeautifulSoup 从 HTML 中提取可读文本。"""
    soup = BeautifulSoup(html, "html.parser")

    # 移除无用标签
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()

    # 尝试找到包含 JD 关键词最多的 <div>/<section>/<article>
    best_block = None
    best_score = 0
    for container in soup.find_all(["div", "section", "article", "main"]):
        text = container.get_text(separator="\n", strip=True)
        if len(text) < 50:
            continue
        hits = len(_JD_KEYWORDS.findall(text))
        # 加权：长度适中 + 关键词多
        score = hits * 10 + min(len(text), 3000) / 100
        if score > best_score:
            best_score = score
            best_block = text

    if best_block and len(best_block) >= 80:
        return best_block

    # 回退到全文
    return soup.get_text(separator="\n", strip=True)


def _clean_text(text: str) -> str:
    """清理提取出的文本：去除连续空行、过长空白等。"""
    lines = text.splitlines()
    cleaned = []
    blank_count = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            blank_count += 1
            if blank_count <= 1:
                cleaned.append("")
            continue
        blank_count = 0
        cleaned.append(stripped)
    return "\n".join(cleaned).strip()


_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_WAF_MARKERS = [
    "CF_APP_WAF", "AC_Opt", "requestInfo", "sceneId",
    "anti_spider", "验证码", "安全验证",
]


def _fetch_html_httpx(url: str) -> Optional[str]:
    """用 httpx 快速抓取页面 HTML，失败返回 None。"""
    try:
        with httpx.Client(
            timeout=20.0,
            follow_redirects=True,
            headers={
                "User-Agent": _UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text
    except httpx.HTTPStatusError as e:
        logger.warning("httpx 状态错误 %s: %s", url, e.response.status_code)
    except httpx.RequestError as e:
        logger.warning("httpx 请求失败 %s: %s", url, e)
    return None


def _playwright_fetch_jd(url: str, job_title: str) -> Optional[str]:
    """用 Playwright 打开页面，搜索职位标题，尝试提取该岗位的 JD 文本。

    策略：
      1. 找到包含职位标题的可点击元素，点击后等待详情展开/页面跳转，提取详情文本
      2. 找到包含职位标题的文本块，提取附近含 JD 关键词的最近文本块
      3. 提取页面上含 JD 关键词的最大文本块
      4. 回退到整页可见文本
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=_UA)
        page.set_default_timeout(30000)

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception as e:
            logger.warning("Playwright goto 失败 %s: %s", url, e)
            # 尝试 domcontentloaded 作为后备
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                browser.close()
                return None

        page.wait_for_timeout(3000)  # 等 JS 渲染

        # ---- 策略 1: 找可点击的职位标题元素，点击后提取详情 ----
        detail_text = _try_click_job_title(page, job_title)
        if detail_text and len(detail_text) >= 50:
            browser.close()
            return detail_text

        # ---- 策略 2 & 3 & 4: 从当前页面 HTML 提取 ----
        html = page.content()
        browser.close()

    # 如果 Playwright 交互阶段没有拿到详情，用 HTML 提取
    return _extract_jd_from_html(html, job_title)


def _try_click_job_title(page, job_title: str) -> Optional[str]:
    """尝试在页面上找到包含职位标题的可点击元素，点击后提取详情文本。"""
    title_norm = job_title.strip()

    # 常见的职位列表选择器模式
    selectors = [
        # 通用：包含 position/job 文字的 class
        "[class*='position']", "[class*='job']", "[class*='Position']", "[class*='Job']",
        "[class*='detail']", "[class*='Detail']",
        "[class*='list-item']", "[class*='item']", "[class*='card']",
        # 常见框架
        "li", "tr", "a", "div[role='button']",
    ]

    for selector in selectors:
        try:
            elements = page.query_selector_all(selector)
        except Exception:
            continue

        for el in elements:
            try:
                text = el.inner_text(timeout=2000)
            except Exception:
                continue
            if not text:
                continue
            # 检查元素文本是否包含职位标题（允许部分匹配）
            if title_norm in text or _fuzzy_title_match(title_norm, text):
                # 检查这个元素本身或其子元素是否可点击
                tag = el.evaluate("e => e.tagName.toLowerCase()")
                if tag in ("a", "button") or el.evaluate("e => getComputedStyle(e).cursor === 'pointer'"):
                    try:
                        el.click(timeout=5000)
                        page.wait_for_timeout(2000)  # 等待详情展开或页面跳转
                        # 提取详情区域
                        detail = _extract_detail_after_click(page)
                        if detail and len(detail) >= 50:
                            return detail
                    except Exception as e:
                        logger.debug("点击职位元素失败: %s", e)
                        continue

    return None


def _fuzzy_title_match(title: str, text: str) -> bool:
    """模糊匹配职位标题：去掉空格后检查包含关系。"""
    title_clean = re.sub(r"[\s（）()]+", "", title)
    text_clean = re.sub(r"[\s（）()]+", "", text)
    if not title_clean:
        return False
    return title_clean in text_clean


def _extract_detail_after_click(page) -> Optional[str]:
    """点击职位后，尝试从详情区域/弹窗/新页面提取 JD 文本。"""
    # 常见详情区域选择器
    detail_selectors = [
        "[class*='detail-content']", "[class*='job-detail']", "[class*='position-detail']",
        "[class*='desc']", "[class*='description']", "[class*='content-detail']",
        "[class*='modal-body']", "[class*='dialog-body']",
        "[class*='popup-content']", "[class*='drawer-content']",
        "main", "article", "[role='dialog']",
    ]

    best_text = None
    best_score = 0

    for selector in detail_selectors:
        try:
            elements = page.query_selector_all(selector)
        except Exception:
            continue
        for el in elements:
            try:
                text = el.inner_text(timeout=2000)
            except Exception:
                continue
            if not text or len(text) < 50:
                continue
            hits = len(_JD_KEYWORDS.findall(text))
            score = hits * 10 + min(len(text), 3000) / 100
            if score > best_score:
                best_score = score
                best_text = text

    if best_text:
        return _clean_text(best_text)

    # 回退到整页文本
    try:
        return _clean_text(page.inner_text("body", timeout=3000))
    except Exception:
        return None


def _extract_jd_from_html(html: str, job_title: str) -> Optional[str]:
    """从 HTML 中提取与特定职位标题相关的 JD 文本。

    策略：
      1. 找到包含职位标题的容器，提取其附近含 JD 关键词的文本块
      2. 提取含 JD 关键词最多的文本块
      3. 回退到整页文本
    """
    soup = BeautifulSoup(html, "html.parser")

    # 移除无用标签
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()

    title_norm = re.sub(r"[\s（）()]+", "", job_title.strip())

    # ---- 策略 1: 找包含职位标题的容器，提取其父级/兄弟节点的 JD 文本 ----
    if title_norm:
        best_nearby = None
        best_nearby_score = 0
        for container in soup.find_all(["div", "section", "article", "li", "tr", "span", "a", "p"]):
            text = container.get_text(separator="\n", strip=True)
            if not text or len(text) < 10:
                continue
            text_clean = re.sub(r"[\s（）()]+", "", text)
            if title_norm in text_clean:
                # 向上找父容器，提取更大范围的文本
                parent = container.parent
                search_scope = parent if parent else container
                parent_text = search_scope.get_text(separator="\n", strip=True)
                if len(parent_text) < 50:
                    continue
                hits = len(_JD_KEYWORDS.findall(parent_text))
                score = hits * 10 + min(len(parent_text), 3000) / 100
                if score > best_nearby_score:
                    best_nearby_score = score
                    best_nearby = parent_text

        if best_nearby and len(best_nearby) >= 80:
            return _clean_text(best_nearby)

    # ---- 策略 2: 找含 JD 关键词最多的容器 ----
    best_block = None
    best_score = 0
    for container in soup.find_all(["div", "section", "article", "main"]):
        text = container.get_text(separator="\n", strip=True)
        if len(text) < 50:
            continue
        hits = len(_JD_KEYWORDS.findall(text))
        score = hits * 10 + min(len(text), 3000) / 100
        if score > best_score:
            best_score = score
            best_block = text

    if best_block and len(best_block) >= 80:
        return _clean_text(best_block)

    # ---- 策略 3: 回退到整页文本 ----
    full_text = soup.get_text(separator="\n", strip=True)
    if full_text:
        return _clean_text(full_text)

    return None


def _llm_extract_jd(job_title: str, page_text: str) -> tuple[str, Optional[str]]:
    """用 LLM 从页面文本中提取特定岗位的 JD。

    返回 (description, requirements)。
    description 包含岗位职责等核心内容，requirements 包含任职要求。
    如果 LLM 无法区分，requirements 返回 None。
    """
    from ..llm import ask, ask_json, LLMError

    # 截断过长的文本以避免超出 token 限制
    truncated = page_text[:8000]

    prompt = (
        f"以下是从一个公司招聘页面提取的文本。页面中可能包含多个岗位的信息。\n"
        f"请找到岗位「{job_title}」的招聘信息，提取该岗位的 JD（职位描述）。\n\n"
        f"请返回 JSON 格式，包含以下字段：\n"
        f"- description: 岗位职责和工作内容的描述\n"
        f"- requirements: 任职要求/资格条件（如果没有则返回空字符串）\n\n"
        f"要求：\n"
        f"1. 只提取「{job_title}」这个岗位的信息，不要混入其他岗位\n"
        f"2. 去掉页面导航、广告、公司介绍等无关内容\n"
        f"3. 保持原始信息的完整性，不要编造内容\n"
        f"4. 如果页面中没有找到该岗位的信息，description 返回空字符串\n\n"
        f"页面文本：\n{truncated}"
    )

    try:
        result = ask_json(
            prompt,
            system="你是招聘信息提取助手。请从页面文本中提取指定岗位的 JD 信息，返回合法 JSON。",
        )
        description = result.get("description", "").strip() if isinstance(result, dict) else ""
        requirements = result.get("requirements", "").strip() if isinstance(result, dict) else ""

        if not description:
            return "", None

        # 如果 requirements 为空，设为 None
        requirements = requirements if requirements else None
        return description, requirements
    except LLMError as e:
        logger.warning("LLM JSON 提取失败，尝试纯文本模式: %s", e)
    except Exception as e:
        logger.warning("LLM JSON 提取异常: %s", e)

    # 回退到纯文本模式
    prompt_text = (
        f"以下是从一个公司招聘页面提取的文本，页面中可能包含多个岗位。\n"
        f"请找到岗位「{job_title}」的招聘信息，提取该岗位的 JD（职位描述）。\n"
        f"包括：岗位职责、任职要求、薪资福利等。去掉无关的页面导航、广告等内容。\n"
        f"保持原始信息的完整性，用简洁清晰的格式输出。\n"
        f"如果页面中没有找到该岗位的信息，请回复「未找到」。\n\n"
        f"页面文本：\n{truncated}"
    )

    try:
        result = ask(
            prompt_text,
            system="你是招聘信息整理助手，请提取指定岗位的 JD 核心内容。",
            temperature=0.3,
        )
        if "未找到" in result:
            return "", None
        return result.strip(), None
    except (LLMError, Exception) as e:
        logger.warning("LLM 纯文本提取也失败: %s", e)
        return "", None


@router.post("/{job_id}/fetch-jd")
def fetch_jd(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    """从岗位的网申链接抓取特定岗位的 JD 内容。

    改进点：
    - Playwright 作为主要方式（支持 JS 渲染和交互）
    - 在页面上搜索特定职位标题，提取该岗位的 JD
    - 用 LLM 从页面文本中提取特定岗位的 JD（职责 + 要求）
    - 保存到 description 和 requirements 字段
    """
    job = db.query(Job).filter(Job.id == job_id, Job.group_id == group.id).first()
    if not job:
        raise HTTPException(404, "岗位不存在")
    if not job.url:
        raise HTTPException(400, "该岗位没有网申链接，无法抓取")

    job_title = job.title.strip()
    page_text: Optional[str] = None

    # 1. 优先用 Playwright（支持 JS 渲染 + 交互式职位搜索）
    try:
        page_text = _playwright_fetch_jd(job.url, job_title)
    except Exception as e:
        logger.warning("Playwright 抓取失败 %s: %s", job.url, e)

    # 2. Playwright 失败或结果太短，用 httpx 作为后备
    if not page_text or len(page_text) < 50:
        html = _fetch_html_httpx(job.url)
        if html:
            # 检测 WAF
            if not any(marker in html for marker in _WAF_MARKERS):
                page_text = _extract_jd_from_html(html, job_title)
            else:
                logger.info("httpx 检测到 WAF，跳过")

    # 3. 两种方式都失败
    if not page_text or len(page_text) < 20:
        raise HTTPException(
            502,
            "无法访问该链接或未能提取到有效内容（Playwright 和 httpx 均失败）",
        )

    # 4. 用 LLM 从页面文本中提取特定岗位的 JD
    description, requirements = _llm_extract_jd(job_title, page_text)

    # 5. LLM 提取失败，回退到原始提取的文本
    if not description:
        description = page_text[:3000]
        if len(page_text) > 3000:
            description += "\n\n…（内容过长已截断）"
        logger.info("LLM 未提取到特定岗位 JD，使用原始页面文本")

    # 6. 保存
    job.description = description
    if requirements:
        job.requirements = requirements
    db.commit()

    return {
        "ok": True,
        "description": description,
        "requirements": requirements,
    }
