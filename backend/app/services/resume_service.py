"""简历解析服务：从 PDF/Word 提取文本，再用 LLM 解析为结构化数据。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import BASE_DIR, get_settings
from ..llm import ask_json, LLMError


def extract_text_from_pdf(path: Path) -> str:
    from PyPDF2 import PdfReader
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def extract_text_from_docx(path: Path) -> str:
    from docx import Document
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(path)
    if suffix in (".docx", ".doc"):
        return extract_text_from_docx(path)
    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="ignore")
    raise ValueError(f"不支持的文件格式: {suffix}")


def parse_resume(text: str) -> dict[str, Any]:
    """用 LLM 把简历文本解析为结构化数据。"""
    prompt = f"""请解析以下简历，提取结构化信息，返回 JSON。
字段包括：
- name: 姓名
- phone: 电话
- email: 邮箱
- education: 最高学历（本科/硕士/博士）
- school: 毕业院校
- major: 专业
- graduation_date: 毕业时间
- skills: 技能列表（数组）
- projects: 项目经历列表，每项含 name/description/role
- internships: 实习经历列表，每项含 company/role/duration/description
- awards: 获奖列表
- certifications: 证书列表
- self_summary: 自我总结（如有）

简历内容：
{text}
"""
    try:
        return ask_json(prompt, system="你是一个简历解析助手，请只返回 JSON。")
    except LLMError:
        # 解析失败时至少保留原文
        return {"raw_text": text, "_parse_error": True}


def save_resume_file(file_bytes: bytes, filename: str) -> Path:
    settings = get_settings()
    resume_dir = BASE_DIR / settings.storage.resume_dir
    resume_dir.mkdir(parents=True, exist_ok=True)
    # 用时间戳避免重名
    import time
    safe_name = f"{int(time.time())}_{filename}"
    path = resume_dir / safe_name
    path.write_bytes(file_bytes)
    return path
