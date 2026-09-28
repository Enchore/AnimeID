"""
设备B：爬取动漫角色图片 + Qwen-VL 自动标注
用法：python scripts/crawl_and_label.py --character "芙莉蓮" --tag "frieren" --count 100
"""
import os
import sys
import json
import argparse
import logging
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from config import (
    QWEN_API_KEY, QWEN_API_BASE, QWEN_MODEL,
    ANIME_CHARACTERS, DATA_DIR
)
from module2_model.qwen_recognizer import QwenRecognizer

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


# ===== 安全爬虫（使用 Danbooru API）=====
def crawl_images_danbooru(character_name: str, tag: str, count: int = 50, output_dir: str = None):
    """
    从 Danbooru API 爬取角色图片（安全、无需登录）
    """
    try:
        import requests
    except ImportError:
        logger.error("需要 requests 库：pip install requests")
        return []

    if output_dir is None:
        slug = character_name.replace(" ", "_")
        output_dir = str(Path(DATA_DIR) / "crawled" / slug)
    os.makedirs(output_dir, exist_ok=True)

    # Danbooru API（无需 Key，公开访问）
    url = "https://danbooru.donmai.us/posts.json"
    params = {
        "tags": f"{tag} solo rating:safe",
        "limit": min(count, 200),
        "page": 1,
    }
    headers = {"User-Agent": "AnimeID-Crawler/1.0"}

    downloaded = []
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        posts = resp.json()

        for i, post in enumerate(posts):
            if len(downloaded) >= count:
                break
            file_url = post.get("file_url")
            if not file_url:
                continue
            if not file_url.startswith("http"):
                file_url = "https://danbooru.donmai.us" + file_url

            ext = file_url.split(".")[-1].split("?")[0]
            if ext not in ("jpg", "jpeg", "png", "webp"):
                continue

            out_path = os.path.join(output_dir, f"{i+1:04d}.{ext}")
            try:
                r = requests.get(file_url, headers=headers, timeout=10)
                with open(out_path, "wb") as f:
                    f.write(r.content)
                downloaded.append(out_path)
                logger.info(f"  ✓ 下载 #{i+1}: {out_path}")
            except Exception as e:
                logger.warning(f"  下载失败 #{i+1}: {e}")
                continue

        logger.info(f"完成爬取：{len(downloaded)} 张图片 → {output_dir}")
        return downloaded

    except Exception as e:
        logger.error(f"Danbooru 爬取失败: {e}")
        return []


# ===== Qwen-VL 自动标注 =====
def auto_label_with_qwen(image_paths: list, output_json: str = None):
    """
    用 Qwen-VL 对爬取的图片自动标注
    跳过已有人工标注的图片
    """
    recognizer = QwenRecognizer()
    if not recognizer.is_available():
        logger.error("Qwen-VL 不可用，请检查 API Key")
        return []

    if output_json is None:
        output_json = str(Path(DATA_DIR) / "auto_labels.json")

    # 读取已有标注（避免重复）
    labels = []
    if os.path.exists(output_json):
        with open(output_json, "r", encoding="utf-8") as f:
            labels = json.load(f)

    new_count = 0
    for img_path in image_paths:
        # 检查是否已标注
        img_name = os.path.basename(img_path)
        if any(l.get("image_filename") == img_name for l in labels):
            logger.info(f"  跳过已标注: {img_name}")
            continue

        # 调用 Qwen-VL
        results = recognizer.recognize(img_path, top_k=1)
        if not results:
            continue

        top1 = results[0]
        conf = top1.get("confidence", 0)

        # 只保存高置信度结果
        if conf >= 85.0:
            label = {
                "uuid": os.path.splitext(img_name)[0],
                "image_filename": img_name,
                "character_name": top1.get("name"),
                "anime_name": top1.get("anime"),
                "confidence": conf,
                "source": "qwen-auto",
                "local_path": img_path,
            }
            labels.append(label)
            new_count += 1
            logger.info(f"  ✓ 标注: {top1.get('name')} ({top1.get('anime')}) - {conf:.1f}%")

    # 保存
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(labels, f, ensure_ascii=False, indent=2)
    logger.info(f"标注完成：新增 {new_count} 条，共 {len(labels)} 条 → {output_json}")
    return labels


# ===== 主流程 =====
def main():
    parser = argparse.ArgumentParser(description="爬取动漫角色图片 + Qwen-VL 自动标注")
    parser.add_argument("--character", type=str, help="角色名（中文）", required=True)
    parser.add_argument("--anime", type=str, help="作品名（中文）", default="")
    parser.add_argument("--tag", type=str, help="搜索标签（英文）", required=True)
    parser.add_argument("--count", type=int, help="目标数量", default=50)
    parser.add_argument("--skip-crawl", action="store_true", help="跳过爬取（只用本地图片）")
    args = parser.parse_args()

    output_dir = str(Path(DATA_DIR) / "crawled" / args.character.replace(" ", "_"))
    os.makedirs(output_dir, exist_ok=True)

    # Step 1: 爬取
    image_paths = []
    if not args.skip_crawl:
        logger.info(f"===== 开始爬取：{args.character} (tag={args.tag}) =====")
        image_paths = crawl_images_danbooru(args.character, args.tag, args.count, output_dir)
    else:
        image_paths = [str(p) for p in Path(output_dir).glob("*.*") if p.suffix in (".jpg", ".png", ".jpeg", ".webp")]
        logger.info(f"跳过爬取，使用本地 {len(image_paths)} 张图片: {output_dir}")

    if not image_paths:
        logger.error("没有图片可标注，退出")
        return

    # Step 2: 自动标注
    logger.info(f"===== 开始 Qwen-VL 自动标注：{len(image_paths)} 张图片 =====")
    auto_label_with_qwen(image_paths)

    # Step 3: 提示下一步
    logger.info("=" * 80)
    logger.info("下一步：将 DATA_DIR/crawled/ 和 auto_labels.json 复制到设备 C")
    logger.info("       设备 C 运行：python -m module5_autotrain.train_worker")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
