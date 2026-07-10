"""
fetch.py — 从 Wowhead Blue Tracker RSS 抓取蓝贴列表
过滤正式服(零售)内容，去重后返回新蓝贴。
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import feedparser
import requests

logger = logging.getLogger(__name__)

# ── 配置 ──────────────────────────────────────────────
RSS_URL = "https://www.wowhead.com/blue-tracker?rss"
PUBLISHED_PATH = Path(__file__).resolve().parent.parent / "data" / "published.json"

# 排除关键词：匹配到任一关键词的蓝贴将被过滤（怀旧服/经典服内容）
EXCLUDE_KEYWORDS = [
    "classic",
    "season of discovery",
    "burning crusade classic",
    "cataclysm classic",
    "wow classic era",
    "mists of pandaria classic",
    "hardcore",
    "wrath of the lich king classic",
]

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


def fetch_rss(url: str = RSS_URL) -> list[dict]:
    """获取并解析 Wowhead Blue Tracker RSS，返回条目列表。"""
    logger.info("正在获取 RSS: %s", url)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()

    feed = feedparser.parse(resp.content)
    if feed.bozo:
        logger.warning("RSS 解析警告: %s", feed.bozo_exception)

    items: list[dict] = []
    for entry in feed.entries:
        item = {
            "guid": getattr(entry, "guid", entry.get("link", "")),
            "title": getattr(entry, "title", "").strip(),
            "link": getattr(entry, "link", ""),
            "description": getattr(entry, "description", "").strip(),
            "pub_date": _parse_date(entry),
            "author": _extract_author(entry),
        }
        items.append(item)

    logger.info("RSS 共获取 %d 条蓝贴", len(items))
    return items


def filter_retail(items: list[dict]) -> list[dict]:
    """过滤仅保留正式服蓝贴：排除怀旧服/经典服相关内容。"""
    retail: list[dict] = []
    for item in items:
        text = f"{item['title']} {item['description']}".lower()
        if not any(kw in text for kw in EXCLUDE_KEYWORDS):
            retail.append(item)
        else:
            logger.debug("已排除非正式服: %s", item["title"][:60])

    logger.info("正式服蓝贴: %d / 总数: %d", len(retail), len(items))
    return retail


def load_published() -> set[str]:
    """加载已发布蓝贴的 guid 集合。"""
    if PUBLISHED_PATH.exists():
        with open(PUBLISHED_PATH, "r", encoding="utf-8-sig") as f:
            records = json.load(f)
        return {r["guid"] for r in records}
    return set()


def save_published(records: list[dict]) -> None:
    """保存已发布记录。"""
    PUBLISHED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PUBLISHED_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def deduplicate(items: list[dict]) -> list[dict]:
    """按 guid 去重：返回不在已发布列表中的新蓝贴。"""
    published_guids = load_published()
    new_items = [it for it in items if it["guid"] not in published_guids]

    # 还需按 pub_date 排序（最新的在前）
    new_items.sort(key=lambda x: x.get("pub_date", ""), reverse=True)

    logger.info("新蓝贴: %d 条", len(new_items))
    return new_items


def mark_published(new_items: list[dict]) -> None:
    """将新发布的蓝贴追加到 published.json。"""
    existing = []
    if PUBLISHED_PATH.exists():
        with open(PUBLISHED_PATH, "r", encoding="utf-8") as f:
            existing = json.load(f)

    for item in new_items:
        existing.append({
            "guid": item["guid"],
            "title": item["title"],
            "link": item["link"],
            "pub_date": item.get("pub_date", ""),
            "author": item.get("author", ""),
            "published_at": datetime.now().isoformat(),
        })

    # 按发布日期降序排列，只保留最近 500 条防止文件过大
    existing.sort(key=lambda x: x.get("pub_date", ""), reverse=True)
    existing = existing[:500]

    save_published(existing)
    logger.info("已更新 published.json，当前共 %d 条记录", len(existing))


# ── 辅助函数 ──────────────────────────────────────────

def _parse_date(entry) -> str:
    """解析 RSS 条目的发布日期。"""
    date_str = getattr(entry, "published", "") or getattr(entry, "pubDate", "")
    if not date_str:
        return ""
    try:
        # RSS pubDate 格式: "Fri, 10 Jul 2026 12:04:34 -0500"
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return date_str


def _extract_author(entry) -> str:
    """从 description 中提取蓝贴作者名。"""
    desc = getattr(entry, "description", "")
    if not desc:
        return "暴雪"
    import re
    m = re.search(r'By<a[^>]*>([^<]+)</a>', desc)
    if m:
        return m.group(1).strip()
    # 尝试 Blizzard Entertainment
    if "Blizzard Entertainment" in desc:
        return "暴雪娱乐"
    return "暴雪"


# ── CLI 测试入口 ──────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    all_items = fetch_rss()
    retail_items = filter_retail(all_items)
    new_items = deduplicate(retail_items)

    print(f"\n=== 新蓝贴 ({len(new_items)} 条) ===")
    for item in new_items[:5]:
        print(f"  [{item['pub_date']}] {item['title']}")
        print(f"   作者: {item['author']}")
        print(f"   链接: {item['link']}")
        print()
