"""
将 active_classes 写入已有 checkpoint
运行方式：
    python -u update_checkpoint.py
"""
import os
import torch
from pathlib import Path

BASE_DIR = Path(__file__).parent
CKPT_PATH = BASE_DIR / "models" / "mobilenet_19chars" / "best_model.pth"

# 与 trainer.py _build_dataloaders 完全一致的 active_classes 计算逻辑
train_dir = BASE_DIR / "data" / "train"
active_classes = sorted([
    d.name for d in train_dir.iterdir()
    if d.is_dir() and any(d.iterdir())
])
print(f"active_classes ({len(active_classes)}):")
for i, c in enumerate(active_classes):
    print(f"  {i}: {c}")

ckpt = torch.load(str(CKPT_PATH), map_location="cpu")
ckpt["active_classes"] = active_classes

# 同时保存一份到 checkpoint_epoch0XX.pth（最新的那份）
import glob
ckpt_files = sorted(glob.glob(str(CKPT_PATH.parent / "checkpoint_epoch*.pth")))
if ckpt_files:
    latest_ckpt = ckpt_files[-1]
    print(f"\n同时更新: {latest_ckpt}")
    ckpt2 = torch.load(latest_ckpt, map_location="cpu")
    ckpt2["active_classes"] = active_classes
    torch.save(ckpt2, latest_ckpt)
    print(f"  已写入 active_classes")

torch.save(ckpt, str(CKPT_PATH))
print(f"\n已更新: {CKPT_PATH}")
print(f"  active_classes 已写入 checkpoint")
