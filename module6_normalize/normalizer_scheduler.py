"""
normalizer_scheduler.py - 定时归一化调度器

功能：
- 定期扫描数据库中所有识别记录的番剧名称
- 将同义/变体名称自动整合为规范名称
- 支持定时任务和手动触发
"""
import os
import sys
import json
import time
import threading
import logging
from pathlib import Path
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent))

from .anime_normalizer import normalize, normalize_record_with_api, get_anilist_cache_stats

logger = logging.getLogger(__name__)

# ===== 调度器配置 =====
DEFAULT_INTERVAL_HOURS = 6         # 默认每6小时运行一次
DEFAULT_BATCH_SIZE = 100           # 每批处理记录数
DEFAULT_USE_API_VERIFY = True      # 是否启用网络验证（AniList API）
DEFAULT_API_BATCH_LIMIT = 20       # 每批最多 API 请求数（避免过慢）


class NormalizerScheduler:
    """归一化调度器（后台线程）"""

    def __init__(self, app=None, interval_hours: int = DEFAULT_INTERVAL_HOURS,
                 use_api_verify: bool = DEFAULT_USE_API_VERIFY):
        self.app = app
        self.interval_seconds = interval_hours * 3600
        self.use_api_verify = use_api_verify
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._running = False

        # 统计
        self.last_run: datetime | None = None
        self.total_normalized: int = 0
        self.last_run_normalized: int = 0
        self.last_run_scanned: int = 0
        self.last_run_api_verified: int = 0   # 网络验证修正的次数
        self.runs: int = 0

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self):
        """启动后台归一化线程"""
        if self._running:
            logger.info("[归一化调度] 已在运行中")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._running = True
        logger.info(f"[归一化调度] 已启动，周期: {self.interval_seconds // 3600}小时")

    def stop(self):
        """停止后台线程"""
        self._stop_event.set()
        self._running = False
        logger.info("[归一化调度] 已停止")

    def _run_loop(self):
        """后台循环"""
        # 首次启动后等待30秒再运行
        time.sleep(30)

        while not self._stop_event.is_set():
            try:
                self.run_now()
            except Exception as e:
                logger.error(f"[归一化调度] 执行异常: {e}", exc_info=True)

            # 等待下一个周期
            self._stop_event.wait(self.interval_seconds)

    def run_now(self) -> dict:
        """
        手动触发一次归一化扫描

        返回：
            {"scanned": int, "normalized": int, "details": [...]}
        """
        if self.app is None:
            logger.warning("[归一化调度] 未绑定 Flask app，无法执行")
            return {"scanned": 0, "normalized": 0, "details": []}

        # 使用 raw SQLAlchemy，绕过 Flask-SQLAlchemy 的 app context 问题
        from module3_web.app import RecognitionRecord

        db_uri = self.app.config.get("SQLALCHEMY_DATABASE_URI") or \
                 self.app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if not db_uri:
            logger.error("[归一化调度] 无法获取数据库 URI")
            return {"scanned": 0, "normalized": 0, "details": []}

        engine = create_engine(db_uri)
        DBSession = sessionmaker(bind=engine)
        db_session = DBSession()

        try:
            result = self._do_normalize(RecognitionRecord, db_session)
            db_session.commit()
            return result
        except Exception as e:
            db_session.rollback()
            logger.error(f"[归一化调度] 执行异常: {e}", exc_info=True)
            return {"scanned": 0, "normalized": 0, "details": []}
        finally:
            db_session.close()

    def _do_normalize(self, RecognitionRecord, db_session) -> dict:
        """执行实际的归一化扫描（使用 raw SQLAlchemy session，无 app context 依赖）"""
        logger.info(
            f"[归一化] 开始扫描数据库... (API验证={'开启' if self.use_api_verify else '关闭'})"
        )
        scanned = 0
        normalized = 0
        api_verified_count = 0   # 被 API 修正的次数
        details = []
        api_call_count = 0         # 本批已用 API 请求数

        try:
            # 分批查询所有有番剧名称的记录
            offset = 0
            while True:
                records = db_session.query(RecognitionRecord) \
                    .filter(RecognitionRecord.top1_anime.isnot(None)) \
                    .filter(RecognitionRecord.top1_anime != "") \
                    .order_by(RecognitionRecord.id) \
                    .offset(offset) \
                    .limit(DEFAULT_BATCH_SIZE) \
                    .all()

                if not records:
                    break

                for record in records:
                    original = record.top1_anime
                    if not original:
                        continue

                    scanned += 1

                    # ==== 选择归一化函数 ====
                    if self.use_api_verify:
                        # 使用 API 验证（网络确认）
                        canonical, was_normalized, source = normalize_record_with_api(original)
                        if source == "api_verified" and was_normalized:
                            api_verified_count += 1
                        api_call_count += 1
                    else:
                        # 仅本地匹配（快速路径）
                        canonical, was_normalized = normalize(original)
                        source = "local"

                    if was_normalized and canonical != original:
                        # 更新记录
                        record.top1_anime = canonical
                        normalized += 1
                        details.append({
                            "record_id": record.id,
                            "original": original,
                            "canonical": canonical,
                            "source": source,
                        })
                        logger.info(
                            f"[归一化] 记录#{record.id}: '{original}' → '{canonical}' ({source})"
                        )

                    # 也检查 top5_results 中的番剧名
                    if record.top5_results:
                        try:
                            top5 = json.loads(record.top5_results)
                            top5_changed = False
                            for item in top5:
                                item_anime = item.get("anime", "")
                                if item_anime:
                                    if self.use_api_verify:
                                        c, ch, s = normalize_record_with_api(item_anime)
                                    else:
                                        c, ch = normalize(item_anime)
                                    if ch and c != item_anime:
                                        item["anime"] = c
                                        top5_changed = True
                                        logger.debug(
                                            f"[归一化] top5 记录#{record.id}: '{item_anime}' → '{c}'"
                                        )
                            if top5_changed:
                                record.top5_results = json.dumps(top5, ensure_ascii=False)
                        except (json.JSONDecodeError, TypeError):
                            pass

                # 提交本批修改
                if normalized > 0 or details:
                    db_session.commit()

                offset += DEFAULT_BATCH_SIZE
                logger.debug(
                    f"[归一化] 已扫描 {scanned} 条，归一化 {normalized} 条，"
                    f"API验证修正 {api_verified_count} 条"
                )

            # 更新统计（使用 Python datetime，不写数据库）
            self.last_run = datetime.now(timezone.utc)
            self.total_normalized += normalized
            self.last_run_normalized = normalized
            self.last_run_scanned = scanned
            self.last_run_api_verified = api_verified_count
            self.runs += 1

            if normalized > 0:
                logger.info(
                    f"[归一化] 扫描完成: {scanned} 条记录, {normalized} 条被归一化, "
                    f"其中 {api_verified_count} 条经网络验证修正"
                )
            else:
                logger.info(f"[归一化] 扫描完成: {scanned} 条记录, 无需归一化")

        except Exception as e:
            db_session.rollback()
            logger.error(f"[归一化] 扫描异常，已回滚: {e}", exc_info=True)

        return {
            "scanned": scanned,
            "normalized": normalized,
            "api_verified": api_verified_count,
            "details": details,
        }

    def get_status(self) -> dict:
        """获取调度器状态"""
        status = {
            "running": self._running,
            "interval_hours": self.interval_seconds // 3600,
            "use_api_verify": self.use_api_verify,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "runs": self.runs,
            "total_normalized": self.total_normalized,
            "last_scan_summary": {
                "scanned": self.last_run_scanned,
                "normalized": self.last_run_normalized,
                "api_verified": self.last_run_api_verified,
            } if self.runs > 0 else None,
        }
        if self.use_api_verify:
            try:
                status["anilist_cache"] = get_anilist_cache_stats()
            except Exception:
                pass
        return status


# ===== 全局单例 =====
_scheduler: NormalizerScheduler | None = None


def get_scheduler(use_api_verify: bool = DEFAULT_USE_API_VERIFY) -> NormalizerScheduler:
    """获取调度器单例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = NormalizerScheduler(use_api_verify=use_api_verify)
    return _scheduler


def init_scheduler(app, interval_hours: int = DEFAULT_INTERVAL_HOURS,
                   use_api_verify: bool = DEFAULT_USE_API_VERIFY):
    """初始化并启动调度器（应在 app 启动时调用）"""
    global _scheduler
    _scheduler = NormalizerScheduler(app=app, interval_hours=interval_hours,
                                    use_api_verify=use_api_verify)
    _scheduler.start()
    return _scheduler
