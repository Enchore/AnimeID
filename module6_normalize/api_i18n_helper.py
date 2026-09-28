"""
api_i18n_helper.py - 在 Qwen 识别后，用真实 API 查询 i18n 数据

此模块提供 enrich_results_with_api_i18n() 函数，
在 /api/recognize 流程中调用，确保 i18n 数据来自真实 API（非 LLM 瞎编）。
"""
import sys
import json
import logging

logger = logging.getLogger(__name__)

def enrich_results_with_api_i18n(results: list, all_characters_json: str = None) -> tuple:
    """
    用真实 API（Bangumi/AniList）查询 i18n 数据，替换/补充 results 中的 i18n 字段
    
    参数：
        results: Qwen 识别结果列表（每个元素是一个字符字典）
        all_characters_json: 多字符记录的 JSON 字符串（可选）
    
    返回：
        (results, all_characters_json)  # 已 enrichment 的版本
    """
    if not results:
        return results, all_characters_json
    
    try:
        # 动态导入（避免循环导入）
        from i18n_enricher import (
            search_character_i18n_bangumi,
            search_anime_i18n_bangumi,
            search_character_i18n_anilist,
            search_anime_i18n_anilist,
        )
    except ImportError:
        logger.warning("[API-i18n] 无法导入 i18n_enricher 模块，跳过 i18n 查询")
        return results, all_characters_json
    
    # ===== 1. 处理 results（top5 候选列表）=====
    for item in results:
        if not isinstance(item, dict):
            continue
        
        char_name = item.get("name", "")
        anime_name = item.get("anime", "")
        
        if not char_name and not anime_name:
            continue
        
        # 查询角色 i18n
        name_i18n = None
        if char_name:
            # 先尝试从已知角色库读取
            name_i18n = _try_get_known_character_i18n(char_name, "name")
            if not name_i18n:
                name_i18n = search_character_i18n_bangumi(char_name, anime_name)
            if not name_i18n:
                name_i18n = search_character_i18n_anilist(char_name, anime_name)
        
        # 查询番剧 i18n
        anime_i18n = None
        if anime_name:
            anime_i18n = _try_get_known_character_i18n(anime_name, "anime")
            if not anime_i18n:
                anime_i18n = search_anime_i18n_bangumi(anime_name)
            if not anime_i18n:
                anime_i18n = search_anime_i18n_anilist(anime_name)
        
        # 更新 item（仅在有真实数据时才更新）
        if name_i18n:
            item["name_i18n"] = name_i18n
            logger.info(f"[API-i18n] 已更新 name_i18n: {char_name}")
        else:
            item["name_i18n"] = {}
            logger.debug(f"[API-i18n] 未找到 name_i18n: {char_name}")
        
        if anime_i18n:
            item["anime_i18n"] = anime_i18n
            logger.info(f"[API-i18n] 已更新 anime_i18n: {anime_name}")
        else:
            item["anime_i18n"] = {}
            logger.debug(f"[API-i18n] 未找到 anime_i18n: {anime_name}")
        
        # 标记为此记录已通过 API 验证
        item["_i18n_verified"] = True
    
    # ===== 2. 处理 all_characters_json（多字符记录）=====
    if all_characters_json:
        try:
            all_chars = json.loads(all_characters_json)
            if isinstance(all_chars, list):
                for char in all_chars:
                    if not isinstance(char, dict):
                        continue
                    
                    char_name = char.get("name", "")
                    anime_name = char.get("anime", "")
                    
                    if not char_name and not anime_name:
                        continue
                    
                    # 查询角色 i18n
                    name_i18n = None
                    if char_name:
                        name_i18n = _try_get_known_character_i18n(char_name, "name")
                        if not name_i18n:
                            name_i18n = search_character_i18n_bangumi(char_name, anime_name)
                        if not name_i18n:
                            name_i18n = search_character_i18n_anilist(char_name, anime_name)
                    
                    # 查询番剧 i18n
                    anime_i18n = None
                    if anime_name:
                        anime_i18n = _try_get_known_character_i18n(anime_name, "anime")
                        if not anime_i18n:
                            anime_i18n = search_anime_i18n_bangumi(anime_name)
                        if not anime_i18n:
                            anime_i18n = search_anime_i18n_anilist(anime_name)
                    
                    if name_i18n:
                        char["name_i18n"] = name_i18n
                    else:
                        char["name_i18n"] = {}
                    
                    if anime_i18n:
                        char["anime_i18n"] = anime_i18n
                    else:
                        char["anime_i18n"] = {}
                    
                    char["_i18n_verified"] = True
                
                all_characters_json = json.dumps(all_chars, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"[API-i18n] 解析 all_characters_json 失败: {e}")
    
    logger.info(f"[API-i18n] i18n 数据查询完成（仅使用真实 API，无 LLM 翻译）")
    return results, all_characters_json


def _try_get_known_character_i18n(name: str, field: str) -> dict:
    """
    尝试从已知角色库（ANIME_CHARACTERS）读取 i18n 数据
    
    参数：
        name: 角色名或番剧名
        field: "name" 或 "anime"
    
    返回：
        i18n 字典，或 None
    """
    try:
        from module3_web.app import ANIME_CHARACTERS
        
        for ck, info in ANIME_CHARACTERS.items():
            info_name = info.get("name", {})
            info_anime = info.get("anime", {})
            
            # 检查 name 是否匹配
            if field == "name" and isinstance(info_name, dict):
                for lang, n in info_name.items():
                    if n == name:
                        return info_name
            elif field == "anime" and isinstance(info_anime, dict):
                for lang, n in info_anime.items():
                    if n == name:
                        return info_anime
    except Exception as e:
        logger.debug(f"[API-i18n] 从已知角色库读取失败: {e}")
    
    return None
