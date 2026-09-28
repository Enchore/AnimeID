"""
运行完整预处理 + 数据集划分
"""
import sys
import time
sys.path.insert(0, '.')

from pathlib import Path
import json

# 强制unbuffered输出
import builtins
original_print = builtins.print
def print(*args, **kwargs):
    kwargs.setdefault('flush', True)
    original_print(*args, **kwargs)

from module1_data.preprocessor import ImagePreprocessor
from config import PROCESSED_DIR, ANIME_CHARACTERS, TRAIN_RATIO, VAL_RATIO, IMAGE_SIZE

log_path = Path(__file__).parent / 'preprocess_full.log'

def log(msg):
    print(msg)
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')

log("=" * 60)
log("开始批量图像预处理")
log("=" * 60)

preprocessor = ImagePreprocessor()

# 处理所有角色
total_stats = {"total": 0, "success": 0, "failed": 0}
char_stats = {}

for i, char_key in enumerate(ANIME_CHARACTERS.keys()):
    log(f"\n[{i+1}/{len(ANIME_CHARACTERS)}] 处理: {char_key}")
    stats = preprocessor.process_character(char_key)
    char_stats[char_key] = stats
    for k in total_stats:
        total_stats[k] += stats[k]
    log(f"  -> 成功: {stats['success']}/{stats['total']}")

log(f"\n处理完成：总计 {total_stats['total']} 张")
log(f"  成功: {total_stats['success']} 张")
log(f"  失败: {total_stats['failed']} 张")

# 数据集划分
log("\n" + "=" * 60)
log("开始数据集划分")
log("=" * 60)

split_stats = preprocessor.split_dataset()
log(f"\n数据集划分完成:")
log(f"  训练集: {split_stats['train']} 张")
log(f"  验证集: {split_stats['val']} 张")
log(f"  测试集: {split_stats['test']} 张")

log("\n全部完成！")
