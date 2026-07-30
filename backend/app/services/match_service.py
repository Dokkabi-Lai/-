"""匹配与内容生成服务。

- match_job: 秋招岗位匹配分析
- optimize_resume: 针对岗位优化简历建议
- generate_self_intro: 生成自我介绍
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from ..llm import ask, ask_json, LLMError
from ..models import AICache, Job, Preference, Resume


def _hash_prompt(prompt: str) -> str:
    return hashlib.md5(prompt.encode("utf-8")).hexdigest()


def _get_cache(db: Session, kind: str, target_id: int, prompt: str) -> str | None:
    row = db.query(AICache).filter_by(
        kind=kind, target_id=target_id, prompt_hash=_hash_prompt(prompt)
    ).first()
    return row.result if row else None


def _save_cache(db: Session, kind: str, target_id: int, prompt: str, result: str):
    cache = AICache(
        kind=kind, target_id=target_id,
        prompt_hash=_hash_prompt(prompt), result=result,
    )
    db.add(cache)
    db.commit()


def _get_resume_text(db: Session, user_id: int | None = None) -> str:
    q = db.query(Resume)
    if user_id is not None:
        resume = q.filter_by(is_default=True, user_id=user_id).first() or q.filter(Resume.user_id == user_id).first()
    else:
        resume = q.filter_by(is_default=True).first() or q.first()
    return (resume.raw_text or "") if resume else ""


def _get_preference_text(db: Session, user_id: int | None = None) -> str:
    q = db.query(Preference)
    if user_id is not None:
        pref = q.filter(Preference.user_id == user_id).first()
    else:
        pref = q.first()
    if not pref:
        return "未设置偏好。"
    parts = []
    if pref.desired_locations:
        parts.append(f"期望地区: {', '.join(pref.desired_locations)}")
    if pref.desired_job_types:
        parts.append(f"期望岗位: {', '.join(pref.desired_job_types)}")
    if pref.desired_industries:
        parts.append(f"期望行业: {', '.join(pref.desired_industries)}")
    if pref.min_salary:
        parts.append(f"最低期望薪资: {pref.min_salary}K")
    return "\n".join(parts) or "未设置偏好。"


# ---------- 秋招匹配 ----------

def match_job(db: Session, job_id: int, use_ai: bool = True, user_id: int | None = None) -> dict[str, Any]:
    """对秋招岗位做匹配分析，返回结构化结果。

    use_ai=True 用大模型分析；use_ai=False 用规则匹配（不花钱）。
    """
    job = db.query(Job).get(job_id)
    if not job:
        raise ValueError("岗位不存在")

    resume_text = _get_resume_text(db, user_id)
    pref_q = db.query(Preference)
    if user_id is not None:
        pref = pref_q.filter(Preference.user_id == user_id).first()
    else:
        pref = pref_q.first()

    # 获取AI推荐投递职位
    resume_q = db.query(Resume)
    if user_id is not None:
        resume = resume_q.filter_by(is_default=True, user_id=user_id).first() or resume_q.filter(Resume.user_id == user_id).first()
    else:
        resume = resume_q.filter_by(is_default=True).first() or resume_q.first()
    rec_positions = (resume.structured or {}).get("recommended_positions") if resume else None

    # 规则匹配（始终先做，作为基础）
    rule_result = _rule_match_job(job, resume_text, pref, recommended_positions=rec_positions)

    if not use_ai:
        return rule_result

    # AI 深度分析
    pref_text = _get_preference_text(db, user_id)
    prompt = f"""请分析求职者与该岗位的匹配度，返回 JSON：
{{
  "score": 0-100 的整数,
  "match_points": ["匹配点1", "匹配点2"],
  "gaps": ["差距点1", "差距点2"],
  "required_skills": [{{"skill": "技能名", "has": true/false}}],
  "pros": ["优势1"],
  "cons": ["劣势1"],
  "summary": "一句话总结"
}}

求职者简历：
{resume_text[:2000]}

求职者偏好：
{pref_text}

