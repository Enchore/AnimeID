"""
module1_data/annotator.py - 数据标注工具
功能：
    - 生成标注元数据文件（JSON格式）
    - 验证标注完整性
    - 输出标注统计报告
"""
import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import RAW_DIR, PROCESSED_DIR, ANIME_CHARACTERS, MIN_IMAGES_PER_CLASS


class DataAnnotator:
    """动漫图像数据标注管理器"""

    def __init__(self, data_dir: str = PROCESSED_DIR):
        self.data_dir = Path(data_dir)
        self.annotations = {}

    def generate_annotations(self, source_dir: Optional[str] = None) -> dict:
        """
        自动生成图像标注（基于目录结构）
        
        目录结构要求：
            data_dir/
            ├── naruto_uzumaki/
            │   ├── img_0001.jpg
            │   └── ...
            └── ...
        
        Returns:
            dict: 完整标注数据
        """
        from typing import Optional
        scan_dir = Path(source_dir) if source_dir else self.data_dir
        
        annotations = {
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
            "total_images": 0,
            "total_characters": 0,
            "characters": {},
            "images": []
        }

        image_id = 0
        for char_key, char_info in ANIME_CHARACTERS.items():
            char_dir = scan_dir / char_key
            if not char_dir.exists():
                continue

            # 收集该角色的所有图像
            image_files = []
            for ext in ('*.jpg', '*.jpeg', '*.png', '*.webp'):
                image_files.extend(char_dir.glob(ext))
            image_files.sort()

            char_annotations = {
                "key": char_key,
                "name": char_info["name"],
                "anime": char_info["anime"],
                "class_id": list(ANIME_CHARACTERS.keys()).index(char_key),
                "image_count": len(image_files),
                "sufficient": len(image_files) >= MIN_IMAGES_PER_CLASS,
            }
            annotations["characters"][char_key] = char_annotations

            # 记录每张图像
            for img_path in image_files:
                stat = img_path.stat()
                annotations["images"].append({
                    "id": image_id,
                    "file_name": str(img_path.relative_to(scan_dir)),
                    "character_key": char_key,
                    "character_name": char_info["name"],
                    "anime": char_info["anime"],
                    "class_id": char_annotations["class_id"],
                    "file_size": stat.st_size,
                })
                image_id += 1

            annotations["total_images"] += len(image_files)

        annotations["total_characters"] = len(annotations["characters"])
        self.annotations = annotations
        return annotations

    def save_annotations(self, output_path: str = None) -> str:
        """保存标注文件"""
        if not self.annotations:
            self.generate_annotations()

        if output_path is None:
            output_path = self.data_dir.parent / "annotations.json"
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.annotations, f, ensure_ascii=False, indent=2)
        
        print(f"标注文件已保存: {output_path}")
        return str(output_path)

    def validate_annotations(self) -> dict:
        """
        验证标注完整性
        
        Returns:
            dict: 验证报告
        """
        if not self.annotations:
            self.generate_annotations()
        
        report = {
            "valid": True,
            "total_characters": self.annotations["total_characters"],
            "total_images": self.annotations["total_images"],
            "insufficient_characters": [],
            "empty_characters": [],
            "missing_characters": [],
        }

        # 检查图像数量是否足够
        for char_key, char_info in ANIME_CHARACTERS.items():
            if char_key not in self.annotations["characters"]:
                report["missing_characters"].append({
                    "key": char_key,
                    "name": char_info["name"],
                })
                report["valid"] = False
                continue

            char_data = self.annotations["characters"][char_key]
            if char_data["image_count"] == 0:
                report["empty_characters"].append(char_key)
                report["valid"] = False
            elif not char_data["sufficient"]:
                report["insufficient_characters"].append({
                    "key": char_key,
                    "name": char_data["name"],
                    "count": char_data["image_count"],
                    "required": MIN_IMAGES_PER_CLASS,
                })

        return report

    def print_report(self):
        """打印标注报告"""
        if not self.annotations:
            self.generate_annotations()

        report = self.validate_annotations()

        print("\n" + "="*70)
        print("数据标注报告")
        print("="*70)
        print(f"标注版本: {self.annotations['version']}")
        print(f"生成时间: {self.annotations['created_at']}")
        print(f"总角色数: {self.annotations['total_characters']}")
        print(f"总图像数: {self.annotations['total_images']}")
        print()

        print(f"{'角色名':<20} {'作品':<15} {'图像数':>8} {'类别ID':>8} {'状态':>8}")
        print("-"*70)

        for char_key, char_data in self.annotations["characters"].items():
            status = "✓达标" if char_data["sufficient"] else f"✗不足"
            print(
                f"{char_data['name']:<20} "
                f"{char_data['anime']:<15} "
                f"{char_data['image_count']:>8} "
                f"{char_data['class_id']:>8} "
                f"{status:>8}"
            )

        print("-"*70)

        if report["missing_characters"]:
            print(f"\n⚠ 缺失角色: {len(report['missing_characters'])} 个")
            for ch in report["missing_characters"]:
                print(f"  - {ch['name']} ({ch['key']})")

        if report["insufficient_characters"]:
            print(f"\n⚠ 图像不足角色: {len(report['insufficient_characters'])} 个")
            for ch in report["insufficient_characters"]:
                print(f"  - {ch['name']}: {ch['count']}/{ch['required']}")

        status_text = "✓ 通过" if report["valid"] else "✗ 未通过"
        print(f"\n验证状态: {status_text}")
        print("="*70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="数据标注工具")
    parser.add_argument("--dir", "-d", type=str, default=None,
                        help="数据目录路径（默认使用配置的processed目录）")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="标注文件输出路径")
    parser.add_argument("--validate", "-v", action="store_true",
                        help="验证现有标注文件")
    args = parser.parse_args()

    annotator = DataAnnotator(data_dir=args.dir or PROCESSED_DIR)
    annotator.generate_annotations()
    annotator.print_report()
    annotator.save_annotations(args.output)
