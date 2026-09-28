"""
module5_autotrain/auto_trainer.py - 在线学习自动训练控制器

Path C 核心模块：监控用户标注数据，自动触发训练，评估并热切换模型

工作流程：
    用户纠错 → 图片进 user_labeled/ 
    → 累计 ≥50 张 → 触发后台训练 
    → 训练完成 → 评估 vs 当前模型 
    → 新模型更好 → 热切换
"""
import os
import sys
import json
import time
import shutil
import logging
import threading
import subprocess
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import BASE_DIR, DATA_DIR, MODELS_DIR

logger = logging.getLogger(__name__)

# ===== 路径配置 =====
LABELED_DIR = os.path.join(DATA_DIR, "user_labeled")
TRAIN_DIR = os.path.join(DATA_DIR, "train")
VAL_DIR = os.path.join(DATA_DIR, "val")
TEST_DIR = os.path.join(DATA_DIR, "test")
STATE_FILE = os.path.join(LABELED_DIR, "training_state.json")
ACTIVE_MODEL_FILE = os.path.join(MODELS_DIR, "active_model.json")
TRAIN_WORKER_SCRIPT = os.path.join(os.path.dirname(__file__), "train_worker.py")

# ===== 训练策略配置 =====
AUTO_TRAIN_THRESHOLD = 20         # 累计 N 张新标注后触发训练（含 qwen-auto + user-correction）
AUTO_TRAIN_COOLDOWN_MINUTES = 30  # 两次训练最小间隔（分钟）
MIN_ACCURACY_IMPROVEMENT = 0.02   # 至少提升 2% 准确率才切换

# ===== 全局状态 =====
_training_lock = threading.Lock()
_is_training = False
_last_train_time = None


# ==============================
# 状态管理
# ==============================

