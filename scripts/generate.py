"""
generate.py — 使用 Jinja2 模板生成静态 HTML 网站。
"""
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "data"

# 初始化 Jinja2
_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=True,
)
_env.globals["now"] = datetime.now()


def slugify(title: str) -> str:
    """从标题生成 URL 友好的 slug。"""
    # 取标题前 60 字符，只保留中英文数字和连字符
    slug = title[:60].strip()
    slug = re.sub(r'[^\w\u4e00-\u9fff-]', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    return slug or "bluepost"


def _text_to_html(text: str) -> str:
    """将纯文本转为简单 HTML（处理换行和段落）。"""
    if not text:
        return ""
    # 按双换行分段
    paragraphs = text.split("\n\n")
    html_parts = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        # 单换行转 <br>
        p_html = p.replace("\n", "<br>")
        html_parts.append(f"<p>{p_html}</p>")
    return "\n".join(html_parts)


def generate_site(posts: list[dict]) -> None:
    """
    生成完整静态网站。

    Args:
        posts: 所有已发布的蓝贴列表（包含新翻译的），按日期倒序
    """
    if not posts:
        logger.warning("无蓝贴数据，跳过生成")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "posts").mkdir(parents=True, exist_ok=True)

    # 为每条蓝贴生成 slug
    for post in posts:
        title = post.get("translated_title") or post.get("title", "")
        post["slug"] = slugify(title)
        # 生成摘要（前200字）
        content = post.get("translated_content", "")
        post["summary"] = content[:200] + ("..." if len(content) > 200 else "")

    # ── 生成首页 ──
    index_template = _env.get_template("index.html")
    index_html = index_template.render(
        posts=posts,
        total_posts=len(posts),
        update_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    (OUTPUT_DIR / "index.html").write_text(index_html, encoding="utf-8")
    logger.info("已生成首页: index.html (%d 篇蓝贴)", len(posts))

    # ── 生成蓝贴详情页 ──
    post_template = _env.get_template("post.html")
    for post in posts:
        content = post.get("translated_content", "")
        post_html = post_template.render(
            translated_title=post.get("translated_title", post.get("title", "")),
            pub_date=post.get("pub_date", ""),
            author=post.get("author", "暴雪"),
            original_link=post.get("link", "#"),
            content_html=_text_to_html(content),
        )
        page_path = OUTPUT_DIR / "posts" / f"{post['slug']}.html"
        page_path.write_text(post_html, encoding="utf-8")

    logger.info("已生成 %d 篇蓝贴详情页", len(posts))


def load_all_posts() -> list[dict]:
    """加载 data/ 目录下所有蓝贴 JSON。"""
    posts_dir = DATA_DIR / "posts"
    if not posts_dir.exists():
        return []

    posts: list[dict] = []
    for f in sorted(posts_dir.glob("*.json"), reverse=True):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                post = json.load(fp)
                posts.append(post)
        except Exception as e:
            logger.warning("加载失败 %s: %s", f.name, e)

    # 按日期倒序
    posts.sort(key=lambda x: x.get("pub_date", ""), reverse=True)
    return posts


def save_post_json(post: dict) -> None:
    """保存单篇蓝贴到 data/posts/ 目录。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "posts").mkdir(parents=True, exist_ok=True)

    title = post.get("translated_title") or post.get("title", "")
    slug = slugify(title)
    # Windows 文件名不能包含 : 等字符，替换为 -
    safe_date = post.get("pub_date", "unknown").replace(":", "-").replace(" ", "_")
    filename = f"{safe_date}_{slug}.json"

    filepath = DATA_DIR / "posts" / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(post, f, ensure_ascii=False, indent=2)
    logger.info("已保存: %s", filename)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    # 测试：用 sample 数据生成站点
    sample_posts = [
        {
            "title": "Test Blue Post",
            "translated_title": "测试蓝贴标题",
            "translated_content": "这是翻译后的蓝贴正文内容。\n\n包含多段文字用于测试。",
            "pub_date": "2026-07-11 12:00",
            "author": "Kaivax",
            "link": "https://www.wowhead.com/blue-tracker/topic/us/2324532",
        }
    ]
    generate_site(sample_posts)
    print("测试站点已生成在 output/ 目录")
