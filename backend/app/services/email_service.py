"""邮箱验证码服务：通过 SMTP 发送真实邮件。"""
from __future__ import annotations

import logging
import random
import re
import smtplib
from datetime import datetime, timedelta
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import EmailVerification

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(normalize_email(email)))


def generate_code(length: int = 6) -> str:
    return "".join(str(random.randint(0, 9)) for _ in range(length))


def _build_message(to_email: str, code: str) -> MIMEMultipart:
    settings = get_settings()
    smtp = settings.email.smtp
    app_name = settings.app.name

    msg = MIMEMultipart("alternative")
    from_addr = smtp.from_addr or smtp.username
    msg["From"] = formataddr((str(Header(smtp.from_name or app_name, "utf-8")), from_addr))
    msg["To"] = to_email
    msg["Subject"] = Header(f"【{app_name}】登录验证码", "utf-8")

    text = (
        f"你好，\n\n"
        f"你正在登录 {app_name}，验证码为：{code}\n"
        f"验证码 {settings.email.code_ttl // 60} 分钟内有效，请勿泄露给他人。\n\n"
        f"如非本人操作，请忽略此邮件。"
    )
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:24px;">
      <h2 style="color:#333;">{app_name}</h2>
      <p>你正在登录，验证码为：</p>
      <p style="font-size:32px;font-weight:bold;letter-spacing:8px;color:#0066ff;">{code}</p>
      <p style="color:#666;font-size:14px;">验证码 {settings.email.code_ttl // 60} 分钟内有效，请勿泄露给他人。</p>
      <p style="color:#999;font-size:12px;">如非本人操作，请忽略此邮件。</p>
    </div>
    """
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    return msg


def send_email_code(to_email: str, code: str) -> None:
    settings = get_settings()
    smtp = settings.email.smtp
    if not smtp.host or not smtp.username or not smtp.password:
        raise RuntimeError("邮件服务未配置，请在 config.yaml 中填写 SMTP 信息")

    msg = _build_message(to_email, code)
    from_addr = smtp.from_addr or smtp.username

    try:
        if smtp.use_ssl:
            server = smtplib.SMTP_SSL(smtp.host, smtp.port, timeout=20)
        else:
            server = smtplib.SMTP(smtp.host, smtp.port, timeout=20)
            if smtp.use_tls:
                server.starttls()
        server.login(smtp.username, smtp.password)
        server.sendmail(from_addr, [to_email], msg.as_string())
        server.quit()
        logger.info("验证码邮件已发送至 %s", to_email)
    except smtplib.SMTPException as e:
        logger.exception("邮件发送失败: %s", to_email)
        raise RuntimeError(f"邮件发送失败：{e}") from e


def can_send_code(db: Session, email: str) -> int | None:
    settings = get_settings()
    since = datetime.utcnow() - timedelta(seconds=settings.email.send_interval)
    recent = (
        db.query(EmailVerification)
        .filter(EmailVerification.email == email, EmailVerification.created_at >= since)
        .order_by(EmailVerification.created_at.desc())
        .first()
    )
    if not recent:
        return None
    elapsed = (datetime.utcnow() - recent.created_at).total_seconds()
    remain = max(0, int(settings.email.send_interval - elapsed))
    return remain or None


def create_and_send_code(db: Session, email: str) -> str:
    settings = get_settings()
    email = normalize_email(email)
    remain = can_send_code(db, email)
    if remain:
        raise ValueError(f"请 {remain} 秒后再试")

    code = generate_code(settings.email.code_length)
    expires_at = datetime.utcnow() + timedelta(seconds=settings.email.code_ttl)
    db.add(EmailVerification(email=email, code=code, expires_at=expires_at))
    db.commit()

    send_email_code(email, code)
    return code


def verify_code(db: Session, email: str, code: str) -> bool:
    email = normalize_email(email)
    code = code.strip()
    if not code:
        return False

    now = datetime.utcnow()
    record = (
        db.query(EmailVerification)
        .filter(
            EmailVerification.email == email,
            EmailVerification.code == code,
            EmailVerification.used.is_(False),
            EmailVerification.expires_at >= now,
        )
        .order_by(EmailVerification.created_at.desc())
        .first()
    )
    if not record:
        return False

    record.used = True
    db.commit()
    return True
