"""
module5_autotrain/train_worker.py - 训练子进程脚本

由 auto_trainer.py 通过 subprocess 调用，在独立进程中执行增量训练。
直接使用现有的 AnimeTrainer 进行训练。
"""
import os
import sys
import json
import argparse
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [TRAIN] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("train_worker")


def main():
    parser = argparse.ArgumentParser(description="自动训练子进程")
    parser.add_argument("--output-dir", required=True, help="模型输出目录 (如 models/auto_v3)")
    parser.add_argument("--epochs", type=int, default=15, help="训练轮数")
    parser.add_argument("--batch-size", type=int, default=32, help="批次大小")
    parser.add_argument("--unfreeze-epoch", type=int, default=5, help="解冻骨干的轮次")
    args = parser.parse_args()

    from config import (
        PROCESSED_DIR, MODELS_DIR, NUM_CLASSES,
        BASE_LR, BACKBONE_LR, WEIGHT_DECAY, LABEL_SMOOTHING,
    )
    from module2_model.trainer import AnimeTrainer

    # ===== 数据检查 =====
    train_dir = os.path.join(os.path.dirname(PROCESSED_DIR), "train")
    if not os.path.exists(train_dir):
        logger.error(f"训练目录不存在: {train_dir}")
        sys.exit(1)

    active_classes = sorted([
        d for d in os.listdir(train_dir)
        if os.path.isdir(os.path.join(train_dir, d))
        and d != "__pycache__"
        and any(
            f.lower().endswith(('.jpg','.jpeg','.png','.gif','.webp'))
            for f in os.listdir(os.path.join(train_dir, d))
        )
    ])
    logger.info(f"活跃类别 ({len(active_classes)}): {active_classes}")

    # ===== 创建训练器 =====
    # experiment_name = 输出目录名，trainer 会自动在 MODELS_DIR 下创建
    exp_name = os.path.basename(args.output_dir)  # e.g., "auto_v3"
    # 先删掉目标目录（trainer 会重建）
    if os.path.exists(args.output_dir):
        import shutil
        shutil.rmtree(args.output_dir)

    logger.info(f"开始增量训练: exp={exp_name}, epochs={args.epochs}, "
                f"batch={args.batch_size}, classes={len(active_classes)}")

    trainer = AnimeTrainer(
        data_root=PROCESSED_DIR,
        backbone="mobilenet_v2",
        loss_type="softmax",
        num_classes=NUM_CLASSES,
        batch_size=args.batch_size,
        epochs=args.epochs,
        base_lr=BASE_LR * 0.5,          # 增量训练降低学习率
        backbone_lr=BACKBONE_LR * 0.5,
        weight_decay=WEIGHT_DECAY,
        experiment_name=exp_name,
    )

    # ===== 执行训练 =====
    trainer.train(unfreeze_epoch=args.unfreeze_epoch)

    # ===== 后处理：复制到指定输出目录 =====
    src_dir = trainer.save_dir.resolve()  # 转为绝对路径
    dst_dir = Path(args.output_dir).resolve()  # 转为绝对路径

    if src_dir != dst_dir:
        import shutil
        # 确保目标目录干净
        if dst_dir.exists():
            shutil.rmtree(dst_dir)
        # 检查源目录是否存在
        if not src_dir.exists():
            logger.error(f"源目录不存在: {src_dir}")
            logger.error(f"训练可能失败，请检查日志")
            sys.exit(1)
        shutil.copytree(src_dir, dst_dir)
        logger.info(f"模型从 {src_dir} 复制到 {dst_dir}")
    else:
        logger.info(f"模型已保存在: {dst_dir}")

    # 保存类别信息
    class_info = {
        "active_classes": active_classes,
        "class_to_idx": {c: i for i, c in enumerate(active_classes)},
    }
    class_info_path = os.path.join(dst_dir, "class_info.json")
    with open(class_info_path, "w", encoding="utf-8") as f:
        json.dump(class_info, f, ensure_ascii=False, indent=2)

    logger.info(f"训练完成: {dst_dir}")
    logger.info(f"最佳模型: {dst_dir}/best_model.pth")


if __name__ == "__main__":
    main()