def _load_state() -> dict:
    """加载训练状态"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "total_labeled": 0,
        "trained_count": 0,
        "model_versions": [],
        "current_version": 0,
    }


def _save_state(state: dict):
    """保存训练状态"""
    os.makedirs(LABELED_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_labeled_count() -> int:
    """获取当前用户标注总数"""
    if not os.path.exists(LABELED_DIR):
        return 0
    count = 0
    for item in os.listdir(LABELED_DIR):
        item_path = os.path.join(LABELED_DIR, item)
        if os.path.isdir(item_path) and item != "__pycache__":
            # 统计目录中的图片文件
            for f in os.listdir(item_path):
                if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                    count += 1
    return count


def get_active_model_path() -> str:
    """获取当前活跃模型的路径"""
    if os.path.exists(ACTIVE_MODEL_FILE):
        with open(ACTIVE_MODEL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("path", "")
    return ""


def get_active_model_info() -> dict:
    """获取当前活跃模型信息"""
    if os.path.exists(ACTIVE_MODEL_FILE):
        with open(ACTIVE_MODEL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"path": "", "version": 0, "accuracy": 0}


# ==============================
# 训练触发
# ==============================

def trigger_training():
    """
    触发自动训练（由纠错 API 调用）
    
    检查条件：
    1. 新标注数量 >= 阈值
    2. 不在冷却期
    3. 没有正在进行的训练
    """
    global _is_training, _last_train_time

    state = _load_state()
    total = get_labeled_count()
    state["total_labeled"] = total
    _save_state(state)

    new_since_last = total - state.get("trained_count", 0)

    # 条件检查
    if new_since_last < AUTO_TRAIN_THRESHOLD:
        logger.info(
            f"[自动训练] 新标注 {new_since_last} 张，"
            f"需 {AUTO_TRAIN_THRESHOLD} 张才触发"
        )
        return

    if _is_training:
        logger.info("[自动训练] 已有训练在进行中，跳过")
        return

    if _last_train_time:
        elapsed = (datetime.utcnow() - _last_train_time).total_seconds() / 60
        if elapsed < AUTO_TRAIN_COOLDOWN_MINUTES:
            logger.info(
                f"[自动训练] 冷却中（{elapsed:.0f}分/{AUTO_TRAIN_COOLDOWN_MINUTES}分），跳过"
            )
            return

    # 启动后台训练
    logger.info(
        f"[自动训练] 满足条件！新标注 {new_since_last} 张，启动后台训练..."
    )
    thread = threading.Thread(target=_run_training_background, daemon=True)
    thread.start()


def _run_training_background():
    """在后台线程中执行训练"""
    global _is_training, _last_train_time

    with _training_lock:
        if _is_training:
            return
        _is_training = True

    try:
        _last_train_time = datetime.utcnow()

        # 复制用户标注数据到训练集
        _merge_labeled_to_training()

        # 确定版本号
        state = _load_state()
        version = len(state.get("model_versions", [])) + 1
        output_dir = os.path.join(MODELS_DIR, f"auto_v{version}")
        os.makedirs(output_dir, exist_ok=True)

        # 运行训练子进程
        logger.info(f"[自动训练] 开始训练 v{version}，输出目录: {output_dir}")
        success = _run_training_subprocess(output_dir, version)

        if success:
            # 评估新模型
            new_model_path = os.path.join(output_dir, "best_model.pth")
            if os.path.exists(new_model_path):
                accuracy = _evaluate_model(new_model_path)
                logger.info(f"[自动训练] v{version} 验证准确率: {accuracy:.2%}")

                # 决定是否切换
                _maybe_swap_model(new_model_path, version, accuracy)

                # 更新状态
                state = _load_state()
                state["trained_count"] = get_labeled_count()
                state["model_versions"].append({
                    "version": version,
                    "path": new_model_path,
                    "accuracy": round(accuracy, 4),
                    "created_at": datetime.utcnow().isoformat(),
                })
                state["current_version"] = version
                _save_state(state)

        logger.info(f"[自动训练] v{version} 完成")

    except Exception as e:
        logger.error(f"[自动训练] 失败: {e}", exc_info=True)
    finally:
        _is_training = False


# ==============================
# 数据合并
# ==============================

def _merge_labeled_to_training():
    """将 user_labeled 目录中的图片合并到训练集"""
    if not os.path.exists(LABELED_DIR):
        return

    state = _load_state()
    already_trained = set()

    # 记录已训练过的文件
    for version_info in state.get("model_versions", []):
        pass  # 简化：总是全量合并

    merged = 0
    for char_dir in os.listdir(LABELED_DIR):
        src_dir = os.path.join(LABELED_DIR, char_dir)
        if not os.path.isdir(src_dir) or char_dir == "__pycache__":
            continue

        dst_dir = os.path.join(TRAIN_DIR, char_dir)
        os.makedirs(dst_dir, exist_ok=True)

        for fname in os.listdir(src_dir):
            if not fname.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                continue
            
            src = os.path.join(src_dir, fname)
            dst = os.path.join(dst_dir, fname)
            if not os.path.exists(dst):
                shutil.copy2(src, dst)
                merged += 1

    if merged > 0:
        logger.info(f"[自动训练] 合并 {merged} 张用户标注图片到训练集")
    return merged


# ==============================
# 训练子进程
# ==============================

def _run_training_subprocess(output_dir: str, version: int) -> bool:
    """在子进程中运行训练脚本"""
    try:
        # 准备训练参数
        cmd = [
            sys.executable,
            TRAIN_WORKER_SCRIPT,
            "--output-dir", output_dir,
            "--epochs", "15",           # 增量训练用较少 epoch
            "--batch-size", "32",
        ]

        logger.info(f"[自动训练] 启动子进程: {' '.join(cmd)}")

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            cwd=BASE_DIR,
        )

        # 流式读取输出（不阻塞）
        for line in proc.stdout:
            logger.info(f"[训练-v{version}] {line.rstrip()}")

        proc.wait(timeout=3600)  # 最多等1小时

        if proc.returncode == 0:
            logger.info(f"[自动训练] v{version} 训练成功")
            return True
        else:
            logger.error(f"[自动训练] v{version} 训练失败，退出码: {proc.returncode}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("[自动训练] 训练超时（1小时）")
        proc.kill()
        return False
    except Exception as e:
        logger.error(f"[自动训练] 子进程异常: {e}")
        return False


# ==============================
# 模型评估与切换
# ==============================

def _evaluate_model(model_path: str) -> float:
    """评估模型在验证集上的准确率"""
    try:
        from module2_model.evaluator import AnimeEvaluator
        evaluator = AnimeEvaluator(model_path)
        results = evaluator.evaluate(
            val_dir=VAL_DIR,
            batch_size=32,
        )
        return results.get("top1_accuracy", 0.0)
    except Exception as e:
        logger.warning(f"[自动训练] 评估失败: {e}")
        return 0.0


def _maybe_swap_model(new_model_path: str, version: int, accuracy: float):
    """如果新模型更好，执行热切换"""
    current_info = get_active_model_info()
    current_accuracy = current_info.get("accuracy", 0.0)
    current_version = current_info.get("version", 0)

    if accuracy > current_accuracy + MIN_ACCURACY_IMPROVEMENT:
        logger.info(
            f"[自动训练] 新模型 v{version} ({accuracy:.2%}) "
            f"优于当前 v{current_version} ({current_accuracy:.2%})，执行热切换！"
        )

        # 更新 active_model.json
        os.makedirs(MODELS_DIR, exist_ok=True)
        with open(ACTIVE_MODEL_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "path": new_model_path,
                "version": version,
                "accuracy": round(accuracy, 4),
                "num_classes": current_info.get("num_classes", 19),
                "updated_at": datetime.utcnow().isoformat(),
            }, f, ensure_ascii=False, indent=2)

        # 通知 app.py 重新加载模型
        _invalidate_model_cache()

        logger.info(f"[自动训练] 模型已切换为 v{version}")
        return True
    else:
        logger.info(
            f"[自动训练] 新模型 v{version} ({accuracy:.2%}) "
            f"未显著优于当前 v{current_version} ({current_accuracy:.2%})，保持当前模型"
        )
        return False


def _invalidate_model_cache():
    """通知 Flask app 清除模型缓存"""
    try:
        # 通过修改全局标记告知 app.py 重新加载
        import module3_web.app as web_app
        web_app._model_cache = None
        web_app._aux_cache = None
        logger.info("[自动训练] 模型缓存已清除，下次请求将加载新模型")
    except Exception as e:
        logger.warning(f"[自动训练] 清除缓存失败: {e}")


# ==============================
# 状态查询 API
# ==============================

def get_auto_train_status() -> dict:
    """获取自动训练状态（供 Web 仪表盘使用）"""
    state = _load_state()
    labeled_count = get_labeled_count()
    
    return {
        "enabled": True,
        "is_training": _is_training,
        "total_labeled": labeled_count,
        "trained_count": state.get("trained_count", 0),
        "new_since_train": labeled_count - state.get("trained_count", 0),
        "threshold": AUTO_TRAIN_THRESHOLD,
        "current_version": state.get("current_version", 0),
        "versions": state.get("model_versions", []),
        "active_model": get_active_model_info(),
        "last_train_time": _last_train_time.isoformat() if _last_train_time else None,
    }


# ==============================
# 启动时初始化
# ==============================

def init_auto_trainer():
    """初始化自动训练模块（Flask 启动时调用）"""
    os.makedirs(LABELED_DIR, exist_ok=True)
    
    state = _load_state()
    labeled_count = get_labeled_count()
    state["total_labeled"] = labeled_count
    _save_state(state)

    active = get_active_model_info()
    if active.get("path"):
        logger.info(
            f"[自动训练] 就绪 | 当前模型: v{active['version']} "
            f"({active['accuracy']:.2%}) | 用户标注: {labeled_count} 张"
        )
    else:
        logger.info(
            f"[自动训练] 就绪 | 无自动训练模型 | 用户标注: {labeled_count} 张"
        )
