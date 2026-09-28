"""
module2_model/evaluator.py - 模型评估器（修复版）
修复：
  - 从 checkpoint 读取 active_classes，不再依赖 config.py 的 20 类列表
  - 使用 FilteredDataset 确保评估时类别索引与训练一致
  - predict_single / evaluate_dataset 均使用动态类别列表
"""
import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    IMAGE_SIZE, MEAN, STD,
    ANIME_CHARACTERS, MODELS_DIR, PROCESSED_DIR, LOGS_DIR,
)
from module2_model.models import AnimeRecognitionModel


# ==============================
# 推理变换
# ==============================
INFERENCE_TRANSFORM = transforms.Compose([
    transforms.Resize(int(IMAGE_SIZE * 1.14)),
    transforms.CenterCrop(IMAGE_SIZE),
    transforms.ToTensor(),
    transforms.Normalize(MEAN, STD),
])


# ==============================
# 与 trainer.py 一致的过滤数据集
# ==============================
IMG_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tif', '.tiff')


class FilteredDataset(torch.utils.data.Dataset):
    """仅加载活跃角色目录的图像（与 trainer.py 一致）"""
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


def get_active_classes(data_root: str) -> List[str]:
    """
    从数据集目录自动推断活跃类别（排除空文件夹）
    与 trainer.py 的 _build_dataloaders 逻辑一致
    """
    train_dir = Path(data_root) / "train"
    if not train_dir.exists():
        return []
    active = sorted([
        d.name for d in train_dir.iterdir()
        if d.is_dir() and any(d.iterdir())
    ])
    return active


