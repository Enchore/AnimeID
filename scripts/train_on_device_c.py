"""
设备C：训练模型（确保与设备 A 类别一致）
用法：python scripts/train_on_device_c.py --data-dir ../data --output-dir ../models/auto_v1
"""
import os
import sys
import json
import argparse
import logging
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from config import ANIME_CHARACTERS, NUM_CLASSES, CLASS_NAMES

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def check_class_consistency():
    """
    检查设备 C 的 CLASS_NAMES 是否与设备 A 一致
    ⚠️ 这是最关键的一步！类别不一致会导致模型无法使用
    """
    logger.info("=" * 80)
    logger.info("检查类别一致性（设备 C vs 设备 A）")
    logger.info("=" * 80)

    # 当前配置的类别数
    logger.info(f"当前 CLASS_NAMES 数量: {len(CLASS_NAMES)}")
    logger.info(f"当前 NUM_CLASSES: {NUM_CLASSES}")

    # 建议：从设备 A 复制 config.py
    logger.info("")
    logger.info("⚠️ 重要提示：")
    logger.info("  设备 C 的 config.py 必须与设备 A 完全相同！")
    logger.info("  特别是以下字段：")
    logger.info("    - ANIME_CHARACTERS（角色库）")
    logger.info("    - CLASS_NAMES（类别列表）")
    logger.info("    - NUM_CLASSES（类别数）")
    logger.info("")
    logger.info("建议操作：")
    logger.info("  1. 从设备 A 复制 config.py 到设备 C")
    logger.info("  2. 或者手动确保两个文件的角色库完全一致")
    logger.info("=" * 80)


def prepare_training_data(data_dir: str, output_dir: str):
    """
    准备训练数据：
    1. 扫描 data/user_labeled/ 目录
    2. 检查每个类别的图片数量
    3. 生成训练报告
    """
    data_path = Path(data_dir)
    if not data_path.exists():
        logger.error(f"数据目录不存在: {data_dir}")
        return False

    user_labeled = data_path / "user_labeled"
    if not user_labeled.exists():
        logger.error(f"user_labeled 目录不存在: {user_labeled}")
        return False

    # 统计每个类别的图片数
    logger.info(f"扫描训练数据: {user_labeled}")
    stats = {}
    for char_dir in user_labeled.iterdir():
        if not char_dir.is_dir():
            continue
        img_count = len(list(char_dir.glob("*.*")))
        stats[char_dir.name] = img_count

    # 输出统计
    logger.info("=" * 80)
    logger.info("训练数据统计：")
    total = 0
    for char_key, count in sorted(stats.items(), key=lambda x: -x[1]):
        logger.info(f"  {char_key}: {count} 张")
        total += count
    logger.info("=" * 80)
    logger.info(f"总计: {len(stats)} 个类别，{total} 张图片")
    logger.info("=" * 80)

    # 检查是否满足训练条件
    if total < 20:
        logger.warning(f"⚠️ 图片总数不足 20 张，可能触发不了自动训练")
        return False

    min_count = min(stats.values()) if stats else 0
    if min_count < 5:
        logger.warning(f"⚠️ 某些类别图片数 < 5 张，建议增加数据")

    return True


def run_training(data_dir: str, output_dir: str):
    """
    运行训练（调用 module5_autotrain）
    """
    logger.info("=" * 80)
    logger.info("开始训练...")
    logger.info("=" * 80)

    # 导入训练模块
    try:
        from module5_autotrain.train_worker import main as train_main
        import sys
        # 模拟命令行参数
        sys.argv = [
            "train_worker.py",
            "--data-dir", data_dir,
            "--output-dir", output_dir,
        ]
        train_main()
    except Exception as e:
        logger.error(f"训练失败: {e}")
        return False

    logger.info("=" * 80)
    logger.info("训练完成！")
    logger.info(f"模型保存在: {output_dir}")
    logger.info("=" * 80)
    return True


def main():
    parser = argparse.ArgumentParser(description="设备C：训练模型（确保类别一致）")
    parser.add_argument("--data-dir", type=str, help="数据目录", default="../data")
    parser.add_argument("--output-dir", type=str, help="模型输出目录", default="../models/auto_v1")
    parser.add_argument("--skip-check", action="store_true", help="跳过类别一致性检查（不推荐）")
    parser.add_argument("--only-check", action="store_true", help="只检查数据，不训练")
    args = parser.parse_args()

    # Step 1: 检查类别一致性
    if not args.skip_check:
        check_class_consistency()
        if not args.only_check:
            input("按 Enter 确认设备 C 的 config.py 已与设备 A 同步...")

    # Step 2: 准备训练数据
    if not prepare_training_data(args.data_dir, args.output_dir):
        if not args.only_check:
            logger.error("训练数据准备失败，退出")
            return

    if args.only_check:
        logger.info("数据检查完成，不执行训练")
        return

    # Step 3: 运行训练
    if not run_training(args.data_dir, args.output_dir):
        return

    # Step 4: 提示下一步
    logger.info("")
    logger.info("下一步：将以下文件复制到设备 A")
    logger.info(f"  {args.output_dir}/")
    logger.info("  包含：best_model.pth, config.json, class_names.json 等")
    logger.info("")


if __name__ == "__main__":
    main()
