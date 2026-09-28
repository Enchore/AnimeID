"""
设备A：替换模型（自动备份 + 热加载）
用法：
  1. 将新模型放到 models/new/ 目录
  2. 运行：python scripts/replace_model_on_device_a.py
  3. 脚本会自动备份旧模型、替换新模型、重启服务
"""
import os
import sys
import json
import shutil
import subprocess
import argparse
import logging
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# 默认路径
MODELS_DIR = SCRIPT_DIR / "models"
CURRENT_MODEL_DIR = MODELS_DIR / "auto_v1"
NEW_MODEL_DIR = MODELS_DIR / "new"  # 新模型放这里
BACKUP_DIR = MODELS_DIR / "backups"


def backup_current_model():
    """备份当前模型"""
    if not CURRENT_MODEL_DIR.exists():
        logger.warning(f"当前模型目录不存在，跳过备份: {CURRENT_MODEL_DIR}")
        return True

    # 创建备份目录
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # 备份文件名（带时间戳）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"auto_v1_backup_{timestamp}"
    
    try:
        shutil.copytree(CURRENT_MODEL_DIR, backup_path)
        logger.info(f"✓ 备份完成: {CURRENT_MODEL_DIR} → {backup_path}")
        return True
    except Exception as e:
        logger.error(f"✗ 备份失败: {e}")
        return False


def validate_new_model(new_model_dir: Path):
    """验证新模型文件是否完整"""
    logger.info(f"验证新模型: {new_model_dir}")
    
    if not new_model_dir.exists():
        logger.error(f"✗ 新模型目录不存在: {new_model_dir}")
        return False

    # 必需文件
    required_files = [
        "best_model.pth",
        "config.json",
        "class_names.json",
    ]
    
    missing = []
    for f in required_files:
        if not (new_model_dir / f).exists():
            missing.append(f)
    
    if missing:
        logger.error(f"✗ 缺少必需文件: {missing}")
        return False

    # 验证 class_names.json 是否与当前系统兼容
    try:
        with open(new_model_dir / "class_names.json", "r") as f:
            new_classes = json.load(f)
        
        # 检查是否是同一个项目（通过角色数判断）
        if len(new_classes) < 19:  # 已知角色至少 19 个
            logger.warning(f"⚠️ 新模型的类别数 ({len(new_classes)}) 少于 19，可能有问题")
        
        logger.info(f"✓ 新模型类别数: {len(new_classes)}")
    except Exception as e:
        logger.error(f"✗ 无法读取 class_names.json: {e}")
        return False

    logger.info("✓ 新模型验证通过")
    return True


def replace_model(new_model_dir: Path):
    """替换模型"""
    logger.info("=" * 80)
    logger.info("开始替换模型...")
    logger.info("=" * 80)

    try:
        # 删除当前模型目录
        if CURRENT_MODEL_DIR.exists():
            shutil.rmtree(CURRENT_MODEL_DIR)
            logger.info(f"✓ 删除旧模型: {CURRENT_MODEL_DIR}")

        # 复制新模型
        shutil.copytree(new_model_dir, CURRENT_MODEL_DIR)
        logger.info(f"✓ 复制新模型: {new_model_dir} → {CURRENT_MODEL_DIR}")

        logger.info("=" * 80)
        logger.info("✓ 模型替换完成！")
        logger.info("=" * 80)
        return True

    except Exception as e:
        logger.error(f"✗ 模型替换失败: {e}")
        return False


def restart_flask():
    """重启 Flask 服务（尝试优雅重启）"""
    logger.info("=" * 80)
    logger.info("尝试重启 Flask 服务...")
    logger.info("=" * 80)

    # 方案 1：如果使用了 auto_reload（推荐）
    # 只需要重启 Python 进程，模型会自动重新加载
    logger.info("提示：")
    logger.info("  1. 如果使用 auto_reload，模型会在下次请求时自动重新加载")
    logger.info("  2. 否则，请手动重启 Flask：")
    logger.info("     - Ctrl+C 停掉服务")
    logger.info("     - 重新运行：python module3_web/app.py")
    logger.info("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="设备A：替换模型（自动备份 + 热加载）")
    parser.add_argument("--new-model-dir", type=str, help="新模型目录", default=str(NEW_MODEL_DIR))
    parser.add_argument("--skip-backup", action="store_true", help="跳过备份（不推荐）")
    parser.add_argument("--skip-validation", action="store_true", help="跳过验证（不推荐）")
    args = parser.parse_args()

    new_model_dir = Path(args.new_model_dir)

    # Step 1: 备份当前模型
    if not args.skip_backup:
        if not backup_current_model():
            logger.error("备份失败，退出")
            return

    # Step 2: 验证新模型
    if not args.skip_validation:
        if not validate_new_model(new_model_dir):
            logger.error("新模型验证失败，退出")
            return

    # Step 3: 替换模型
    if not replace_model(new_model_dir):
        logger.error("模型替换失败，退出")
        return

    # Step 4: 提示重启
    restart_flask()

    logger.info("")
    logger.info("完成！请重启 Flask 服务以使用新模型。")


if __name__ == "__main__":
    main()
