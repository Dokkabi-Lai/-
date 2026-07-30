"""牛客网校招日程爬虫。

数据源: https://www.nowcoder.com/jobs/school/schedule?tab=36 (26届秋招)
牛客有阿里云 WAF，httpx/curl 都被拦，必须用 Playwright 真实浏览器。

策略：
1. 列表页获取公司基本信息（名称、日期、地点、链接）
2. 对有企业详情页的公司，进入详情页提取「招聘岗位」字段
3. 将岗位类别拆分为子岗位，每个子岗位独立入库
"""
from __future__ import annotations

import datetime as dt
import re
from urllib.parse import unquote

from .base import BaseSpider, SpiderResult

LIST_URL = "https://www.nowcoder.com/jobs/school/schedule?tab=36"


def _parse_date_range(text: str) -> tuple[dt.date | None, dt.date | None]:
    """解析 '07月21日-10月19日' 或 '2026/07/21 ~ 2026/10/19' 格式。"""
    # 格式1: 07月21日-10月19日
    m = re.search(r"(\d{1,2})月(\d{1,2})日\s*-\s*(\d{1,2})月(\d{1,2})日", text)
    if m:
        year = dt.date.today().year
        try:
            open_d = dt.date(year, int(m.group(1)), int(m.group(2)))
            close_d = dt.date(year, int(m.group(3)), int(m.group(4)))
            if close_d < open_d:
                close_d = dt.date(year + 1, int(m.group(3)), int(m.group(4)))
            return open_d, close_d
        except ValueError:
            pass
    # 格式2: 2026/07/21 ~ 2026/10/19
    m2 = re.search(r"(\d{4})/(\d{2})/(\d{2})\s*~\s*(\d{4})/(\d{2})/(\d{2})", text)
    if m2:
        try:
            open_d = dt.date(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))
            close_d = dt.date(int(m2.group(4)), int(m2.group(5)), int(m2.group(6)))
            return open_d, close_d
        except ValueError:
            pass
    return None, None


def _clean_url(href: str) -> str:
    """从牛客跳转链接中提取真实 URL。"""
    url_match = re.search(r"url=([^&]+)", href)
    if url_match:
        return unquote(url_match.group(1))
    return href


def _split_roles(text: str) -> list[str]:
    """拆分 '运营、市场/营销、管理、后端开发' 为列表。"""
    if not text:
        return []
    # 先把换行替换为逗号
    text = text.replace("\n", "、").replace("\r", "")
    # 按中英文逗号、顿号拆分
    parts = re.split(r"[、，,;；]+", text.strip())
    return [p.strip() for p in parts if p.strip() and 1 < len(p.strip()) <= 20]


class NowcoderSpider(BaseSpider):
    name = "nowcoder"
    item_type = "job"

    def run(self) -> SpiderResult:
        result = SpiderResult(source=self.name)
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()

                # 1. 抓取列表页
                companies = self._fetch_list(page)
                result.message = f"列表页获取 {len(companies)} 家公司"

                # 2. 对有企业详情页的公司，进入详情页提取子岗位（限制最多15个以避免超时）
                items = []
                enterprise_count = 0
                max_enterprise_visits = 15
                for comp in companies:
                    enterprise_url = comp.get("enterprise_url")
                    if enterprise_url and enterprise_count < max_enterprise_visits:
                        enterprise_count += 1
                        sub_roles = self._fetch_enterprise_roles(page, enterprise_url)
                        if sub_roles:
                            # 为每个岗位类别创建独立记录
                            for role in sub_roles:
                                items.append({
                                    **comp,
                                    "source_id": f"{comp['company']}_{role}",
                                    "title": role,
                                })
                            continue
                    # 无法获取子岗位的，保留原始公司级记录
                    items.append(comp)

                browser.close()

                result.items = items
                result.count = len(items)
                if not items:
                    result.message = "未解析到岗位，页面结构可能变化"
                else:
                    result.message = f"共获取 {len(items)} 条岗位记录"
        except Exception as e:
            result.status = "failed"
            result.message = str(e)
        return result

    def _fetch_list(self, page) -> list[dict]:
        """抓取列表页，获取公司基本信息。"""
        page.goto(LIST_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_selector("ul.items-list li.list-item-box", timeout=10000)

        # 滚动加载更多
        last_count = 0
        for _ in range(10):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)
            current_count = page.evaluate(
                "document.querySelectorAll('ul.items-list li.list-item-box').length"
            )
            if current_count == last_count:
                break
            last_count = current_count

        html = page.content()
        return self._parse_list(html)

    def _parse_list(self, html: str) -> list[dict]:
        """解析列表页 HTML。"""
        soup = self.soup(html)
        items: list[dict] = []

        for li in soup.select("ul.items-list > li.list-item-box"):
            try:
                title_el = li.select_one("div.act-company-head div.title")
                if not title_el:
                    title_el = li.select_one("div.title")
                intro_el = li.select_one("div.introduce")
                content_el = li.select_one("div.company-content")
                link_el = li.select_one("a.tw-block.clearfix")

                company = title_el.get_text(strip=True) if title_el else ""
                if not company:
                    continue

                intro = intro_el.get_text(strip=True) if intro_el else ""
                content_text = content_el.get_text(separator=" ", strip=True) if content_el else ""
                open_date, close_date = _parse_date_range(content_text)

                loc_match = re.search(r"地点[：:]\s*(.+?)(?:立即投递|官网投递|$)", content_text)
                location = loc_match.group(1).strip() if loc_match else None
                if location == "正在收集中":
                    location = None

                href = link_el.get("href", "") if link_el else ""
                url = _clean_url(href)

                # 判断是否是牛客企业详情页
                enterprise_url = None
                if "/enterprise/" in href:
                    enterprise_url = href if href.startswith("http") else f"https://www.nowcoder.com{href}"

                items.append({
                    "source": self.name,
                    "source_id": company,
                    "company": company,
                    "title": f"{company}校招",
                    "location": location,
                    "salary": None,
                    "description": intro,
                    "requirements": None,
                    "open_date": open_date.isoformat() if open_date else None,
                    "close_date": close_date.isoformat() if close_date else None,
                    "url": url,
                    "enterprise_url": enterprise_url,
                })
            except Exception:
                continue

        return items

    def _fetch_enterprise_roles(self, page, url: str) -> list[str]:
        """访问企业详情页，提取招聘岗位类别。"""
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=10000)
            page.wait_for_timeout(2000)

            # 提取「招聘岗位」字段（内容可能跨行）
            text = page.inner_text("body")
            match = re.search(r"招聘岗位[：:]\s*([\s\S]+?)(?:网申助手|点击即可|移动版)", text)
            if match:
                roles_text = match.group(1).strip()
                roles = _split_roles(roles_text)
                if roles:
                    return roles
        except Exception:
            pass
        return []

    def parse(self, html: str) -> list[dict]:
        """兼容旧调用方式。"""
        return self._parse_list(html)
