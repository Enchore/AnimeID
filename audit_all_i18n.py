"""
audit_all_i18n.py - 审计并修复所有记录的 i18n 数据

使用真实 API（Bangumi/AniList）查询官方译名，不使用 LLM 翻译。
"""
import sys
import os
import json
import logging

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'module3_web'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'module6_normalize'))
sys.path.insert(0, os.path.dirname(__file__))

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

from config import ANIME_CHARACTERS
from module3_web.app import app, db, RecognitionRecord
from i18n_enricher import (
    enrich_record_i18n_multi_source,
    search_character_i18n_bangumi,
    search_anime_i18n_bangumi,
    search_character_i18n_anilist,
    search_anime_i18n_anilist,
)


def audit_single_record(record, session):
    """
    审计单条记录的 i18n 数据
    
    返回：(needs_update, corrected_name_i18n, corrected_anime_i18n)
    """
    if not record.top5_results:
        return False, None, None
    
    try:
        top5 = json.loads(record.top5_results) if isinstance(record.top5_results, str) else record.top5_results
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"[审计] 记录#{record.id} top5_results 解析失败")
        return False, None, None
    
    if not top5 or not isinstance(top5, list) or len(top5) == 0:
        return False, None, None
    
    changed = False
    top5_new = json.loads(json.dumps(top5))  # 深拷贝
    
    for i, item in enumerate(top5_new):
        char_name = item.get("name") or record.top1_character_name
        anime_name = item.get("anime") or record.top1_anime
        
        if not char_name and not anime_name:
            continue
        
        # 查询真实的 i18n 数据（仅使用 API，不使用 LLM）
        real_name_i18n = None
        real_anime_i18n = None
        
        # 尝试从已知角色库读取
        matched_key = None
        for ck, info in ANIME_CHARACTERS.items():
            names = info.get("name", {})
            if isinstance(names, dict):
                for lang_name in names.values():
                    if lang_name == char_name:
                        matched_key = ck
                        break
            if matched_key:
                break
        
        if matched_key:
            # 已知角色：直接从角色库读取
            real_name_i18n = ANIME_CHARACTERS[matched_key]["name"]
            real_anime_i18n = ANIME_CHARACTERS[matched_key]["anime"]
            logger.info(f"[审计] 记录#{record.id} 从角色库读取: {char_name}")
        else:
            # 新角色：使用 API 查询
            logger.info(f"[审计] 记录#{record.id} 查询 API: {char_name} / {anime_name}")
            
            # 查询角色 i18n
            if not real_name_i18n:
                real_name_i18n = search_character_i18n_bangumi(char_name, anime_name)
            if not real_name_i18n:
                real_name_i18n = search_character_i18n_anilist(char_name, anime_name)
            
            # 查询番剧 i18n
            if anime_name and not real_anime_i18n:
                real_anime_i18n = search_anime_i18n_bangumi(anime_name)
            if anime_name and not real_anime_i18n:
                real_anime_i18n = search_anime_i18n_anilist(anime_name)
        
        # 对比现有数据
        old_name_i18n = item.get("name_i18n", {})
        old_anime_i18n = item.get("anime_i18n", {})
        
        # 如果查到了真实数据，且跟现有数据不同 → 更新
        if real_name_i18n and real_name_i18n != old_name_i18n:
            item["name_i18n"] = real_name_i18n
            changed = True
            logger.info(f"[审计] 记录#{record.id} name_i18n 已更新: {char_name}")
            logger.debug(f"  旧: {json.dumps(old_name_i18n, ensure_ascii=False)}")
            logger.debug(f"  新: {json.dumps(real_name_i18n, ensure_ascii=False)}")
        
        if real_anime_i18n and real_anime_i18n != old_anime_i18n:
            item["anime_i18n"] = real_anime_i18n
            changed = True
            logger.info(f"[审计] 记录#{record.id} anime_i18n 已更新: {anime_name}")
            logger.debug(f"  旧: {json.dumps(old_anime_i18n, ensure_ascii=False)}")
            logger.debug(f"  新: {json.dumps(real_anime_i18n, ensure_ascii=False)}")
    
    if changed:
        record.top5_results = json.dumps(top5_new, ensure_ascii=False)
        return True, None, None
    
    return False, None, None


def main():
    """主函数：审计所有记录"""
    with app.app_context():
        records = RecognitionRecord.query.all()
        total = len(records)
        
        logger.info(f"[审计] 开始审计 {total} 条记录...")
        
        updated = 0
        skipped = 0
        errors = 0
        
        for i, record in enumerate(records):
            try:
                needs_update, _, _ = audit_single_record(record, db.session)
                
                if needs_update:
                    db.session.commit()
                    updated += 1
                    logger.info(f"[审计] 进度: {i+1}/{total}, 已更新: {updated}")
                else:
                    skipped += 1
                    
            except Exception as e:
                errors += 1
                logger.error(f"[审计] 记录#{record.id} 处理失败: {e}", exc_info=True)
        
        logger.info(f"[审计] 完成！总计: {total}, 更新: {updated}, 跳过: {skipped}, 错误: {errors}")


if __name__ == "__main__":
    main()
