"""
scraper.py — 提取并清理蓝贴原文内容。

Wowhead 页面需要 JavaScript 渲染，无法直接用 requests 抓取完整页面。
因此本模块以 RSS description 为主要内容来源（已包含蓝贴核心正文），
同时尽可能清理 HTML 标签和无关元信息。
"""
import logging
import re
from html import unescape

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def clean_html(html_text: str) -> str:
    """清理 HTML 标签和实体，保留纯文本。"""
    if not html_text:
        return ""

    soup = BeautifulSoup(html_text, "lxml")
    for br in soup.find_all("br"):
        br.replace_with("\n")

    text = soup.get_text(separator="\n")
    text = unescape(text)

    # 清理多余空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = text.strip()
    return text


def extract_content_from_rss_description(description: str) -> str:
    """从 RSS description 中提取纯净的蓝贴正文。

    RSS description 格式: "蓝贴正文...<br><br>By<a>Author</a> on YYYY/MM/DD at HH:MM PM"
    本函数移除尾部的作者/时间戳行，保留纯正文。
    """
    if not description:
        return ""

    text = clean_html(description)

    # 移除 "By AuthorName on YYYY/MM/DD at HH:MM PM" 尾部署名
    text = re.sub(
        r'\n*By\s+.+?\s+on\s+\d{4}/\d{2}/\d{2}\s+at\s+\d{1,2}:\d{2}\s+[AP]M\s*$',
        '', text, flags=re.IGNORECASE,
    )
    # 移除可能残留的尾部 "By ..." 行
    lines = text.strip().split("\n")
    if lines and re.match(r'^By\s+', lines[-1].strip()):
        lines = lines[:-1]
    text = "\n".join(lines).strip()

    return text


def get_bluepost_content(item: dict) -> str:
    """
    获取蓝贴的完整内容文本。

    以 RSS description 为主要来源（已验证包含充足内容），
    清理 HTML 后返回纯文本。

    Args:
        item: 蓝贴条目字典，需包含 description 字段

    Returns:
        清理后的纯文本蓝贴内容
    """
    description = item.get("description", "")
    content = extract_content_from_rss_description(description)

    if not content:
        logger.warning("无法提取内容，返回原始 description")
        return clean_html(description)

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
