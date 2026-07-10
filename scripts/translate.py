"""
translate.py — 使用 DeepSeek API 将蓝贴英文原文翻译为中文。
使用 requests 直接调用，避免 OpenAI SDK 的 httpx 兼容问题。
"""
import json
import logging
import os
import time
import traceback
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ── DeepSeek API 配置 ─────────────────────────────────
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

# 每次翻译最大字符数
MAX_CHUNK_SIZE = 6000

SYSTEM_PROMPT = """你是魔兽世界（World of Warcraft）官方蓝贴的专业中文翻译。
请将以下英文蓝贴内容翻译成通顺、自然的中文。

翻译要求：
1. 使用魔兽世界社区公认的游戏术语译名：
   - Dungeon → 地下城
   - Raid → 团队副本
   - Hotfix → 在线修正
   - Patch → 补丁
   - PTR → 测试服（Public Test Realm）
   - Mythic → 史诗
   - Heroic → 英雄
   - Normal → 普通
   - World Tier → 世界层级
   - Boss → 首领
   - NPC → NPC
   - Buff / Nerf → 增强 / 削弱
   - Class → 职业
   - Spec / Specialization → 专精
   - Talent → 天赋
   - Quest → 任务
   - Mount → 坐骑
   - Pet → 宠物
   - Transmog → 幻化
   - PvP / PvE → PvP / PvE（保留英文缩写）
   - Addon → 插件
   - Realm → 服务器
   - Faction → 阵营
   - Alliance / Horde → 联盟 / 部落
2. 保持原文的语气（官方公告类的正式语气）
3. 保留原文中的数字、百分比、日期格式不变
4. 职业名称使用中文通用译名（如 Mage→法师、Warrior→战士、Paladin→圣骑士等）
5. 如果原文是列表格式，翻译后也保持列表格式
6. 只输出中文翻译结果，不要添加任何额外解释"""


def _call_deepseek_api(messages: list[dict]) -> Optional[str]:
    """直接通过 requests 调用 DeepSeek Chat API。"""
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 4096,
    }

    for attempt in range(3):
        try:
            resp = requests.post(
                DEEPSEEK_API_URL,
                headers=headers,
                json=payload,
                timeout=(15, 60),  # (connect_timeout, read_timeout)
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                return content
            else:
                logger.warning(
                    "API 返回 %d: %s (尝试 %d/3)",
                    resp.status_code, resp.text[:200], attempt + 1,
                )
        except requests.ConnectionError as e:
            logger.warning("连接错误 (尝试 %d/3): %s", attempt + 1, e)
        except requests.Timeout as e:
            logger.warning("请求超时 (尝试 %d/3): %s", attempt + 1, e)
        except Exception as e:
            logger.warning("API 调用异常 (尝试 %d/3): %s: %s", attempt + 1, type(e).__name__, e)
            logger.debug("详细堆栈:\n%s", traceback.format_exc())

        if attempt < 2:
            time.sleep((attempt + 1) * 3)

    return None


def translate_text(title: str, content: str) -> str:
    """
    翻译蓝贴内容为中文。

    Returns:
        中文翻译文本。失败时返回空字符串。
    """
    if not DEEPSEEK_API_KEY:
        logger.error("未设置 DEEPSEEK_API_KEY")
        return ""

    full_text = f"标题: {title}\n\n{content}"
    if len(full_text) > MAX_CHUNK_SIZE:
        full_text = full_text[:MAX_CHUNK_SIZE] + "\n\n[内容过长，已截断]"

    logger.info("正在翻译: %s (%d 字符)", title[:50], len(full_text))
    result = _call_deepseek_api([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": full_text},
    ])

    if result:
        logger.info("翻译成功，%d 字符", len(result))
        return result
    else:
        logger.error("翻译最终失败: %s", title[:50])
        return ""


def translate_batch(items: list[dict], save_callback=None) -> list[dict]:
    """
    批量翻译蓝贴，逐条保存防止数据丢失。

    Args:
        items: 蓝贴列表
        save_callback: 每条翻译完成后的回调函数，签名为 callback(item)

    Returns:
        翻译成功的蓝贴列表
    """
    results = []
    for i, item in enumerate(items):
        logger.info("翻译进度: %d/%d", i + 1, len(items))

        try:
            translated = translate_text(item["title"], item.get("content", ""))
            item["translated_content"] = translated

            if translated:
                title_trans = _translate_title(item["title"])
                item["translated_title"] = title_trans if title_trans else item["title"]
            else:
                item["translated_title"] = item["title"]
                logger.warning("翻译返回空: %s", item["title"][:50])
                continue

            results.append(item)

            # 逐条保存回调
            if save_callback:
                try:
                    save_callback(item)
                except Exception as e:
                    logger.error("保存回调失败: %s", e)

        except Exception as e:
            logger.error("翻译异常 (%d/%d): %s - %s", i + 1, len(items), item["title"][:50], e)

        # 请求间隔
        if i < len(items) - 1:
            time.sleep(1)

    logger.info("批量翻译完成: %d/%d 成功", len(results), len(items))
    return results


def _translate_title(title: str) -> str:
    """单独翻译标题。"""
    if not DEEPSEEK_API_KEY:
        return title
    result = _call_deepseek_api([
        {"role": "system", "content": "你是魔兽世界蓝贴翻译。将英文标题翻译为中文，只输出中文标题。"},
        {"role": "user", "content": title},
    ])
    return result if result else title


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    # 测试翻译
    test_title = "Item Levels Increasing in Midnight Season 2"
    test_content = (
        "Looking at players' gear in Midnight Season 1, improved by upgrades, "
        "Voidcores, and powerful loot that became available in 12.0.7, we need "
        "to make sure that Season 2 is offering meaningful upgrades."
    )
    result = translate_text(test_title, test_content)
    print(f"原文: {test_title}")
    print(f"译文: {result}")
