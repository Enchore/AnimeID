"""
module2_model/trainer.py - 模型训练器
实现：
    - 迁移学习（分阶段解冻骨干网络）
    - 分层学习率（骨干网络使用更小的学习率）
    - LabelSmoothing防止过拟合
    - 学习率调度（CosineAnnealingLR）
    - 训练日志记录
    - 最优模型保存（基于验证集准确率）
"""
import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import datasets, transforms

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    IMAGE_SIZE, MEAN, STD,
    BATCH_SIZE, NUM_EPOCHS, BASE_LR, BACKBONE_LR,
    WEIGHT_DECAY, NUM_CLASSES, MODEL_BACKBONE, LOSS_TYPE,
    EMBEDDING_SIZE, MODELS_DIR, LOGS_DIR,
    PROCESSED_DIR
)
from module2_model.models import build_model
from module2_model.losses import build_loss


# ===========================
# 数据变换
# ===========================
def get_transforms(phase: str):
    """
    获取数据增强变换
    
    训练集：随机水平翻转、随机裁剪、颜色抖动
    验证/测试集：仅中心裁剪和归一化
    """
    if phase == "train":
        return transforms.Compose([
            transforms.RandomResizedCrop(IMAGE_SIZE, scale=(0.8, 1.0)),
            transforms.RandomHorizontalFlip(),
            transforms.ColorJitter(
                brightness=0.3, contrast=0.3,
                saturation=0.3, hue=0.1
            ),
            transforms.RandomRotation(15),
            transforms.ToTensor(),
            transforms.Normalize(MEAN, STD),
        ])
    else:
        return transforms.Compose([
            transforms.Resize(int(IMAGE_SIZE * 1.14)),
            transforms.CenterCrop(IMAGE_SIZE),
            transforms.ToTensor(),
            transforms.Normalize(MEAN, STD),
        ])


# ===========================
# 评估指标
# ===========================
def compute_accuracy(outputs: torch.Tensor, labels: torch.Tensor, topk=(1, 5)) -> dict:
    """
    计算Top-K准确率
    
    Args:
        outputs: 模型logits (B, num_classes)
        labels: 真实标签 (B,)
        topk: 计算哪几个K值
    
    Returns:
        dict: {'top1': float, 'top5': float}
    """
    with torch.no_grad():
        maxk = max(topk)
        batch_size = labels.size(0)

        _, pred = outputs.topk(maxk, dim=1, largest=True, sorted=True)
        pred = pred.t()   # (maxk, B)
        correct = pred.eq(labels.view(1, -1).expand_as(pred))  # (maxk, B)

        results = {}
        for k in topk:
            correct_k = correct[:k].reshape(-1).float().sum()
            results[f"top{k}"] = (correct_k / batch_size * 100).item()

        return results


