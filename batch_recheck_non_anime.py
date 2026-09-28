"""
批量重检脚本：对数据库中所有 is_anime=1 的历史记录，
重新用 qwen-vl 做非动漫检测，标记出非动漫图片。
"""
import os
import sys
import sqlite3
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from module2_model.qwen_recognizer import get_qwen_recognizer

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# 数据库路径
DB_PATH = Path(__file__).parent / "anime_system.db"
UPLOADS_DIR = Path(__file__).parent / "uploads"


def main():
    if not DB_PATH.exists():
        logger.error(f"数据库不存在: {DB_PATH}")
        return
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # 查询所有 is_anime=1 的记录
    cursor.execute("""
        SELECT id, image_filename, top1_character_name, top1_anime, user_corrected_name
        FROM recognition_records
        WHERE is_anime = 1 OR is_anime IS NULL
        ORDER BY id
    """)
    records = cursor.fetchall()
    
    logger.info(f"共找到 {len(records)} 条待检测记录")
    
    qwen = get_qwen_recognizer()
    if not qwen.is_available():
        logger.error("Qwen-VL 不可用，终止")
        conn.close()
        return
    
    non_anime_count = 0
    skipped_count = 0
    checked_count = 0
    
    for rec in records:
        rec_id, filename, char_name, anime, corrected_name = rec
        
        # 跳过已经用户纠正过的记录（用户不会把非动漫纠正为动漫角色）
        if corrected_name:
            logger.info(f"  ID={rec_id} [{filename}] 已有用户纠正 '{corrected_name}'，跳过")
            skipped_count += 1
            continue
        
        image_path = UPLOADS_DIR / filename
        if not image_path.exists():
            logger.warning(f"  ID={rec_id} [{filename}] 图片文件不存在，跳过")
            skipped_count += 1
            continue
        
        checked_count += 1
        logger.info(f"  检测 ID={rec_id} [{filename}] 当前识别: {char_name} ({anime})")
        
        try:
            results = qwen.recognize(str(image_path), top_k=1)  # 只需要检测is_anime
            
            if results and results[0].get("is_anime") == False:
                reason = results[0].get("anime", "非动漫图片")
                logger.info(f"    → 判定为非动漫! 原因: {reason}")
                
                # 更新数据库
                cursor.execute("""
                    UPDATE recognition_records 
                    SET is_anime = 0,
                        top1_character_name = '非动漫图片',
                        top1_character_key = '_not_anime_',
                        top1_anime = ?,
                        top1_confidence = 0.0,
                        top5_results = ?
                    WHERE id = ?
                """, (
                    reason,
                    json.dumps([{
                        "rank": 0, "character_key": "_not_anime_",
                        "name": "非动漫图片", "anime": reason,
                        "confidence": 0.0, "source": "qwen-vl",
                        "is_anime": False,
                    }]),
                    rec_id,
                ))
                conn.commit()
                non_anime_count += 1
            else:
                logger.info(f"    → 确认为动漫图片 ✓")
                
        except Exception as e:
            logger.error(f"    → 检测失败: {e}")
    
    conn.close()
    
    logger.info("=" * 50)
    logger.info(f"批量重检完成!")
    logger.info(f"  检测: {checked_count} 条")
    logger.info(f"  跳过: {skipped_count} 条（已纠正或无文件）")
    logger.info(f"  发现非动漫: {non_anime_count} 条")
    logger.info("=" * 50)


if __name__ == "__main__":
    import json
    main()
