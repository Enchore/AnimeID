"""
设备B：批量爬取动漫角色图片 + Qwen-VL 自动标注
支持断点续爬（中断后重启可继续）

用法：
  python scripts/batch_crawl.py              # 从第一个 pending 角色开始爬取
  python scripts/batch_crawl.py --resume     # 从中断处继续（默认行为）
  python scripts/batch_crawl.py --reset      # 重置所有状态为 pending
  python scripts/batch_crawl.py --status     # 查看爬取进度

功能：
  1. 读取 config/characters_to_crawl.json 中的角色列表
  2. 依次爬取每个角色的图片（从 Danbooru）
  3. 用 Qwen-VL 自动标注
  4. 保存进度到 JSON 文件（每完成一个角色更新一次）
  5. 中断后重启，自动跳过已完成的角色
"""
import os
import sys
import json
import argparse
import logging
import time
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from config import QWEN_API_KEY, DATA_DIR
from module2_model.qwen_recognizer import QwenRecognizer

logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s [%(levelname)s] %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

# 配置文件路径
CONFIG_FILE = SCRIPT_DIR / "config" / "characters_to_crawl.json"
PROGRESS_FILE = SCRIPT_DIR / "data" / "crawl_progress.json"


def load_config():
    """加载角色配置"""
    if not CONFIG_FILE.exists():
        logger.error(f"配置文件不存在: {CONFIG_FILE}")
        return None
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config):
    """保存配置文件（更新状态）"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def load_progress():
    """加载爬取进度"""
    if not PROGRESS_FILE.exists():
        return {
            "last_run": None,
            "completed": 0,
            "failed": 0,
            "skipped": 0,
            "current_index": 0,
            "details": []
        }
    with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_progress(progress):
    """保存爬取进度"""
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def crawl_images_danbooru(character_name: str, tag: str, count: int = 50):
    """
    从 Danbooru API 爬取角色图片
    """
    try:
        import requests
    except ImportError:
        logger.error("需要 requests 库：pip install requests")
        return []
    
    slug = character_name.replace(" ", "_")
    output_dir = Path(DATA_DIR) / "crawled" / slug
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 检查已存在的图片（续爬时跳过）
    existing = list(output_dir.glob("*.*"))
    if existing:
        logger.info(f"  📂 发现 {len(existing)} 张已下载图片，将继续爬取")
    
    # Danbooru API
    url = "https://danbooru.donmai.us/posts.json"
    headers = {"User-Agent": "AnimeID-Crawler/1.0"}
    
    downloaded = []
    page = 1
    target_count = count - len(existing)
    
    if target_count <= 0:
        logger.info(f"  ✓ 已满足目标数量 ({count} 张)，跳过爬取")
        return [str(p) for p in existing]
    
    logger.info(f"  🌐 开始爬取：目标 {count} 张，还需 {target_count} 张")
    
    try:
        while len(downloaded) < target_count:
            params = {
                "tags": f"{tag} solo rating:safe",
                "limit": 100,
                "page": page,
            }
            
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            posts = resp.json()
            
            if not posts:
                logger.info(f"  ⚠️  没有更多图片了（第 {page} 页为空）")
                break
            
            for post in posts:
                if len(downloaded) >= target_count:
                    break
                
                file_url = post.get("file_url")
                if not file_url:
                    continue
                if not file_url.startswith("http"):
                    file_url = "https://danbooru.donmai.us" + file_url
                
                ext = file_url.split(".")[-1].split("?")[0]
                if ext not in ("jpg", "jpeg", "png", "webp"):
                    continue
                
                # 文件名：已有数量 + 新下载序号
                filename = f"{len(existing) + len(downloaded) + 1:04d}.{ext}"
                out_path = output_dir / filename
                
                # 跳过已存在
                if out_path.exists():
                    continue
                
                try:
                    r = requests.get(file_url, headers=headers, timeout=10)
                    r.raise_for_status()
                    with open(out_path, "wb") as f:
                        f.write(r.content)
                    downloaded.append(str(out_path))
                    logger.info(f"    ✓ 下载 {len(downloaded)}/{target_count}: {filename}")
                    
                    # 限速（避免被 ban）
                    time.sleep(0.5)
                    
                except Exception as e:
                    logger.warning(f"    ⚠️  下载失败: {e}")
                    continue
            
            page += 1
            if page > 10:  # 最多爬 10 页
                break
        
        logger.info(f"  ✅ 爬取完成：新增 {len(downloaded)} 张，共 {len(existing) + len(downloaded)} 张")
        return [str(p) for p in existing] + downloaded
        
    except Exception as e:
        logger.error(f"  ❌ Danbooru 爬取失败: {e}")
        return [str(p) for p in existing]


def auto_label_with_qwen(image_paths: list, character_name: str):
    """
    用 Qwen-VL 对图片自动标注
    只保存高置信度结果（≥85%）
    """
    recognizer = QwenRecognizer()
    if not recognizer.is_available():
        logger.error("  ❌ Qwen-VL 不可用，请检查 API Key")
        return 0
    
    # 输出文件
    output_json = Path(DATA_DIR) / "auto_labels.json"
    
    # 读取已有标注
    labels = []
    if output_json.exists():
        with open(output_json, "r", encoding="utf-8") as f:
            labels = json.load(f)
    
    new_count = 0
    skip_count = 0
    
    for img_path in image_paths:
        img_name = os.path.basename(img_path)
        
        # 检查是否已标注
        if any(l.get("image_filename") == img_name for l in labels):
            skip_count += 1
            continue
        
        # 调用 Qwen-VL
        try:
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
                    "labeled_at": datetime.now().isoformat(),
                }
                labels.append(label)
                new_count += 1
                logger.info(f"    ✓ 标注: {top1.get('name')} ({top1.get('anime')}) - {conf:.1f}%")
            else:
                logger.info(f"    ⚠️  置信度低 ({conf:.1f}%)，跳过: {img_name}")
        
        except Exception as e:
            logger.warning(f"    ⚠️  标注失败: {e}")
            continue
        
        # 限速（Qwen API 限制）
        time.sleep(1)
    
    # 保存
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(labels, f, ensure_ascii=False, indent=2)
    
    logger.info(f"  ✅ 标注完成：新增 {new_count} 条，跳过 {skip_count} 条，共 {len(labels)} 条")
    return new_count


def process_character(char_cfg: dict, args):
    """
    处理单个角色：爬取 + 标注
    """
    character_name = char_cfg["character_cn"]
    tag = char_cfg["danbooru_tag"]
    count = char_cfg["count"]
    
    logger.info("=" * 80)
    logger.info(f"[{char_cfg['id']}/{args.total}] 处理角色：{character_name} (tag={tag})")
    logger.info("=" * 80)
    
    # Step 1: 爬取图片
    logger.info("📥 Step 1: 爬取图片...")
    image_paths = crawl_images_danbooru(character_name, tag, count)
    
    if not image_paths:
        logger.error("  ❌ 没有图片，跳过此角色")
        return "failed"
    
    # Step 2: 自动标注
    logger.info("🏷️  Step 2: Qwen-VL 自动标注...")
    new_labels = auto_label_with_qwen(image_paths, character_name)
    
    # Step 3: 保存到训练数据
    if new_labels > 0:
        logger.info("💾 Step 3: 保存到训练数据...")
        save_to_training_data(image_paths, character_name)
    
    return "completed"


def save_to_training_data(image_paths: list, character_name: str):
    """
    将爬取的图片和标注保存到训练数据目录
    供设备 C 使用
    """
    training_dir = Path(DATA_DIR) / "user_labeled"
    training_dir.mkdir(parents=True, exist_ok=True)
    
    # 复制图片到 training_dir/images/
    images_dir = training_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    
    copied = 0
    for img_path in image_paths:
        import shutil
        img_name = os.path.basename(img_path)
        dst = images_dir / img_name
        if not dst.exists():
            shutil.copy2(img_path, dst)
            copied += 1
    
    logger.info(f"  ✓ 已复制 {copied} 张图片到训练数据目录")


def show_status(config, progress):
    """显示爬取进度"""
    characters = config["characters"]
    total = len(characters)
    completed = sum(1 for c in characters if c["status"] == "completed")
    failed = sum(1 for c in characters if c["status"] == "failed")
    pending = sum(1 for c in characters if c["status"] == "pending")
    
    print("=" * 80)
    print("📊 爬取进度")
    print("=" * 80)
    print(f"  总角色数：{total}")
    print(f"  ✅ 已完成：{completed}")
    print(f"  ❌ 失败：{failed}")
    print(f"  ⏳ 待处理：{pending}")
    print(f"  进度：{completed/total*100:.1f}%")
    print("=" * 80)
    
    # 显示最近的任务
    if progress.get("details"):
        print("\n最近任务：")
        for detail in progress["details"][-10:]:
            status_icon = "✅" if detail["status"] == "completed" else "❌"
            print(f"  {status_icon} {detail['character']} - {detail['status']} ({detail['time']})")


def main():
    parser = argparse.ArgumentParser(description="批量爬取动漫角色图片（支持断点续爬）")
    parser.add_argument("--resume", action="store_true", help="从中断处继续（默认行为）")
    parser.add_argument("--reset", action="store_true", help="重置所有状态为 pending")
    parser.add_argument("--status", action="store_true", help="查看爬取进度")
    parser.add_argument("--limit", type=int, help="限制处理角色数量（测试用）")
    parser.add_argument("--priority", type=int, help="只处理指定优先级的角色")
    args = parser.parse_args()
    
    # 加载配置
    config = load_config()
    if not config:
        return
    
    args.total = len(config["characters"])
    
    # 查看进度
    if args.status:
        progress = load_progress()
        show_status(config, progress)
        return
    
    # 重置状态
    if args.reset:
        for char in config["characters"]:
            char["status"] = "pending"
        save_config(config)
        # 删除进度文件
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()
        logger.info("✅ 已重置所有状态为 pending")
        return
    
    # 加载进度
    progress = load_progress()
    
    # 筛选待处理角色
    characters_to_process = [c for c in config["characters"] if c["status"] == "pending"]
    
    if args.priority:
        characters_to_process = [c for c in characters_to_process if c["priority"] == args.priority]
    
    if args.limit:
        characters_to_process = characters_to_process[:args.limit]
    
    if not characters_to_process:
        logger.info("✅ 所有角色已处理完成！")
        show_status(config, progress)
        return
    
    logger.info(f"🚀 开始批量爬取：{len(characters_to_process)} 个角色待处理")
    
    # 处理每个角色
    for i, char_cfg in enumerate(characters_to_process, 1):
        logger.info(f"\n[{i}/{len(characters_to_process)}] 当前角色：{char_cfg['character_cn']}")
        
        try:
            status = process_character(char_cfg, args)
            
            # 更新配置状态
            for char in config["characters"]:
                if char["id"] == char_cfg["id"]:
                    char["status"] = status
                    char["last_processed"] = datetime.now().isoformat()
                    break
            
            # 更新进度
            progress["last_run"] = datetime.now().isoformat()
            progress["completed"] = sum(1 for c in config["characters"] if c["status"] == "completed")
            progress["failed"] = sum(1 for c in config["characters"] if c["status"] == "failed")
            progress["details"].append({
                "character": char_cfg["character_cn"],
                "status": status,
                "time": datetime.now().isoformat(),
            })
            
            # 保存（每完成一个角色保存一次，支持断点续爬）
            save_config(config)
            save_progress(progress)
            
            logger.info(f"✅ 角色 {char_cfg['character_cn']} 处理完成 ({i}/{len(characters_to_process)})")
            
            # 限速（避免 API 限制）
            if i < len(characters_to_process):
                logger.info(f"⏸️  等待 5 秒后继续下一个角色...")
                time.sleep(5)
        
        except KeyboardInterrupt:
            logger.warning("\n⚠️  用户中断，进度已保存，可重启后继续")
            save_config(config)
            save_progress(progress)
            return
        
        except Exception as e:
            logger.error(f"❌ 处理角色 {char_cfg['character_cn']} 时出错: {e}")
            # 更新状态为 failed
            for char in config["characters"]:
                if char["id"] == char_cfg["id"]:
                    char["status"] = "failed"
                    break
            save_config(config)
            save_progress(progress)
            continue
    
    # 完成
    logger.info("=" * 80)
    logger.info("🎉 批量爬取完成！")
    show_status(config, progress)
    logger.info("=" * 80)
    logger.info("📦 下一步：")
    logger.info("  1. 将 data/user_labeled/ 复制到设备 C")
    logger.info("  2. 设备 C 运行：python scripts/train_on_device_c.py")
    logger.info("  3. 训练完成后，将新模型复制到设备 A")
    logger.info("  4. 设备 A 运行：python scripts/replace_model_on_device_a.py")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
