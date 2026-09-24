"""流程阶段的统一分类规则。"""
from __future__ import annotations

import re

from sqlalchemy import and_, func, or_


DEFAULT_APPLICATION_STAGES = ["投递", "简历筛选", "测评", "一面", "二面", "HR面", "Offer"]
LEGACY_DEFAULT_APPLICATION_STAGES = ["投递", "简历筛选", "笔试", "一面", "二面", "HR面", "Offer"]


def _normalized_stage_name(stage_name: str | None) -> str:
    return re.sub(r"\s+", "", stage_name or "").upper()


def is_assessment_stage(stage_name: str | None) -> bool:
    """测评、评测、笔试和 AI 面统一视为前期测评环节。"""
    normalized = _normalized_stage_name(stage_name)
    return bool(
        any(keyword in normalized for keyword in ("测评", "评测", "笔试"))
        or ("AI" in normalized and "面" in normalized)
    )


def is_interview_stage(stage_name: str | None) -> bool:
    """识别正式面试；AI 面明确排除在外。"""
    normalized = _normalized_stage_name(stage_name)
    return bool(normalized and not is_assessment_stage(normalized) and "面" in normalized)


def stage_statistics_bucket(stage_name: str | None) -> str:
    """把自定义流程名称归并到稳定的统计类别。"""
    if is_assessment_stage(stage_name):
        return "测评"
    if is_interview_stage(stage_name):
        return "面试"
    return (stage_name or "其他").strip() or "其他"


def assessment_stage_filter(column):
    """返回可用于 SQLAlchemy 查询的测评类阶段条件。"""
    return or_(
        column.like("%测评%"),
        column.like("%评测%"),
        column.like("%笔试%"),
        and_(func.upper(column).like("%AI%"), column.like("%面%")),
    )