class AnimeEvaluator:
    """动漫角色识别模型评估器（修复版）"""

    def __init__(
        self,
        model_path: str,
        data_root: str = None,
        device: str = None,
    ):
        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        print(f"加载模型: {model_path}")
        self.model = AnimeRecognitionModel.load(model_path, str(self.device))
        self.model.to(self.device)
        self.model.eval()
        print(f"模型加载完成，运行设备: {self.device}")

        # ===== 修复核心：获取与训练一致的类别列表 =====
        ckpt = torch.load(model_path, map_location="cpu")

        # 优先从 checkpoint 读取 active_classes
        if "active_classes" in ckpt:
            self.active_classes = ckpt["active_classes"]
            print(f"  从 checkpoint 读取类别列表: {len(self.active_classes)} 类")
        else:
            # 回退：从数据集目录推断
            if data_root is None:
                data_root = str(Path(PROCESSED_DIR).parent)
            self.active_classes = get_active_classes(data_root)
            print(f"  从数据集推断类别列表: {len(self.active_classes)} 类")

        self.num_classes = len(self.active_classes)
        self.class_to_idx = {name: i for i, name in enumerate(self.active_classes)}
        self.idx_to_class = {i: name for i, name in enumerate(self.active_classes)}

        # 用于 predict_single 的中文名映射
        self.class_info = {}
        for name in self.active_classes:
            info = ANIME_CHARACTERS.get(name, {})
            self.class_info[name] = {
                "name": info.get("name", name),
                "anime": info.get("anime", "未知"),
            }

    # ===== 单图预测 =====
    def predict_single(
        self,
        image_input,
        top_k: int = 5,
    ) -> List[Dict]:
        if isinstance(image_input, (str, Path)):
            img = Image.open(str(image_input)).convert('RGB')
        elif isinstance(image_input, Image.Image):
            img = image_input.convert('RGB')
        else:
            raise ValueError("image_input 必须是PIL图像或文件路径")

        img_tensor = INFERENCE_TRANSFORM(img).unsqueeze(0).to(self.device)

        with torch.no_grad():
            embedding, logits = self.model(img_tensor)
            probs = F.softmax(logits, dim=1)[0]

        top_k = min(top_k, self.num_classes)
        top_probs, top_indices = probs.topk(top_k)

        results = []
        for rank, (prob, idx) in enumerate(
            zip(top_probs.cpu().tolist(), top_indices.cpu().tolist()), start=1
        ):
            char_key = self.idx_to_class.get(idx, f"class_{idx}")
            info = self.class_info.get(char_key, {})
            results.append({
                "rank": rank,
                "character_key": char_key,
                "name": info.get("name", char_key),
                "anime": info.get("anime", "未知"),
                "confidence": round(prob * 100, 2),
                "class_id": idx,
            })

        return results

    # ===== 数据集批量评估 =====
    @torch.no_grad()
    def evaluate_dataset(
        self,
        data_dir: str,
        phase: str = "test",
    ) -> Dict:
        from torch.utils.data import DataLoader

        phase_dir = Path(data_dir) / phase
        if not phase_dir.exists():
            raise FileNotFoundError(f"数据目录不存在: {phase_dir}")

        dataset = FilteredDataset(
            phase_dir, self.active_classes, self.class_to_idx,
            transform=INFERENCE_TRANSFORM,
        )

        if len(dataset) == 0:
            raise RuntimeError(f"{phase_dir} 中没有找到有效图像")

        dataloader = DataLoader(dataset, batch_size=32, shuffle=False, num_workers=0)

        all_preds = []
        all_labels = []
        all_top5_correct = []

        for images, labels in dataloader:
            images = images.to(self.device)
            _, logits = self.model(images)

            _, top1_preds = logits.max(dim=1)
            all_preds.extend(top1_preds.cpu().tolist())
            all_labels.extend(labels.tolist())

            _, top5_preds = logits.topk(min(5, self.num_classes), dim=1)
            for i, label in enumerate(labels):
                all_top5_correct.append(label.item() in top5_preds[i].cpu().tolist())

        all_preds = np.array(all_preds)
        all_labels = np.array(all_labels)
        all_top5_correct = np.array(all_top5_correct)

        n = len(all_labels)
        top1_acc = (all_preds == all_labels).sum() / n * 100
        top5_acc = all_top5_correct.sum() / n * 100

        # 平均每类精确率
        class_acc = []
        for cls_id in range(self.num_classes):
            cls_mask = all_labels == cls_id
            if cls_mask.sum() == 0:
                continue
            cls_acc = (all_preds[cls_mask] == cls_id).sum() / cls_mask.sum()
            class_acc.append(cls_acc)
        mean_acc = np.mean(class_acc) * 100 if class_acc else 0

        # 每类详细报告
        per_class_report = {}
        for cls_id in range(self.num_classes):
            char_key = self.active_classes[cls_id]
            info = self.class_info.get(char_key, {})
            cls_mask = all_labels == cls_id
            n_cls = cls_mask.sum()
            if n_cls == 0:
                continue
            correct = (all_preds[cls_mask] == cls_id).sum()
            per_class_report[char_key] = {
                "name": info.get("name", char_key),
                "anime": info.get("anime", ""),
                "total": int(n_cls),
                "correct": int(correct),
                "accuracy": round(correct / n_cls * 100, 2),
            }

        report = {
            "total_samples": n,
            "top1_accuracy": round(top1_acc, 2),
            "top5_accuracy": round(top5_acc, 2),
            "mean_per_class_accuracy": round(mean_acc, 2),
            "per_class": per_class_report,
        }

        return report

    def print_evaluation_report(self, report: Dict):
        print("\n" + "=" * 70)
        print("模型评估报告")
        print("=" * 70)
        print(f"总样本数:          {report['total_samples']}")
        print(f"Top-1 准确率:      {report['top1_accuracy']:.2f}%")
        print(f"Top-5 准确率:      {report['top5_accuracy']:.2f}%")
        print(f"平均每类精确率:    {report['mean_per_class_accuracy']:.2f}%")
        print()
        print(f"{'角色名':<20} {'作品':<15} {'样本数':>8} {'正确':>6} {'准确率':>8}")
        print("-" * 70)

        for char_key, info in report["per_class"].items():
            print(
                f"{info['name']:<20} {info['anime']:<15} "
                f"{info['total']:>8} {info['correct']:>6} {info['accuracy']:>7.1f}%"
            )
        print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="动漫角色识别模型评估")
    parser.add_argument("--model", "-m", type=str, required=True,
                        help="模型权重文件路径")
    parser.add_argument("--image", "-i", type=str, default=None,
                        help="单张图像预测")
    parser.add_argument("--data-dir", "-d", type=str, default=None,
                        help="数据集根目录（用于批量评估）")
    parser.add_argument("--phase", default="test",
                        choices=["train", "val", "test"])
    parser.add_argument("--topk", type=int, default=5)
    args = parser.parse_args()

    # data_dir 用于推断 active_classes（当 checkpoint 不含此信息时）
    data_root = None
    if args.data_dir:
        data_root = args.data_dir
    elif args.image:
        # 尝试从模型路径推断 data_root
        model_path = Path(args.model)
        # models/mobilenet_19chars/best_model.pth -> 往上两级是项目根目录
        project_root = model_path.parent.parent
        candidate = project_root / "data"
        if candidate.exists():
            data_root = str(candidate)

    evaluator = AnimeEvaluator(args.model, data_root=data_root)

    if args.image:
        print(f"\n预测图像: {args.image}")
        results = evaluator.predict_single(args.image, top_k=args.topk)
        print(f"\n识别结果 (Top-{args.topk}):")
        for r in results:
            print(f"  #{r['rank']} {r['name']} ({r['anime']}) - {r['confidence']:.1f}%")

    elif args.data_dir:
        report = evaluator.evaluate_dataset(args.data_dir, args.phase)
        evaluator.print_evaluation_report(report)

        report_path = Path(LOGS_DIR) / "evaluation_report.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n报告已保存: {report_path}")

    else:
        print("请指定 --image 或 --data-dir 参数")
