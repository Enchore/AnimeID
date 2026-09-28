"""
設備B：從 Danbooru API 獲取熱門角色標籤
用法：python scripts/fetch_danbooru_tags.py --limit 1000
"""
import json
import requests
import argparse
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Danbooru API
DANBOORU_API = "https://danbooru.donmai.us/tags.json"

def fetch_character_tags(limit=1000, min_post_count=1000):
    """
    從 Danbooru API 獲取角色標籤（按圖片數量排序）
    """
    logger.info(f"📡 正在從 Danbooru API 獲取角色標籤（前 {limit} 個，最少 {min_post_count} 張圖片）...")
    
    headers = {"User-Agent": "AnimeIDCrawler/1.0"}
    
    all_tags = []
    page = 1
    max_pages = (limit // 100) + 1
    
    while len(all_tags) < limit and page <= max_pages:
        try:
            params = {
                "search[category]": 4,  # 4 = 角色標籤
                "search[order]": "count",
                "limit": 100,
                "page": page,
            }
            
            resp = requests.get(DANBOORU_API, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            tags = resp.json()
            
            if not tags:
                break
            
            for tag in tags:
                if tag.get("post_count", 0) < min_post_count:
                    continue
                all_tags.append({
                    "name": tag["name"],
                    "post_count": tag["post_count"],
                })
            
            logger.info(f"  已獲取 {len(all_tags)} 個角色標籤（第 {page} 頁）")
            page += 1
            
        except Exception as e:
            logger.error(f"❌ 獲取失敗（第 {page} 頁）: {e}")
            break
    
    logger.info(f"✅ 共獲取 {len(all_tags)} 個角色標籤")
    return all_tags


def save_tags_to_json(tags, output_file):
    """
    將獲取的標籤保存到 JSON 文件
    """
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "meta": {
                "source": "Danbooru API",
                "total": len(tags),
                "min_post_count": 1000,
            },
            "tags": tags,
        }, f, ensure_ascii=False, indent=2)
    
    logger.info(f"💾 已保存到：{output_path}")


def main():
    parser = argparse.ArgumentParser(description="從 Danbooru API 獲取熱門角色標籤")
    parser.add_argument("--limit", type=int, default=1000, help="目標數量（預設 1000）")
    parser.add_argument("--min-count", type=int, default=1000, help="最少圖片數量（預設 1000）")
    parser.add_argument("--output", type=str, default="config/danbooru_tags.json", help="輸出文件")
    args = parser.parse_args()
    
    # 獲取標籤
    tags = fetch_character_tags(args.limit, args.min_count)
    
    if not tags:
        logger.error("❌ 沒有獲取到任何標籤")
        return
    
    # 保存
    save_tags_to_json(tags, args.output)
    
    # 顯示前 20 個
    print("\n" + "="*80)
    print("📋 前 20 個熱門角色標籤：")
    print("="*80)
    for i, tag in enumerate(tags[:20], 1):
        print(f"  {i:3d}. {tag['name']:<40} ({tag['post_count']:>8,} 張圖片)")
    print("="*80)
    print(f"\n💡 提示：")
    print(f"  1. 編輯 {args.output}，手動添加中文角色名")
    print(f"  2. 然後運行：python scripts/import_tags_to_crawl_list.py")
    print("="*80)


if __name__ == "__main__":
    main()
