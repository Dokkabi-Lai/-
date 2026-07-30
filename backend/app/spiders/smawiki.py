"""sma-wiki.cn 校招信息汇总爬虫。

数据源: https://campus.sma-wiki.cn/campus/campus_recruit.html
所有数据在页面 JS 变量 RAW_DATA 中（约2665条），无需翻页。
"""
from __future__ import annotations

import datetime as dt
import re
from urllib.parse import unquote

from .base import BaseSpider, SpiderResult

LIST_URL = "https://campus.sma-wiki.cn/campus/campus_recruit.html?channel=ysgg"

# 只保留这些批次
ALLOWED_BATCHES = {"27届提前批", "27提前批", "27届秋招", "27届秋招补录", "27届校招"}


def _split_positions(text: str) -> list[str]:
    """拆分岗位字符串为列表。支持逗号、顿号、空格分隔。"""
    if not text:
        return []
    # 先把换行替换
    text = text.replace("\n", ",").replace("、", ",").replace("，", ",")
    parts = re.split(r"[,;；]+", text.strip())
    return [p.strip() for p in parts if p.strip() and 1 < len(p.strip()) <= 30]


def _clean_company_name(name: str) -> str:
    """从公司名中提取干净的公司名（去掉批次描述）。"""
    # 去掉 "27届" "26届" "秋招" "校招" "实习" "提前批" "启动" 等后缀
    name = re.sub(r'\d+届.*$', '', name)
    name = re.sub(r'(秋季|春季)?(校园|校招|实习|提前批).*$', '', name)
    name = re.sub(r'\d{4}年.*$', '', name)
    return name.strip() if name.strip() else name


def _parse_deadline(text: str) -> dt.date | None:
    """解析截止日期 '2026/9/23' """
    if not text:
        return None
    try:
        parts = text.split('/')
        if len(parts) == 3:
            return dt.date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        pass
    return None


def _clean_url(url: str) -> str:
    """清理 URL，可能是 markdown 格式或带跳转。"""
    if not url:
        return None
    # 去掉 markdown 格式 ](url)
    m = re.search(r'\]\((.+?)\)', url)
    if m:
        url = m.group(1)
    # 解码 URL
    url = unquote(url)
    # 去掉跳转前缀
    m2 = re.search(r'target=([^&]+)', url)
    if m2:
        return unquote(m2.group(1))
    return url.strip()


class SmaWikiSpider(BaseSpider):
    name = "smawiki"
    item_type = "job"

    def run(self) -> SpiderResult:
        result = SpiderResult(source=self.name)
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(LIST_URL, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(3000)

                # 直接从 JS 变量获取数据
                raw_data = page.evaluate('typeof RAW_DATA !== "undefined" ? RAW_DATA : []')
                browser.close()

                if not raw_data:
                    result.status = "failed"
                    result.message = "未获取到 RAW_DATA"
                    return result

                items = []
                for record in raw_data:
                    company_raw = record.get("company", "").strip()
                    if not company_raw:
                        continue
                    
                    company = _clean_company_name(company_raw)
                    positions = _split_positions(record.get("positions", ""))
                    location = record.get("location", "")
                    app_link = _clean_url(record.get("appLink", ""))
                    source_link = _clean_url(record.get("sourceLink", ""))
                    deadline = _parse_deadline(record.get("deadline", ""))
                    industry = record.get("industry", "")
                    nature = record.get("nature", "")
                    batch = record.get("batch", "")
                    evaluation = record.get("evaluation", "")
                    full_date = record.get("fullDate", "")

                    # 批次过滤：只保留 27届提前批 和 27届秋招
                    if batch not in ALLOWED_BATCHES:
                        continue

                    # 构建描述信息
                    desc_parts = []
                    if batch: desc_parts.append(f"批次: {batch}")
                    if industry: desc_parts.append(f"行业: {industry}")
                    if nature: desc_parts.append(f"性质: {nature}")
                    if evaluation: desc_parts.append(evaluation)
                    description = "\n".join(desc_parts)

                    if positions:
                        # 为每个岗位创建独立记录
                        for pos in positions:
                            items.append({
                                "source": self.name,
                                "source_id": f"{company}_{pos}_{batch}",
                                "company": company,
                                "title": pos,
                                "location": location,
                                "salary": None,
                                "description": description,
                                "requirements": None,
                                "batch": batch,
                                "open_date": full_date or None,
                                "close_date": deadline.isoformat() if deadline else None,
                                "url": app_link or source_link,
                            })
                    else:
                        # 没有具体岗位的，保留公司级记录
                        items.append({
                            "source": self.name,
                            "source_id": f"{company}_{batch}",
                            "company": company,
                            "title": f"{company}校招",
                            "location": location,
                            "salary": None,
                            "description": description,
                            "requirements": None,
                            "batch": batch,
                            "open_date": full_date or None,
                            "close_date": deadline.isoformat() if deadline else None,
                            "url": app_link or source_link,
                        })

                result.items = items
                result.count = len(items)
                result.message = f"共获取 {len(items)} 条岗位记录（来自 {len(raw_data)} 家公司）"
        except Exception as e:
            result.status = "failed"
            result.message = str(e)
        return result
