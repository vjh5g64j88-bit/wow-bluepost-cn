"""
main.py — 主流程编排
1. 抓取 RSS → 过滤正式服 → 去重
2. 如有新蓝贴 → 抓取完整内容 → DeepSeek 翻译 → 生成静态网站
3. 无新蓝贴 → 跳过退出
"""
import logging
import sys
from pathlib import Path

# 确保 scripts 目录在 Python 路径中
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fetch import fetch_rss, filter_retail, deduplicate, mark_published
from scraper import get_bluepost_content
from translate import translate_batch
from generate import generate_site, load_all_posts, save_post_json

# ── 日志配置 ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


def main():
    logger.info("=" * 50)
    logger.info("WOW 蓝贴中文翻译站 — 开始新一轮更新")
    logger.info("=" * 50)

    # ── Step 1: 抓取 RSS ──
    try:
        all_items = fetch_rss()
    except Exception as e:
        logger.error("RSS 抓取失败: %s", e)
        sys.exit(1)

    if not all_items:
        logger.warning("RSS 无内容，退出")
        sys.exit(0)

    # ── Step 2: 过滤正式服 ──
    retail_items = filter_retail(all_items)

    # ── Step 3: 去重 ──
    new_items = deduplicate(retail_items)

    if not new_items:
        logger.info("✅ 无新蓝贴，无需更新。退出。")
        # 即使无新蓝贴，也重新生成一次站点（确保已发布的都显示）
        existing_posts = load_all_posts()
        if existing_posts:
            generate_site(existing_posts)
        sys.exit(0)

    logger.info("🎯 发现 %d 条新蓝贴，准备处理...", len(new_items))

    # ── Step 4: 提取原文内容（基于 RSS description）──
    for item in new_items:
        logger.info("提取原文: %s", item["title"][:60])
        item["content"] = get_bluepost_content(item)

    # ── Step 5: 翻译（逐条翻译+实时保存）──
    logger.info("开始翻译 %d 条蓝贴...", len(new_items))

    translated_items = []
    def save_one(item):
        """每翻译完一条就保存，防止中断丢失"""
        save_post_json(item)
        mark_published([item])
        translated_items.append(item)

    translate_batch(new_items, save_callback=save_one)

    # 过滤翻译失败的（翻译成功的在回调中已保存）
    valid_items = [it for it in translated_items if it.get("translated_content")]
    if not valid_items:
        logger.error("所有翻译均失败，退出")
        sys.exit(1)

    logger.info("翻译成功: %d / %d 条", len(valid_items), len(new_items))

    # ── Step 6: 生成静态网站 ──
    all_posts = load_all_posts()
    generate_site(all_posts)

    logger.info("=" * 50)
    logger.info("✅ 更新完成！新增 %d 篇，共 %d 篇蓝贴", len(valid_items), len(all_posts))
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
