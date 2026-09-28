"""
i18n_enrich_scheduler.py - i18n 数据补全定时调度器

功能：
- 定期扫描数据库中缺少 i18n 数据的识别记录
- 自动补全已知角色的多语言名称
- 支持定时任务和手动触发
"""
import time
import threading
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

# ===== 调度器配置 =====
DEFAULT_INTERVAL_HOURS = 24         # 默认每24小时运行一次（i18n补全不需要太频繁）
DEFAULT_BATCH_SIZE = 100             # 每批处理记录数
DEFAULT_USE_BANGUMI = True           # 是否启用 Bangumi API 搜索（默认开启，中文数据最全）
DEFAULT_USE_ANILIST = True           # 是否启用 AniList API 搜索（默认开启，英文/日文数据）
DEFAULT_USE_LLM = False              # 是否启用 LLM 翻译（默认关闭，较慢）


class I18nEnrichScheduler:
    """i18n 补全调度器（后台线程）"""

    def __init__(self, app=None, interval_hours: int = DEFAULT_INTERVAL_HOURS,
                 use_bangumi: bool = DEFAULT_USE_BANGUMI,
                 use_anilist: bool = DEFAULT_USE_ANILIST,
                 use_llm: bool = DEFAULT_USE_LLM):
        self.app = app
        self.interval_seconds = interval_hours * 3600
        self.use_bangumi = use_bangumi
        self.use_anilist = use_anilist
        self.use_llm = use_llm
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._running = False

        # 统计
        self.last_run: datetime | None = None
        self.total_enriched: int = 0
        self.last_run_enriched: int = 0
        self.last_run_scanned: int = 0
        self.runs: int = 0

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self):
        """启动后台补全线程"""
        if self._running:
            logger.info("[i18n补全调度] 已在运行中")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._running = True
        logger.info(f"[i18n补全调度] 已启动，周期: {self.interval_seconds // 3600}小时")

    def stop(self):
        """停止后台线程"""
        self._stop_event.set()
        self._running = False
        logger.info("[i18n补全调度] 已停止")

    def _run_loop(self):
        """后台循环"""
        # 首次启动后等待60秒再运行（比归一化调度多等30秒）
        time.sleep(60)

        while not self._stop_event.is_set():
            try:
                self.run_now()
            except Exception as e:
                logger.error(f"[i18n补全调度] 执行异常: {e}", exc_info=True)

            # 等待下一个周期
            self._stop_event.wait(self.interval_seconds)

    def run_now(self) -> dict:
        """
        手动触发一次 i18n 补全扫描

        返回：
            {"scanned": int, "enriched": int, "details": [...]}
        """
        if self.app is None:
            logger.warning("[i18n补全调度] 未绑定 Flask app，无法执行")
            return {"scanned": 0, "enriched": 0, "details": []}

        # 使用 raw SQLAlchemy，绕过 Flask-SQLAlchemy 的 app context 问题
        from module3_web.app import RecognitionRecord

        db_uri = self.app.config.get("SQLALCHEMY_DATABASE_URI") or \
                 self.app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if not db_uri:
            logger.error("[i18n补全调度] 无法获取数据库 URI")
            return {"scanned": 0, "enriched": 0, "details": []}

        engine = create_engine(db_uri)
        DBSession = sessionmaker(bind=engine)
        db_session = DBSession()

        try:
            from .i18n_enricher import enrich_all_missing_i18n
            result = enrich_all_missing_i18n(
                db_session,
                batch_size=DEFAULT_BATCH_SIZE,
                use_bangumi=self.use_bangumi,
                use_anilist=self.use_anilist,
                use_llm=self.use_llm
            )
            db_session.commit()
            return result
        except Exception as e:
            db_session.rollback()
            logger.error(f"[i18n补全调度] 执行异常: {e}", exc_info=True)
            return {"scanned": 0, "enriched": 0, "details": []}
        finally:
            db_session.close()

    def get_status(self) -> dict:
        """获取调度器状态"""
        return {
            "running": self._running,
            "interval_hours": self.interval_seconds // 3600,
            "use_bangumi": self.use_bangumi,
            "use_anilist": self.use_anilist,
            "use_llm": self.use_llm,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "runs": self.runs,
            "total_enriched": self.total_enriched,
            "last_scan_summary": {
                "scanned": self.last_run_scanned,
                "enriched": self.last_run_enriched,
            } if self.runs > 0 else None,
        }


# ===== 全局单例 =====
_scheduler: I18nEnrichScheduler | None = None


def get_i18n_enrich_scheduler(use_bangumi: bool = DEFAULT_USE_BANGUMI,
                                use_anilist: bool = DEFAULT_USE_ANILIST,
                                use_llm: bool = DEFAULT_USE_LLM) -> I18nEnrichScheduler:
    """获取 i18n 补全调度器单例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = I18nEnrichScheduler(
            use_bangumi=use_bangumi,
            use_anilist=use_anilist,
            use_llm=use_llm
        )
    return _scheduler


def init_i18n_enrich_scheduler(app, interval_hours: int = DEFAULT_INTERVAL_HOURS,
                                use_bangumi: bool = DEFAULT_USE_BANGUMI,
                                use_anilist: bool = DEFAULT_USE_ANILIST,
                                use_llm: bool = DEFAULT_USE_LLM):
    """初始化并启动 i18n 补全调度器（应在 app 启动时调用）"""
    global _scheduler
    _scheduler = I18nEnrichScheduler(
        app=app,
        interval_hours=interval_hours,
        use_bangumi=use_bangumi,
        use_anilist=use_anilist,
        use_llm=use_llm
    )
    _scheduler.start()
    return _scheduler