岗位信息：
公司: {job.company}
岗位: {job.title}
地点: {job.location}
薪资: {job.salary}
要求: {job.requirements or job.description or '无'}
"""
    cached = _get_cache(db, "match", job_id, prompt)
    if cached:
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            pass

    try:
        result = ask_json(prompt, system="你是求职匹配分析助手，请只返回 JSON。")
    except LLMError as e:
        # AI 失败时回退到规则匹配结果
        rule_result["ai_error"] = str(e)
        return rule_result

    _save_cache(db, "match", job_id, prompt, json.dumps(result, ensure_ascii=False))
    return result


def _rule_match_job(job, resume_text: str, pref, recommended_positions: list[str] | None = None) -> dict[str, Any]:
    """规则匹配：基于偏好和简历关键词，不调用大模型。"""
    score = 50
    match_points = []
    gaps = []
    pros = []
    cons = []

    # 推荐投递职位匹配
    if recommended_positions:
        job_text = (job.title or "") + " " + (job.description or "")
        for pos in recommended_positions:
            if pos in job_text:
                score += 20
                match_points.append(f"AI推荐职位匹配: {pos}")
                break

    # 地区匹配
    if pref and pref.desired_locations and job.location:
        for loc in pref.desired_locations:
            if loc in job.location:
                score += 15
                match_points.append(f"地点匹配: {loc}")
                break
        else:
            score -= 10
            gaps.append(f"地点可能不符: 岗位在{job.location}，你期望{','.join(pref.desired_locations)}")

    # 岗位类型匹配
    if pref and pref.desired_job_types and job.title:
        for jt in pref.desired_job_types:
            if jt in job.title or jt in (job.description or ""):
                score += 15
                match_points.append(f"岗位类型匹配: {jt}")
                break

    # 薪资匹配
    if pref and pref.min_salary and job.salary:
        import re
        m = re.search(r"(\d+)", job.salary)
        if m and int(m.group(1)) >= pref.min_salary:
            score += 10
            pros.append(f"薪资符合预期")
        elif m and int(m.group(1)) < pref.min_salary:
            score -= 5
            cons.append(f"薪资可能偏低")

    # 简历关键词匹配
    if resume_text and job.requirements:
        req_keywords = [w.strip() for w in job.requirements.replace("，", ",").replace("、", ",").split(",") if len(w.strip()) > 1]
        has_skills = []
        miss_skills = []
        for kw in req_keywords[:10]:
            if kw in resume_text:
                has_skills.append(kw)
            else:
                miss_skills.append(kw)
        if has_skills:
            score += len(has_skills) * 3
            match_points.append(f"已具备技能: {','.join(has_skills[:5])}")
        if miss_skills:
            gaps.append(f"可能需要补充: {','.join(miss_skills[:5])}")

    score = max(0, min(100, score))
    return {
        "score": score,
        "match_points": match_points or ["基础匹配"],
        "gaps": gaps,
        "required_skills": [],
        "pros": pros,
        "cons": cons,
        "summary": f"规则匹配度 {score} 分" + ("（点击AI深度分析获取详细建议）" if not gaps else ""),
        "mode": "rule",
    }


# ---------- 简历优化 ----------

def optimize_resume(db: Session, job_id: int, user_id: int | None = None) -> dict[str, Any]:
    """针对指定岗位给出简历优化建议。"""
    job = db.query(Job).get(job_id)
    if not job:
        raise ValueError("岗位不存在")

    resume_text = _get_resume_text(db, user_id)
    if not resume_text:
        return {"suggestions": ["请先上传简历"], "optimized_items": []}

    prompt = f"""请针对该岗位分析简历并给出优化建议，返回 JSON：
{{
  "overall_comment": "总体评价",
  "suggestions": ["建议1", "建议2"],
  "optimized_items": [
    {{"section": "项目经历", "original": "原文关键句", "improved": "优化后的表述", "reason": "优化原因"}}
  ],
  "keywords_to_add": ["应补充的关键词"]
}}

简历内容：
{resume_text[:3000]}

岗位信息：
公司: {job.company}
岗位: {job.title}
要求: {job.requirements or job.description or '无'}
"""
    cached = _get_cache(db, "resume_optimize", job_id, prompt)
    if cached:
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            pass

    try:
        result = ask_json(prompt, system="你是专业的简历优化顾问，请只返回 JSON。")
    except LLMError as e:
        return {"suggestions": [f"AI 服务暂不可用: {e}"], "optimized_items": []}

    _save_cache(db, "resume_optimize", job_id, prompt, json.dumps(result, ensure_ascii=False))
    return result


# ---------- 自我介绍生成 ----------

def generate_self_intro(db: Session, job_id: int, style: str = "正式", user_id: int | None = None) -> dict:
    """为指定岗位生成自我介绍。"""
    job = db.query(Job).get(job_id)
    if not job:
        raise ValueError("岗位不存在")

    resume_text = _get_resume_text(db, user_id)

    prompt = f"""请为面试生成一段自我介绍，返回 JSON：
{{
  "intro": "自我介绍全文（300字左右）",
  "key_points": ["要强调的点1", "要强调的点2"],
  "tips": ["注意事项1"]
}}

风格要求: {style}（正式/轻松/技术型）

简历：
{resume_text[:2000]}

面试岗位：
公司: {job.company}
岗位: {job.title}
要求: {job.requirements or job.description or '无'}
"""
    cached = _get_cache(db, "intro", job_id, prompt)
    if cached:
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            pass

    try:
        result = ask_json(prompt, system="你是面试辅导教练，请只返回 JSON。")
    except LLMError as e:
        return {"intro": f"AI 服务暂不可用: {e}", "key_points": [], "tips": []}

    _save_cache(db, "intro", job_id, prompt, json.dumps(result, ensure_ascii=False))
    return result
