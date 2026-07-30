"""简历与偏好接口。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..llm import ask_json, LLMError
from ..models import Preference, Resume, User, get_db
from ..services.resume_service import extract_text, parse_resume, save_resume_file
from .deps import get_current_user

router = APIRouter(prefix="/api/resume", tags=["resume"])


class ResumeOut(BaseModel):
    id: int
    name: str
    is_default: bool
    has_text: bool

    class Config:
        from_attributes = True


class PreferenceIn(BaseModel):
    desired_locations: Optional[list[str]] = None
    desired_job_types: Optional[list[str]] = None
    desired_industries: Optional[list[str]] = None
    min_salary: Optional[int] = None
    max_company_size: Optional[str] = None


def _serialize_resume(r: Resume) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "is_default": r.is_default,
        "has_text": bool(r.raw_text),
        "structured": r.structured,
    }


@router.get("/list")
def list_resumes(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Resume).filter(Resume.user_id == user.id).all()
    return [_serialize_resume(r) for r in rows]


@router.post("/upload")
async def upload_resume(
    file: UploadFile = File(...),
    name: str = "默认简历",
    use_ai: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """上传简历文件并提取文本。use_ai=true 时用大模型解析结构化数据（可选）。"""
    if not file.filename:
        raise HTTPException(400, "未提供文件")
    content = await file.read()
    path = save_resume_file(content, file.filename)
    try:
        text = extract_text(path)
    except Exception as e:
        raise HTTPException(400, f"文件解析失败: {e}")

    structured = parse_resume(text) if use_ai else None

    db.query(Resume).filter(Resume.is_default == True, Resume.user_id == user.id).update({Resume.is_default: False})
    resume = Resume(name=name, file_path=str(path), raw_text=text, structured=structured, is_default=True, user_id=user.id)
    db.add(resume)
    db.commit()
    return _serialize_resume(resume)


@router.post("/{resume_id}/default")
def set_default(resume_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == user.id).first()
    if not r:
        raise HTTPException(404, "简历不存在")
    db.query(Resume).filter(Resume.is_default == True, Resume.user_id == user.id).update({Resume.is_default: False})
    r.is_default = True
    db.commit()
    return {"ok": True}


@router.delete("/{resume_id}")
def delete_resume(resume_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == user.id).first()
    if not r:
        raise HTTPException(404, "简历不存在")
    db.delete(r)
    db.commit()
    return {"ok": True}


class ManualResumeCreate(BaseModel):
    name: str = "手动简历"
    raw_text: str = ""


class ManualResumeUpdate(BaseModel):
    name: Optional[str] = None
    raw_text: Optional[str] = None


@router.post("/manual")
def create_manual_resume(data: ManualResumeCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """手动创建简历（不上传文件，自己填写文本内容）。"""
    db.query(Resume).filter(Resume.is_default == True, Resume.user_id == user.id).update({Resume.is_default: False})
    r = Resume(name=data.name, raw_text=data.raw_text, is_default=True, user_id=user.id)
    db.add(r)
    db.commit()
    return _serialize_resume(r)


@router.patch("/{resume_id}/text")
def update_resume_text(resume_id: int, data: ManualResumeUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """手动编辑简历文本内容。"""
    r = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == user.id).first()
    if not r:
        raise HTTPException(404, "简历不存在")
    if data.name is not None:
        r.name = data.name
    if data.raw_text is not None:
        r.raw_text = data.raw_text
    db.commit()
    return _serialize_resume(r)


@router.get("/{resume_id}/text")
def get_resume_text(resume_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取简历纯文本。"""
    r = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == user.id).first()
    if not r:
        raise HTTPException(404, "简历不存在")
    return {"id": r.id, "name": r.name, "raw_text": r.raw_text or ""}


