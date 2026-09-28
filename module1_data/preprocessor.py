"""
module1_data/preprocessor.py - 图像预处理模块（优化版：支持禁用水印/字幕处理）
功能：
    - 图像裁剪（去除边框/字幕区域）
    - 去除水印（基于亮度阈值）
    - 尺寸标准化（224×224）
    - 格式统一（RGB模式）
    - 质量过滤（模糊度检测）
    - 数据集划分（train/val/test）
"""
import os
import sys
import shutil
import argparse
import json
from pathlib import Path
from typing import Tuple, Optional

import cv2
import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    RAW_DIR, PROCESSED_DIR, IMAGE_SIZE, ANIME_CHARACTERS,
    TRAIN_RATIO, VAL_RATIO, TEST_RATIO
)


class ImagePreprocessor:
    """动漫图像预处理器"""

    def __init__(
        self,
        input_dir: str = RAW_DIR,
        output_dir: str = PROCESSED_DIR,
        target_size: Tuple[int, int] = (IMAGE_SIZE, IMAGE_SIZE),
        blur_threshold: float = 100.0,
        remove_subtitle: bool = True,
        remove_watermark: bool = True,
    ):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.target_size = target_size
        self.blur_threshold = blur_threshold
        self.remove_subtitle_flag = remove_subtitle
        self.remove_watermark_flag = remove_watermark

    def detect_blur(self, img_array: np.ndarray) -> float:
        gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)
        return cv2.Laplacian(gray, cv2.CV_64F).var()

    def remove_subtitle_region(self, img_array: np.ndarray, ratio: float = 0.12) -> np.ndarray:
        h, w = img_array.shape[:2]
        crop_h = int(h * ratio)
        return img_array[:h - crop_h, :]

    def detect_and_remove_watermark(self, img_array: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)
        _, bright_mask = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        bright_mask = cv2.morphologyEx(bright_mask, cv2.MORPH_CLOSE, kernel)
        bright_ratio = np.sum(bright_mask > 0) / (bright_mask.shape[0] * bright_mask.shape[1])
        if bright_ratio > 0.05:
            img_array = cv2.inpaint(img_array, bright_mask, 3, cv2.INPAINT_TELEA)
        return img_array

    def standardize_size(self, img: Image.Image) -> Image.Image:
        w, h = img.size
        scale = min(self.target_size[0] / w, self.target_size[1] / h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        img_resized = img.resize((new_w, new_h), Image.BILINEAR)  # 改用BILINEAR加速
        result = Image.new('RGB', self.target_size, (255, 255, 255))
        paste_x = (self.target_size[0] - new_w) // 2
        paste_y = (self.target_size[1] - new_h) // 2
        result.paste(img_resized, (paste_x, paste_y))
        return result

    def process_single_image(
        self,
        img_path: Path,
        output_path: Path,
        remove_subtitle: bool = None,
        remove_watermark: bool = None,
    ) -> bool:
        try:
            if remove_subtitle is None:
                remove_subtitle = self.remove_subtitle_flag
            if remove_watermark is None:
                remove_watermark = self.remove_watermark_flag

            img_bgr = cv2.imread(str(img_path))
            if img_bgr is None:
                print(f"    [错误] 无法读取: {img_path.name}")
                return False

            blur_score = self.detect_blur(img_bgr)
            if blur_score < self.blur_threshold:
                print(f"    [跳过] 图像过于模糊 (score={blur_score:.1f}): {img_path.name}")
                return False

            if remove_subtitle:
                img_bgr = self.remove_subtitle_region(img_bgr)
            if remove_watermark:
                img_bgr = self.detect_and_remove_watermark(img_bgr)

            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            img_pil = Image.fromarray(img_rgb)
            img_pil = self.standardize_size(img_pil)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            img_pil.save(str(output_path.with_suffix('.jpg')), 'JPEG', quality=95)
            return True

        except Exception as e:
            print(f"    [错误] 处理失败 {img_path.name}: {e}")
            return False

    def process_character(self, character_key: str) -> dict:
        char_input_dir = self.input_dir / character_key
        char_output_dir = self.output_dir / character_key
        char_output_dir.mkdir(parents=True, exist_ok=True)

        if not char_input_dir.exists():
            print(f"  [警告] 原始数据目录不存在: {char_input_dir}")
            return {"total": 0, "success": 0, "failed": 0}

        image_files = []
        for ext in ('*.jpg', '*.jpeg', '*.png', '*.gif', '*.webp'):
            image_files.extend(char_input_dir.glob(ext))

        char_info = ANIME_CHARACTERS.get(character_key, {})
        print(f"\n  处理角色: {char_info.get('name', character_key)} ({len(image_files)}张)")

        success, failed = 0, 0
        for i, img_path in enumerate(image_files):
            output_path = char_output_dir / f"{character_key}_{i:04d}.jpg"
            if self.process_single_image(img_path, output_path):
                success += 1
            else:
                failed += 1

        return {"total": len(image_files), "success": success, "failed": failed}

    def process_all(self) -> dict:
        print("\n" + "=" * 60)
        print("开始批量图像预处理")
        print("=" * 60)

        total_stats = {"total": 0, "success": 0, "failed": 0}
        char_stats = {}

        for char_key in ANIME_CHARACTERS:
            stats = self.process_character(char_key)
            char_stats[char_key] = stats
            for k in total_stats:
                total_stats[k] += stats[k]

        print(f"\n处理完成：总计 {total_stats['total']} 张")
        print(f"  成功: {total_stats['success']} 张")
        print(f"  失败: {total_stats['failed']} 张")

        return {"total": total_stats, "by_character": char_stats}

    def split_dataset(self) -> dict:
        import random
        random.seed(42)

        split_stats = {"train": 0, "val": 0, "test": 0}

        for char_key in ANIME_CHARACTERS:
            char_dir = self.output_dir / char_key
            if not char_dir.exists():
                continue

            images = sorted(char_dir.glob("*.jpg"))
            random.shuffle(images)

            n = len(images)
            n_train = int(n * TRAIN_RATIO)
            n_val = int(n * VAL_RATIO)

            splits = {
                "train": images[:n_train],
                "val": images[n_train:n_train + n_val],
                "test": images[n_train + n_val:],
            }

            for split_name, split_images in splits.items():
                split_dir = self.output_dir.parent / split_name / char_key
                split_dir.mkdir(parents=True, exist_ok=True)
                for img_path in split_images:
                    dest = split_dir / img_path.name
                    if not dest.exists():
                        shutil.copy2(str(img_path), str(dest))
                split_stats[split_name] += len(split_images)

        print(f"\n数据集划分完成:")
        print(f"  训练集: {split_stats['train']} 张")
        print(f"  验证集: {split_stats['val']} 张")
        print(f"  测试集: {split_stats['test']} 张")

        meta_path = self.output_dir.parent / "dataset_meta.json"
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump({
                "split": split_stats,
                "characters": list(ANIME_CHARACTERS.keys()),
                "image_size": IMAGE_SIZE,
                "train_ratio": TRAIN_RATIO,
                "val_ratio": VAL_RATIO,
                "test_ratio": TEST_RATIO,
            }, f, ensure_ascii=False, indent=2)

        return split_stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="动漫图像预处理工具")
    parser.add_argument("--character", "-c", type=str, default=None,
                        help="仅处理指定角色（默认处理全部）")
    parser.add_argument("--split", "-s", action="store_true",
                        help="处理完成后进行数据集划分")
    parser.add_argument("--no-subtitle", action="store_true",
                        help="不去除字幕区域")
    parser.add_argument("--no-watermark", action="store_true",
                        help="不去除水印")
    args = parser.parse_args()

    preprocessor = ImagePreprocessor(
        remove_subtitle=not args.no_subtitle,
        remove_watermark=not args.no_watermark,
    )

    if args.character:
        preprocessor.process_character(args.character)
    else:
        preprocessor.process_all()

    if args.split:
        preprocessor.split_dataset()
