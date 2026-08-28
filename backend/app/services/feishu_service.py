"""从飞书电子表格同步岗位。"""
from __future__ import annotations

import logging
import re
import datetime as dt
from typing import Optional

import httpx

from ..config import get_settings
from ..models import Group, SyncState, get_sessionmaker
from .excel_import_service import import_job_items, parse_value_rows

logger = logging.getLogger(__name__)

TOKEN_RE = re.compile(r"/(?:sheets|wiki)/([A-Za-z0-9]+)")


def extract_spreadsheet_token(raw: str) -> str:
    text = (raw or "").strip()
    m = TOKEN_RE.search(text)
    return m.group(1) if m else text


def is_configured() -> bool:
    cfg = get_settings().jobs.feishu
    return bool(cfg.app_id and cfg.app_secret and cfg.spreadsheet_token)


def _tenant_token() -> str:
    cfg = get_settings().jobs.feishu
    with httpx.Client(timeout=20) as client:
        resp = client.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": cfg.app_id, "app_secret": cfg.app_secret},
        )
        resp.raise_for_status()
        data = resp.json()
    if data.get("code") not in (0, None) and not data.get("tenant_access_token"):
        raise RuntimeError(data.get("msg") or "获取飞书 token 失败")
    token = data.get("tenant_access_token")
    if not token:
        raise RuntimeError("飞书未返回 tenant_access_token，请检查 App ID / Secret")
    return token


def _first_sheet_id(client: httpx.Client, token: str, spreadsheet_token: str, preferred: str) -> str:
    if preferred:
        return preferred
    resp = client.get(
        f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/metainfo",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(data.get("msg") or "读取飞书表格信息失败")
    sheets = (data.get("data") or {}).get("sheets") or []
    if not sheets:
        raise RuntimeError("飞书表格没有工作表")
    return sheets[0].get("sheetId") or sheets[0].get("sheet_id")


def fetch_sheet_rows(
    spreadsheet_value: Optional[str] = None,
    preferred_sheet_id: Optional[str] = None,
) -> tuple[list, list[list]]:
    cfg = get_settings().jobs.feishu
    spreadsheet_token = extract_spreadsheet_token(spreadsheet_value or cfg.spreadsheet_token)
    tenant = _tenant_token()
    with httpx.Client(timeout=40) as client:
        sheet_id = _first_sheet_id(
            client, tenant, spreadsheet_token, preferred_sheet_id if preferred_sheet_id is not None else cfg.sheet_id
        )
        values: list[list] = []
        page_size = 2000
        for start in range(1, 50001, page_size):
            end = start + page_size - 1
            resp = client.get(
                f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/values/{sheet_id}!A{start}:L{end}",
                headers={"Authorization": f"Bearer {tenant}"},
                params={"valueRenderOption": "ToString", "dateTimeRenderOption": "FormattedString"},
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(data.get("msg") or "读取飞书表格内容失败")
            page = ((data.get("data") or {}).get("valueRange") or {}).get("values") or []
            values.extend(page)
            if len(page) < page_size:
                break
    if not values:
        raise RuntimeError("飞书表格是空的")
    return values[0], values[1:]


def _save_state(
    db,
    status: str,
    result: Optional[dict] = None,
    message: str = "",
    group_id: Optional[int] = None,
) -> None:
    source_key = f"feishu:{group_id}" if group_id else "feishu"
    state = db.query(SyncState).filter(SyncState.source == source_key).first()
    if not state:
        state = SyncState(source=source_key)
        db.add(state)
    result = result or {}
    state.status = status
    state.created_count = result.get("created", 0)
    state.updated_count = result.get("updated", 0)
    state.deactivated_count = result.get("deactivated", 0)
    state.message = message[:1000] or None
    state.synced_at = dt.datetime.now()
    db.commit()


def sync_jobs_from_feishu(db=None, group_id: Optional[int] = None) -> dict:
    cfg = get_settings().jobs.feishu
    if not (cfg.app_id and cfg.app_secret):
        raise RuntimeError("尚未配置飞书：请在 config.yaml 填写 app_id、app_secret、spreadsheet_token")
    own_session = db is None
    if own_session:
        db = get_sessionmaker()()
    try:
        group = db.get(Group, group_id) if group_id else None
        spreadsheet_value = (
            group.feishu_spreadsheet_token
            if group and group.feishu_spreadsheet_token
            else cfg.spreadsheet_token if not group or group.is_system else ""
        )
        sheet_id = (
            group.feishu_sheet_id
            if group and group.feishu_spreadsheet_token
            else cfg.sheet_id if not group or group.is_system else ""
        )
        if not spreadsheet_value:
            raise RuntimeError("当前群组尚未绑定飞书表格")
        header, rows = fetch_sheet_rows(spreadsheet_value, sheet_id)
        items = parse_value_rows(header, rows)
        if not items:
            raise RuntimeError("飞书表格里没有识别到岗位，请确认表头包含「公司」「岗位」")
        result = import_job_items(
            items,
            db=db,
            source_label="feishu",
            deactivate_missing=True,
            group_id=group_id,
        )
        result["source"] = "feishu"
        _save_state(db, "success", result, group_id=group_id)
        return result
    except Exception as exc:
        db.rollback()
        _save_state(db, "failed", message=str(exc), group_id=group_id)
        raise
    finally:
        if own_session:
            db.close()