# ===========================
# 主训练器
# ===========================
class AnimeTrainer:
    """动漫角色识别模型训练器"""

    def __init__(
        self,
        data_root: str = PROCESSED_DIR,
        backbone: str = MODEL_BACKBONE,
        loss_type: str = LOSS_TYPE,
        num_classes: int = NUM_CLASSES,
        batch_size: int = BATCH_SIZE,
        epochs: int = NUM_EPOCHS,
        base_lr: float = BASE_LR,
        backbone_lr: float = BACKBONE_LR,
        weight_decay: float = WEIGHT_DECAY,
        device: str = None,
        experiment_name: str = None,
    ):
        self.data_root = Path(data_root).parent  # 数据集根目录（包含train/val/test）
        self.batch_size = batch_size
        self.epochs = epochs
        self.base_lr = base_lr
        self.backbone_lr = backbone_lr
        self.num_classes = num_classes  # 可能被 _build_dataloaders 动态调整

        # 设备
        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)
        print(f"训练设备: {self.device}")

        # 实验名称（用于保存路径）
        self.experiment_name = experiment_name or (
            f"{backbone}_{loss_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        self.save_dir = Path(MODELS_DIR) / self.experiment_name
        # 确保是绝对路径
        self.save_dir = self.save_dir.resolve()
        self.save_dir.mkdir(parents=True, exist_ok=True)

        # 日志
        self.log_path = Path(LOGS_DIR) / f"{self.experiment_name}.json"
        self.history = {
            "train_loss": [], "val_loss": [],
            "train_top1": [], "val_top1": [],
            "train_top5": [], "val_top5": [],
            "lr": [],
        }

        # 初始化组件（num_classes 可能被 _build_dataloaders 动态调整）
        self._build_dataloaders()
        self._build_model(backbone, self.num_classes)
        self._build_optimizer(loss_type, self.num_classes)

    def _build_dataloaders(self):
        """构建数据加载器（自动过滤无数据的角色目录）"""
        from PIL import Image
        
        train_dir = self.data_root / "train"
        active_classes = sorted([
            d.name for d in train_dir.iterdir()
            if d.is_dir() and any(d.iterdir())
        ])
        
        if not active_classes:
            raise RuntimeError(f"train 目录中没有找到任何图像数据: {train_dir}")
        
        # 动态调整分类数
        original_num = self.num_classes
        self.num_classes = len(active_classes)
        if self.num_classes != original_num:
            print(f"  [适配] 仅 {self.num_classes}/{original_num} 个角色有数据，自动调整分类数")
        
        # 建立连续标签映射
        self.class_to_idx = {name: i for i, name in enumerate(active_classes)}
        self.idx_to_class = {i: name for name, i in self.class_to_idx.items()}
        print(f"  活跃角色: {active_classes}")
        self.active_classes = active_classes  # 保存活跃角色列表
        
        # 图像扩展名
        IMG_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tif', '.tiff')
        
        class FilteredDataset(torch.utils.data.Dataset):
            """仅加载活跃角色目录的图像"""
            def __init__(self, root, active_classes, class_to_idx, transform=None):
                self.samples = []
                self.targets = []
                root = Path(root)
                for cls_name in active_classes:
                    cls_dir = root / cls_name
                    if not cls_dir.is_dir():
                        continue
                    for ext in IMG_EXTENSIONS:
                        for p in cls_dir.glob(f'*{ext}'):
                            self.samples.append(p)
                            self.targets.append(class_to_idx[cls_name])
                        for p in cls_dir.glob(f'*{ext.upper()}'):
                            self.samples.append(p)
                            self.targets.append(class_to_idx[cls_name])
                self.transform = transform
            
            def __len__(self):
                return len(self.samples)
            
            def __getitem__(self, idx):
                img = Image.open(self.samples[idx]).convert('RGB')
                if self.transform:
                    img = self.transform(img)
                return img, self.targets[idx]
        
        # 构建各阶段 DataLoader
        self.dataloaders = {}
        for phase in ("train", "val", "test"):
            phase_dir = self.data_root / phase
            if not phase_dir.exists():
                print(f"  [警告] {phase} 目录不存在: {phase_dir}")
                continue
            
            dataset = FilteredDataset(
                phase_dir, active_classes, self.class_to_idx,
                transform=get_transforms(phase)
            )
            
            if len(dataset) == 0:
                print(f"  [跳过] {phase}: 无有效样本")
                continue
            
            self.dataloaders[phase] = DataLoader(
                dataset,
                batch_size=self.batch_size,
                shuffle=(phase == "train"),
                num_workers=0,
                pin_memory=self.device.type == "cuda",
            )
            
            # 统计每个角色的样本数
            from collections import Counter
            class_counts = Counter(
                active_classes[t] for t in dataset.targets
            )
            
            print(f"  {phase}: {len(dataset)} 张图像, "
                  f"{len(self.dataloaders[phase])} 批次")
            print(f"    角色分布: {dict(class_counts)}")

    def _build_model(self, backbone: str, num_classes: int):
        """构建模型（迁移学习：初始冻结骨干）"""
        self.model = build_model(
            backbone=backbone,
            num_classes=num_classes,
            pretrained=True,
            freeze_backbone=True,   # 第一阶段冻结骨干
        ).to(self.device)

    def _build_optimizer(self, loss_type: str, num_classes: int):
        """构建优化器和损失函数"""
        self.criterion = build_loss(loss_type, EMBEDDING_SIZE, num_classes).to(self.device)

        # 分层学习率
        param_groups = [
            {
                "params": list(self.model.get_head_parameters()) +
                          list(self.criterion.parameters()),
                "lr": self.base_lr,
                "name": "head",
            },
            {
                "params": self.model.get_backbone_parameters(),
                "lr": self.backbone_lr,
                "name": "backbone",
            },
        ]
        self.optimizer = optim.AdamW(param_groups, weight_decay=WEIGHT_DECAY)

        # CosineAnnealing学习率调度
        self.scheduler = optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer, T_max=self.epochs, eta_min=1e-6
        )

    def _train_epoch(self, epoch: int) -> dict:
        """训练一个Epoch"""
        self.model.train()
        if hasattr(self.criterion, 'metric_loss') and self.criterion.metric_loss:
            self.criterion.metric_loss.train()

        total_loss = 0.0
        total_top1 = 0.0
        total_top5 = 0.0
        n_batches = 0

        if "train" not in self.dataloaders:
            return {"loss": 0, "top1": 0, "top5": 0}

        for batch_idx, (images, labels) in enumerate(self.dataloaders["train"]):
            images = images.to(self.device)
            labels = labels.to(self.device)

            self.optimizer.zero_grad()

            # 前向传播
            embedding, logits = self.model(images)
            loss, metric_loss, aux_loss = self.criterion(embedding, logits, labels)

            # 反向传播
            loss.backward()
            nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=5.0)
            self.optimizer.step()

            # 统计
            acc = compute_accuracy(logits, labels, topk=(1, 5))
            total_loss += loss.item()
            total_top1 += acc["top1"]
            total_top5 += acc["top5"]
            n_batches += 1

            if (batch_idx + 1) % 10 == 0:
                print(
                    f"    [{batch_idx+1}/{len(self.dataloaders['train'])}] "
                    f"Loss: {loss.item():.4f} | "
                    f"Top-1: {acc['top1']:.1f}% | Top-5: {acc['top5']:.1f}%"
                )

        return {
            "loss": total_loss / max(n_batches, 1),
            "top1": total_top1 / max(n_batches, 1),
            "top5": total_top5 / max(n_batches, 1),
        }

    @torch.no_grad()
    def _evaluate(self, phase: str = "val") -> dict:
        """在验证/测试集上评估"""
        self.model.eval()
        if hasattr(self.criterion, 'metric_loss') and self.criterion.metric_loss:
            self.criterion.metric_loss.eval()

        if phase not in self.dataloaders:
            return {"loss": 0, "top1": 0, "top5": 0}

        total_loss = 0.0
        total_top1 = 0.0
        total_top5 = 0.0
        n_batches = 0

        for images, labels in self.dataloaders[phase]:
            images = images.to(self.device)
            labels = labels.to(self.device)

            embedding, logits = self.model(images)
            loss, _, _ = self.criterion(embedding, logits, labels)

            acc = compute_accuracy(logits, labels, topk=(1, 5))
            total_loss += loss.item()
            total_top1 += acc["top1"]
            total_top5 += acc["top5"]
            n_batches += 1

        return {
            "loss": total_loss / max(n_batches, 1),
            "top1": total_top1 / max(n_batches, 1),
            "top5": total_top5 / max(n_batches, 1),
        }

    def train(self, unfreeze_epoch: int = 10):
        """
        执行完整训练流程
        
        两阶段迁移学习：
            第1~unfreeze_epoch轮：仅训练头部（骨干冻结）
            之后：解冻骨干，全网络微调（分层学习率）
        
        Args:
            unfreeze_epoch: 解冻骨干的轮次（默认第10轮）
        """
        best_val_top1 = 0.0
        best_epoch = 0

        print(f"\n{'='*60}")
        print(f"开始训练: {self.experiment_name}")
        print(f"总轮数: {self.epochs} | 解冻骨干: 第{unfreeze_epoch}轮")
        print(f"{'='*60}")

        for epoch in range(1, self.epochs + 1):
            # 第unfreeze_epoch轮解冻骨干网络
            if epoch == unfreeze_epoch:
                print(f"\n>>> Epoch {epoch}: 解冻骨干网络，开始全网络微调 <<<")
                self.model.unfreeze_backbone()

            print(f"\nEpoch [{epoch}/{self.epochs}]")
            
            # 训练
            train_metrics = self._train_epoch(epoch)
            
            # 验证
            val_metrics = self._evaluate("val")

            # 学习率调度
            self.scheduler.step()
            current_lr = self.optimizer.param_groups[0]["lr"]

            # 记录历史
            self.history["train_loss"].append(train_metrics["loss"])
            self.history["val_loss"].append(val_metrics["loss"])
            self.history["train_top1"].append(train_metrics["top1"])
            self.history["val_top1"].append(val_metrics["top1"])
            self.history["train_top5"].append(train_metrics["top5"])
            self.history["val_top5"].append(val_metrics["top5"])
            self.history["lr"].append(current_lr)

            print(
                f"  训练 | Loss: {train_metrics['loss']:.4f} | "
                f"Top-1: {train_metrics['top1']:.2f}% | Top-5: {train_metrics['top5']:.2f}%"
            )
            print(
                f"  验证 | Loss: {val_metrics['loss']:.4f} | "
                f"Top-1: {val_metrics['top1']:.2f}% | Top-5: {val_metrics['top5']:.2f}%"
            )
            print(f"  LR: {current_lr:.2e}")

            # 保存最优模型
            if val_metrics["top1"] > best_val_top1:
                best_val_top1 = val_metrics["top1"]
                best_epoch = epoch
                best_path = str(self.save_dir / "best_model.pth")
                self.model.save(best_path, {
                    "epoch": epoch,
                    "val_top1": best_val_top1,
                    "optimizer_state": self.optimizer.state_dict(),
                    "active_classes": self.active_classes,
                })
                print(f"  ★ 最优模型已保存 (Top-1: {best_val_top1:.2f}%)")

            # 每10轮保存检查点
            if epoch % 10 == 0:
                ckpt_path = str(self.save_dir / f"checkpoint_epoch{epoch:03d}.pth")
                self.model.save(ckpt_path, {"epoch": epoch})

            # 保存训练历史（每轮都写，防止中断丢失）
            with open(self.log_path, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2)

        print(f"\n{'='*60}")
        print(f"训练完成！最优Epoch: {best_epoch} | 最优验证Top-1: {best_val_top1:.2f}%")
        print(f"模型保存路径: {self.save_dir}")
        print(f"{'='*60}")

        # 最终测试集评估
        if "test" in self.dataloaders:
            print("\n评估测试集...")
            test_metrics = self._evaluate("test")
            print(
                f"测试集 | Top-1: {test_metrics['top1']:.2f}% | "
                f"Top-5: {test_metrics['top5']:.2f}%"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="动漫角色识别模型训练")
    parser.add_argument("--backbone", default=MODEL_BACKBONE,
                        choices=["resnet50", "mobilenet_v2"])
    parser.add_argument("--loss", default=LOSS_TYPE,
                        choices=["arcface", "cosface", "softmax"])
    parser.add_argument("--epochs", type=int, default=NUM_EPOCHS)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--lr", type=float, default=BASE_LR)
    parser.add_argument("--unfreeze-epoch", type=int, default=10,
                        help="第几轮解冻骨干网络")
    parser.add_argument("--name", type=str, default=None,
                        help="实验名称")
    args = parser.parse_args()

    trainer = AnimeTrainer(
        backbone=args.backbone,
        loss_type=args.loss,
        batch_size=args.batch_size,
        epochs=args.epochs,
        base_lr=args.lr,
        experiment_name=args.name,
    )
    trainer.train(unfreeze_epoch=args.unfreeze_epoch)
