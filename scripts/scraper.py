"""
scraper.py — 从 Blizzard 官方论坛抓取蓝贴完整原文。
Wowhead 页面需 JS 渲染，但蓝贴原文在 Blizzard 论坛可直接抓取。
"""
import logging
import re
from html import unescape

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def clean_html(html_text: str) -> str:
    """清理 HTML 标签和实体，保留纯文本。"""
    if not html_text:
        return ""
    soup = BeautifulSoup(html_text, "lxml")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text(separator="\n")
    text = unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return text.strip()


def _build_blizzard_url(wowhead_link: str) -> str | None:
    """从 wowhead 蓝贴链接构造 Blizzard 论坛原文 URL。

    wowhead: https://www.wowhead.com/blue-tracker/topic/us/2324532
    blizzard: https://us.forums.blizzard.com/en/wow/t/2324532/1

    wowhead: https://www.wowhead.com/blue-tracker/topic/eu/621832
    blizzard: https://eu.forums.blizzard.com/en/wow/t/621832/1
    """
    # 匹配 topic/{region}/{thread_id}
    m = re.search(r'/topic/(us|eu)/(\d+)', wowhead_link)
    if m:
        region = m.group(1)
        thread_id = m.group(2)
        return f"https://{region}.forums.blizzard.com/en/wow/t/{thread_id}/1"
    return None


def _scrape_blizzard_forum(url: str) -> str:
    """从 Blizzard 论坛（Discourse）抓取蓝贴正文。"""
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "lxml")

        # Discourse 论坛正文选择器
        for selector in [
            ".topic-post .cooked",
            ".post .cooked",
            "[itemprop='text']",
            ".regular.contents .cooked",
            "article .post-body",
            ".post-body",
        ]:
            el = soup.select_one(selector)
            if el and len(el.get_text(strip=True)) > 100:
                return el.get_text(separator="\n").strip()

        # 终极降级：获取整个页面的可见文本
        logger.warning("未命中选择器，尝试全页提取")
        for tag in soup(["script", "style", "nav", "header", "footer", ".topic-list", ".suggested-topics"]):
            if hasattr(tag, 'decompose'):
                tag.decompose()
        # 提取包含 "Greetings" 附近的大块文本
        body = soup.find("body")
        if body:
            text = body.get_text(separator="\n")
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            return text

        return ""
    except Exception as e:
        logger.warning("Blizzard 论坛抓取失败: %s", e)
        return ""


def extract_content_from_rss_description(description: str) -> str:
    """从 RSS description 中提取纯净的蓝贴正文（降级方案）。"""
    if not description:
        return ""
    text = clean_html(description)
    text = re.sub(
        r'\n*By\s+.+?\s+on\s+\d{4}/\d{2}/\d{2}\s+at\s+\d{1,2}:\d{2}\s+[AP]M\s*$',
        '', text, flags=re.IGNORECASE,
    )
    lines = text.strip().split("\n")
    if lines and re.match(r'^By\s+', lines[-1].strip()):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def get_bluepost_content(item: dict) -> str:
    """
    获取蓝贴完整原文。
    优先从 Blizzard 论坛抓取全文，失败则降级使用 RSS 摘要。

    Args:
        item: 蓝贴条目字典，需包含 link 和 description

    Returns:
        清理后的纯文本蓝贴内容
    """
    link = item.get("link", "")
    description = item.get("description", "")

    # ── 尝试从 Blizzard 论坛抓取全文 ──
    blizz_url = _build_blizzard_url(link)
    if blizz_url:
        logger.info("从 Blizzard 论坛抓取: %s", blizz_url[:70])
        full_content = _scrape_blizzard_forum(blizz_url)
        if full_content and len(full_content) > 100:
            logger.info("论坛抓取成功: %d 字符", len(full_content))
            return full_content
        logger.info("论坛抓取失败，降级使用 RSS")

    # ── 降级：RSS 摘要 ──
    content = extract_content_from_rss_description(description)
    if content:
        logger.info("使用 RSS 摘要: %d 字符", len(content))
    else:
        content = clean_html(description)
        logger.warning("内容为空，使用原始 description")
    return content

    logger.info("提取内容: %d 字符", len(content))
    return content


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    # 测试 RSS 摘要提取
    sample_desc = (
        "We identified a potential cause of the crashing issue and pushed a client patch "
        "that may alleviate the problem. If it continues to occur after downloading this "
        "update, please let us know the error /...<br><br>By<a "
        "href='https://www.wowhead.com/blue-tracker/author/SpeedyRogue'>SpeedyRogue</a> "
        "on 2026/07/10 at 12:04 PM"
    )
    content = extract_content_from_rss_description(sample_desc)
    print("=== 提取的正文 ===")
    print(content[:500])
    print(f"\n总字符数: {len(content)}")
