"""爬虫基类。"""
from __future__ import annotations

import random
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup

from ..models import SpiderLog


USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]


@dataclass
class SpiderResult:
    source: str
    status: str = "success"
    count: int = 0
    message: str = ""
    items: list[dict[str, Any]] = field(default_factory=list)


class BaseSpider:
    """爬虫基类。子类实现 run()。"""

    name: str = "base"
    item_type: str = "job"

    def __init__(self):
        self.client = httpx.Client(
            headers={"User-Agent": random.choice(USER_AGENTS)},
            timeout=30.0,
            follow_redirects=True,
        )

    def fetch_html(self, url: str) -> str:
        """抓取页面 HTML。优先用 curl（能过 WAF），失败回退 httpx。"""
        time.sleep(random.uniform(1.0, 3.0))
        try:
            result = subprocess.run(
                ["curl", "-s", "-L", "--max-time", "30",
                 "-H", f"User-Agent: {random.choice(USER_AGENTS)}",
                 url],
                capture_output=True, text=True, timeout=35,
            )
            html = result.stdout
            if len(html) > 5000 and "waf" not in html.lower()[:500]:
                return html
        except Exception:
            pass
        resp = self.client.get(url)
        resp.raise_for_status()
        return resp.text

    def fetch_bytes(self, url: str) -> bytes:
        """下载二进制内容（Excel/zip 等）。"""
        time.sleep(random.uniform(1.0, 3.0))
        try:
            result = subprocess.run(
                ["curl", "-s", "-L", "--max-time", "60",
                 "-H", f"User-Agent: {random.choice(USER_AGENTS)}",
                 url],
                capture_output=True, timeout=65,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except Exception:
            pass
        resp = self.client.get(url)
        resp.raise_for_status()
        return resp.content

    def fetch_json(self, url: str, **kwargs) -> dict:
        time.sleep(random.uniform(1.0, 3.0))
        resp = self.client.get(url, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    def run(self) -> SpiderResult:
        raise NotImplementedError

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def log_spider(db, result: SpiderResult):
    db.add(SpiderLog(
        source=result.source,
        status=result.status,
        count=result.count,
        message=result.message,
    ))
    db.commit()
