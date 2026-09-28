"""
將 Danbooru 標籤導入到爬取列表
用法：
  python scripts/import_tags_to_crawl_list.py --input config/danbooru_tags.json
  python scripts/import_tags_to_crawl_list.py --input config/danbooru_tags.json --limit 500
"""
import json
import argparse
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# 配置文件路徑
CONFIG_FILE = Path(__file__).parent.parent / "config" / "characters_to_crawl.json"


def load_existing_config():
    """加載現有配置"""
    if not CONFIG_FILE.exists():
        return {"meta": {}, "characters": []}
    
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def import_tags(tags_file, limit=500):
    """
    將 Danbooru 標籤導入到爬取列表
    """
    # 讀取標籤文件
    with open(tags_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    tags = data.get("tags", [])
    if limit:
        tags = tags[:limit]
    
    logger.info(f"📥 開始導入 {len(tags)} 個標籤...")
    
    # 加載現有配置
    config = load_existing_config()
    existing_tags = {c["danbooru_tag"] for c in config["characters"]}
    
    # 導入新標籤
    new_count = 0
    next_id = max([c["id"] for c in config["characters"]], default=0) + 1
    
    for tag_data in tags:
        tag_name = tag_data["name"]
        post_count = tag_data["post_count"]
        
        # 跳過已存在的標籤
        if tag_name in existing_tags:
            logger.info(f"  跳過已存在：{tag_name}")
            continue
        
        # 推測角色名和作品名（從標籤名提取）
        # 格式通常是：character_name 或 character_name_(series)
        if "(" in tag_name:
            char_part = tag_name.split("(")[0].strip()
            series_part = tag_name.split("(")[1].rstrip(")")
        else:
            char_part = tag_name
            series_part = "unknown"
        
        # 轉換為中文（這裡需要先有人工審核，先用英文）
        character_cn = char_part.replace("_", " ").title()
        anime_cn = series_part.replace("_", " ").title()
        
        # 添加到列表
        config["characters"].append({
            "id": next_id,
            "character_cn": character_cn,
            "character_en": char_part.replace("_", " ").title(),
            "anime_cn": anime_cn,
            "anime_en": series_part.replace("_", " ").title(),
            "danbooru_tag": tag_name,
            "count": min(200, max(50, post_count // 100)),  # 根據圖片數量動態調整
            "priority": 3,
            "status": "pending",
            "note": f"自動導入，需人工審核中文名（圖片數：{post_count}）"
        })
        
        next_id += 1
        new_count += 1
    
    # 保存
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    logger.info(f"✅ 導入完成：新增 {new_count} 個角色")
    logger.info(f"⚠️  請人工審核並添加正確的中文角色名！")
    
    return new_count


def main():
    parser = argparse.ArgumentParser(description="將 Danbooru 標籤導入到爬取列表")
    parser.add_argument("--input", type=str, required=True, help="Danbooru 標籤文件（JSON）")
    parser.add_argument("--limit", type=int, help="限制導入數量（默認全部）")
    args = parser.parse_args()
    
    import_tags(args.input, args.limit)


if __name__ == "__main__":
    main()