@router.get("/preference")
def get_preference(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.query(Preference).filter(Preference.user_id == user.id).first()
    if not p:
        return {}
    return {
        "desired_locations": p.desired_locations,
        "desired_job_types": p.desired_job_types,
        "desired_industries": p.desired_industries,
        "min_salary": p.min_salary,
        "max_company_size": p.max_company_size,
    }


@router.post("/preference")
def set_preference(data: PreferenceIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.query(Preference).filter(Preference.user_id == user.id).first()
    if not p:
        p = Preference(user_id=user.id)
        db.add(p)
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    db.commit()
    return {"ok": True}


# ---------- 简历AI分析 ----------

@router.post("/{resume_id}/analyze")
def analyze_resume(resume_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """用大模型分析简历，返回结构化解析结果。"""
    r = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == user.id).first()
    if not r:
        raise HTTPException(404, "简历不存在")
    if not r.raw_text:
        raise HTTPException(400, "简历内容为空")

    prompt = f"""你是一位资深的人力资源专家和职业规划顾问，拥有10年以上的校招经验。请对以下简历进行深度专业分析，返回 JSON：

{{
  "summary": "一句话总体评价（包括求职者的核心竞争力和定位）",
  "skills": ["技能1", "技能2", "..."],
  "skill_analysis": [
    {{"skill": "技能名", "level": "了解/熟悉/精通", "evidence": "简历中的依据"}}
  ],
  "education": "最高学历，如 本科-计算机科学-XX大学",
  "education_detail": "教育背景详细描述，包括学校层次(985/211/双非等)、GPA、相关课程等",
  "experience_years": 0,
  "projects": [
    {{"name": "项目名", "role": "担任角色", "description": "项目简述", "highlights": ["亮点1", "亮点2"], "tech_stack": ["用到的技术"]}}
  ],
  "internships": [
    {{"company": "公司名", "role": "岗位", "duration": "时长", "description": "工作内容简述"}}
  ],
  "strengths": [
    {{"point": "优势点", "evidence": "简历中的具体依据", "impact": "对求职的帮助"}}
  ],
  "weaknesses": [
    {{"point": "不足点", "suggestion": "改进建议"}}
  ],
  "suitable_roles": ["适合的岗位类型1", "岗位类型2"],
  "recommended_positions": ["具体可投递的职位关键词1", "职位关键词2"],
  "suggested_industries": ["适合的行业1"],
  "career_direction": "职业发展方向建议（如：建议走技术路线/产品路线/管理等）",
  "market_competitiveness": "在当前校招市场中的竞争力评估（高/中/低）及原因分析",
  "improvement_suggestions": [
    {{"aspect": "改进方面(如：项目经历/技能/实习/表达)", "current": "当前问题", "suggestion": "具体改进建议", "priority": "高/中/低"}}
  ],
  "interview_prep": ["面试中可能被问到的重点问题1", "问题2"],
  "salary_expectation": "合理的薪资期望范围（K），基于学历、技能、经验综合判断"
}}

分析要求：
1. recommended_positions 是具体的、可直接用于搜索投递的职位名称/关键词，例如 "Java后端开发"、"Python开发工程师"、"数据平台工程师"等，至少给出5-8个
2. skill_analysis 要对每项技能给出熟练度评级和简历中的依据
3. strengths 和 weaknesses 要有具体证据支撑，不要泛泛而谈
4. improvement_suggestions 要分优先级，给出可执行的具体建议
5. interview_prep 要基于简历内容预测面试官可能提问的方向
6. salary_expectation 要结合市场行情给出合理范围
7. 整体分析要专业、客观、有建设性

简历内容：
{r.raw_text[:4000]}
"""
    try:
        result = ask_json(prompt, system="你是专业的简历分析师，请只返回 JSON。")
        # 保存结构化数据到简历
        r.structured = result
        db.commit()
        return result
    except LLMError as e:
        raise HTTPException(500, f"AI分析失败: {e}")


class PositionsIn(BaseModel):
    positions: list[str]


@router.post("/analysis/positions")
def save_recommended_positions(data: PositionsIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """保存用户编辑后的推荐投递职位到默认简历的 structured 字段。"""
    resume = db.query(Resume).filter_by(is_default=True, user_id=user.id).first()
    if not resume:
        raise HTTPException(404, "未找到默认简历")
    structured = resume.structured or {}
    structured["recommended_positions"] = data.positions
    resume.structured = structured
    # SQLAlchemy 可能不会检测到 dict 内部变化，显式标记
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(resume, "structured")
    db.commit()
    return {"ok": True, "positions": data.positions}


# ---------- 问答式偏好识别 ----------

@router.post("/preference/chat")
def preference_chat(body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """基于对话上下文，用AI分析用户回答并更新偏好。
    body: { messages: [{role, content}], resume_text: "可选简历文本" }
    返回: { reply, preference: {desired_locations, desired_job_types, desired_industries, min_salary} }
    """
    messages = body.get("messages", [])
    resume_text = body.get("resume_text", "")

    # 构建对话历史
    conversation = "\n".join([f"{'用户' if m['role']=='user' else '助手'}: {m['content']}" for m in messages[-10:]])

    prompt = f"""你是一个求职顾问助手，正在通过对话了解用户的求职偏好。

对话历史：
{conversation}

{f"用户简历摘要：{resume_text[:500]}" if resume_text else ""}

请根据对话，返回 JSON：
{{
  "reply": "你的下一句回复（友好、简洁，每次只问一个问题）",
  "is_complete": false,
  "preference": {{
    "desired_locations": ["已明确的城市列表，未明确则为空数组"],
    "desired_job_types": ["已明确的岗位类型"],
    "desired_industries": ["已明确的行业"],
    "min_salary": null
  }}
}}

规则：
- 如果用户还没提供足够信息，reply 中继续问一个问题，is_complete=false
- 如果已经了解了地点、岗位、行业中的至少2项，可以 is_complete=true，reply 中总结偏好
- 每次只问一个问题，不要一次问太多
- 语气友好自然，像朋友聊天
"""
    try:
        result = ask_json(prompt, system="你是求职顾问，请只返回 JSON。")

        # 如果对话完成，自动保存偏好
        if result.get("is_complete") and result.get("preference"):
            pref = result["preference"]
            p = db.query(Preference).filter(Preference.user_id == user.id).first()
            if not p:
                p = Preference(user_id=user.id)
                db.add(p)
            if pref.get("desired_locations"):
                p.desired_locations = pref["desired_locations"]
            if pref.get("desired_job_types"):
                p.desired_job_types = pref["desired_job_types"]
            if pref.get("desired_industries"):
                p.desired_industries = pref["desired_industries"]
            if pref.get("min_salary"):
                p.min_salary = pref["min_salary"]
            db.commit()

        return result
    except LLMError as e:
        raise HTTPException(500, f"AI服务暂不可用: {e}")
