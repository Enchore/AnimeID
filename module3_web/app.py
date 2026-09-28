"""
module3_web/app.py - Flask Web应用主入口
动漫角色图像识别系统 - 社交化Web平台

功能：
    - 角色识别API（图像上传/URL）
    - 类社交媒体"角色墙"
    - 用户点赞/纠错互动
    - 数据库管理（SQLite）
"""
import os
import sys
import io
import json
import uuid
import logging
import argparse
import threading
from pathlib import Path
from datetime import datetime
from urllib.request import urlopen, Request
from sqlalchemy.ext.hybrid import hybrid_property
from urllib.error import URLError

from functools import wraps
from flask import (
    Flask, request, jsonify, render_template, session,
    redirect, url_for, flash, send_from_directory, g
)
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.utils import secure_filename
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    FLASK_HOST, FLASK_PORT, FLASK_DEBUG, SECRET_KEY, ADMIN_PASSWORD,
    MAX_UPLOAD_SIZE, ALLOWED_EXTENSIONS, DATABASE_URI,
    MODELS_DIR, BASE_DIR, DATA_DIR, LOGS_DIR, NUM_CLASSES,
    SUPPORTED_LOCALES, DEFAULT_LOCALE, get_char_name, get_anime_name,
    ANIME_CHARACTERS, CLASS_NAMES,
)

# 番剧名称归一化
try:
    from module6_normalize.anime_normalizer import normalize as normalize_anime
    from module6_normalize.anime_normalizer import normalize_record_with_api
    _NORMALIZER_AVAILABLE = True
    _NORMALIZER_API_OK = True
except ImportError:
    _NORMALIZER_AVAILABLE = False
    _NORMALIZER_API_OK = False
    def normalize_anime(name: str):
        return (name, False)
    def normalize_record_with_api(name: str):
        return (name, False, None)

# i18n API 查询辅助模块（Qwen 识别后，用真实 API 查询 i18n 数据）
try:
    from module6_normalize.api_i18n_helper import enrich_results_with_api_i18n
    _API_I18N_HELPER_AVAILABLE = True
except ImportError:
    _API_I18N_HELPER_AVAILABLE = False
    def enrich_results_with_api_i18n(results, all_characters_json=None):
        return results, all_characters_json

# 簡→繁轉換器（管理員頁面本地化 fallback 用）
try:
    import opencc
    _s2t_converter = opencc.OpenCC('s2t')  # 簡體 → 繁體
except Exception:
    _s2t_converter = None

# ==============================
# 应用初始化
# ==============================
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config.update(
    SECRET_KEY=SECRET_KEY,
    SQLALCHEMY_DATABASE_URI=DATABASE_URI,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    MAX_CONTENT_LENGTH=MAX_UPLOAD_SIZE,
    UPLOAD_FOLDER=os.path.join(BASE_DIR, "uploads"),
    TEMPLATES_AUTO_RELOAD=True,
)
CORS(app)
db = SQLAlchemy(app)

# 註冊多語系模板過濾器
try:
    # 以模組方式執行時使用相對引入
    from .locale_utils import (
        register_template_filters,
        localize_recognition_result, localize_recognition_results,
        localize_record_data, _locale_to_i18n_key,
        detect_locale,
    )
except (ImportError, ValueError):
    # 直接執行 python app.py 時使用絕對引入
    from locale_utils import (
        register_template_filters,
        localize_recognition_result, localize_recognition_results,
        localize_record_data, _locale_to_i18n_key,
        detect_locale,
    )
register_template_filters(app)

# 上传目录
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


# 迁移函数在 logger 定义之后统一调用（见下方）


# ===== Jinja2 自定义过滤器 =====
@app.template_filter("from_json_or_none")
def from_json_or_none(value):
    """安全解析 JSON 字符串，失败返回 None"""
    if not value:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


@app.before_request
def handle_language_preference():
    """在每个请求前处理语言偏好（?lang=xx 参数设置为 Cookie 后重定向）"""
    lang = request.args.get("lang")
    if lang and lang in SUPPORTED_LOCALES:
        # 构造不含 lang 参数的 URL
        args = dict(request.args)
        args.pop("lang", None)
        query = "&".join(f"{k}={v}" for k, v in args.items())
        redirect_url = request.path + ("?" + query if query else "")
        resp = redirect(redirect_url)
        resp.set_cookie("animeid_lang", lang, max_age=365*24*60*60, path="/")
        return resp

    # 若無 Cookie，標記需要在回應中寫入默認語系 Cookie（after_request 處理）
    if not request.cookies.get("animeid_lang"):
        g._set_default_lang = True


@app.after_request
def set_default_lang_cookie(response):
    """首次訪問時自動寫入默認語言 Cookie（繁體中文）"""
    if hasattr(g, '_set_default_lang') and g._set_default_lang:
        response.set_cookie(
            "animeid_lang", DEFAULT_LOCALE,
            max_age=365*24*60*60, path="/"
        )
    return response


# ===== 数据库迁移 =====
def _migrate_db():
    """为现有数据库添加新列（安全迁移，recognition_records + pending_reviews）"""
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)

    # ---- recognition_records 迁移 ----
    existing_cols = {col["name"] for col in inspector.get_columns("recognition_records")}

    migrations = []
    if "all_characters" not in existing_cols:
        migrations.append("ALTER TABLE recognition_records ADD COLUMN all_characters TEXT")
    if "character_count" not in existing_cols:
        migrations.append("ALTER TABLE recognition_records ADD COLUMN character_count INTEGER DEFAULT 1")
    # 點讚二分維度遷移
    if "like_accuracy" not in existing_cols:
        migrations.append("ALTER TABLE recognition_records ADD COLUMN like_accuracy INTEGER DEFAULT 0")
    if "like_character" not in existing_cols:
        migrations.append("ALTER TABLE recognition_records ADD COLUMN like_character INTEGER DEFAULT 0")

    for sql in migrations:
        try:
            db.session.execute(text(sql))
            db.session.commit()
            logger.info(f"[遷移] 執行: {sql}")
        except Exception as e:
            db.session.rollback()
            logger.warning(f"[遷移] 跳過（可能已存在）: {e}")

    # 點讚二分維度：從舊 likes 欄位回填（僅處理有舊數據的記錄，不覆蓋已有值）
    try:
        cols = {col["name"] for col in inspector.get_columns("recognition_records")}
        if "likes" in cols and "like_accuracy" in cols:
            result = db.session.execute(text(
                "UPDATE recognition_records "
                "SET like_accuracy = COALESCE(likes, 0), "
                "    like_character = COALESCE(like_character, 0) "
                "WHERE (like_accuracy IS NULL OR like_accuracy = 0) "
                "AND COALESCE(likes, 0) > 0"
            ))
            db.session.commit()
            logger.info(f"[遷移] 已回填 {result.rowcount} 條 like_accuracy / like_character（從舊 likes 欄位）")
            # 回填完成後刪除舊 likes 欄位，防止重複執行
            if "likes" in {col["name"] for col in inspector.get_columns("recognition_records")}:
                try:
                    db.session.execute(text("ALTER TABLE recognition_records DROP COLUMN likes"))
                    db.session.commit()
                    logger.info("[遷移] 已刪除舊 likes 欄位（避免後續重複遷移）")
                except Exception:
                    db.session.rollback()
    except Exception as e:
        db.session.rollback()
        logger.warning(f"[遷移] 回填失敗（可忽略）: {e}")

    if migrations:
        logger.info(f"[遷移] recognition_records 完成，共 {len(migrations)} 條")

    # ---- pending_reviews 迁移 ----
    # 检查表是否存在（首次启动时可能尚未创建）
    try:
        pr_cols = {col["name"] for col in inspector.get_columns("pending_reviews")}

        pr_migrations = []
        if "edited_name" not in pr_cols:
            pr_migrations.append("ALTER TABLE pending_reviews ADD COLUMN edited_name VARCHAR(100)")
        if "edited_anime" not in pr_cols:
            pr_migrations.append("ALTER TABLE pending_reviews ADD COLUMN edited_anime VARCHAR(100)")
        if "edited_note" not in pr_cols:
            pr_migrations.append("ALTER TABLE pending_reviews ADD COLUMN edited_note TEXT")
        if "same_entity" not in pr_cols:
            pr_migrations.append("ALTER TABLE pending_reviews ADD COLUMN same_entity BOOLEAN DEFAULT 0")

        for sql in pr_migrations:
            try:
                db.session.execute(text(sql))
                db.session.commit()
                logger.info(f"[遷移] pending_reviews 執行: {sql}")
            except Exception as e:
                db.session.rollback()
                logger.warning(f"[遷移] pending_reviews 跳過（可能已存在）: {e}")

        if pr_migrations:
            logger.info(f"[遷移] pending_reviews 完成，共 {len(pr_migrations)} 條")
    except Exception as e:
        # 表不存在時跳過（首次啟動會在 db.create_all() 之後再遷移）
        logger.debug(f"[遷移] pending_reviews 跳過（表可能未建立）: {e}")

# 日志
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, "web.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)


# ==============================
# 数据库模型
# ==============================
class RecognitionRecord(db.Model):
    """识别记录"""
    __tablename__ = "recognition_records"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    image_filename = db.Column(db.String(255), nullable=False)
    image_url = db.Column(db.String(1024), nullable=True)    # 外链URL

    # 识别结果
    is_anime = db.Column(db.Boolean, default=True, nullable=True)  # 是否为动漫图片
    top1_character_key = db.Column(db.String(100), nullable=True)
    top1_character_name = db.Column(db.String(100), nullable=True)
    top1_anime = db.Column(db.String(100), nullable=True)
    top1_confidence = db.Column(db.Float, nullable=True)
    top5_results = db.Column(db.Text, nullable=True)         # JSON字符串

    # 互動數據（兩個點讚維度）
    like_accuracy  = db.Column(db.Integer, default=0)    # 識別正確點讚
    like_character = db.Column(db.Integer, default=0)    # 喜歡角色點讚
    corrections     = db.Column(db.Integer, default=0)
    user_corrected_name = db.Column(db.String(100), nullable=True)  # 用户纠错后的正确名称
    user_corrected_anime = db.Column(db.String(100), nullable=True)  # 用户纠错后的正确作品名
    correction_approved = db.Column(db.Boolean, default=False)      # 纠错是否已被管理员核准
    is_correct = db.Column(db.Boolean, nullable=True)        # 用户反馈是否正确

    # 多人角色识别（JSON数组，支持双人/多人图片）
    all_characters = db.Column(db.Text, nullable=True)  # JSON: [{"name":"...","anime":"...","confidence":95},...]
    character_count = db.Column(db.Integer, default=1)  # 识别出的角色数量

    # 元数据
    client_ip = db.Column(db.String(50), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    recognition_source = db.Column(db.String(50), nullable=True)  # qwen-open / qwen-verified / local-only / mock
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        top5 = json.loads(self.top5_results) if self.top5_results else []
        # 優先使用 DB 欄位，舊紀錄退化到從 top5 解析
        source = self.recognition_source
        if not source and top5:
            source = top5[0].get("source")
        known_to_db = None
        if top5:
            known_to_db = top5[0].get("known_to_db")
        # 多角色数据
        all_chars = json.loads(self.all_characters) if self.all_characters else None
        return {
            "id": self.id,
            "uuid": self.uuid,
            "image_url": self.image_url or f"/uploads/{self.image_filename}",
            "is_anime": self.is_anime,
            "top1": {
                "character_key": self.top1_character_key,
                "name": self.top1_character_name,
                "anime": self.top1_anime,
                "confidence": self.top1_confidence,
            },
            "top5": top5,
            "all_characters": all_chars,
            "character_count": self.character_count or 1,
            "likes": self.likes,                     # 向後兼容
            "like_accuracy":  self.like_accuracy or 0,
            "like_character": self.like_character or 0,
            "corrections": self.corrections,
            "user_corrected_name": self.user_corrected_name,
            "user_corrected_anime": self.user_corrected_anime,
            "source": source,
            "known_to_db": known_to_db,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @hybrid_property
    def likes(self):
        """向後兼容：總點贊數 = 識別正確 + 喜歡角色"""
        return (self.like_accuracy or 0) + (self.like_character or 0)

    @likes.expression
    def likes(cls):
        return cls.like_accuracy + cls.like_character


    @property
    def is_qwen_new(self):
        """是否為 Qwen-VL 發現的新角色（不在已知庫中）"""
        try:
            top5 = json.loads(self.top5_results) if self.top5_results else []
            if top5:
                src = top5[0].get("source", "")
                known = top5[0].get("known_to_db", True)
                return src == "qwen-vl" and known is False
        except (json.JSONDecodeError, TypeError):
            pass
        return False


class UserFeedback(db.Model):
    """用户反馈（纠错/点赞）"""
    __tablename__ = "user_feedbacks"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    record_id = db.Column(db.Integer, db.ForeignKey("recognition_records.id"), nullable=False)
    feedback_type = db.Column(db.String(20), nullable=False)  # like_accuracy / like_character / correction
    character_key = db.Column(db.String(100), nullable=True)   # 多人識別時標識具體角色（null=整張圖全局）
    correct_name = db.Column(db.String(100), nullable=True)   # 纠错时提供的正确名称
    client_ip = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class UserActionLog(db.Model):
    """用户行为日志"""
    __tablename__ = "user_action_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    action_type = db.Column(db.String(50), nullable=False)    # upload / recognize / like / correct / view
    record_id = db.Column(db.Integer, nullable=True)
    character_key = db.Column(db.String(100), nullable=True)
    detail = db.Column(db.Text, nullable=True)                # JSON附加信息
    client_ip = db.Column(db.String(50), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Comment(db.Model):
    """评论模型（支持嵌套回复）"""
    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    record_id = db.Column(db.Integer, db.ForeignKey("recognition_records.id"), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("comments.id"), nullable=True)  # 父评论ID（嵌套回复）
    username = db.Column(db.String(50), default="匿名用户")
    content = db.Column(db.Text, nullable=False)
    likes = db.Column(db.Integer, default=0)
    client_ip = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 自引用关系
    replies = db.relationship("Comment", backref=db.backref("parent", remote_side=[id]), lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "record_id": self.record_id,
            "parent_id": self.parent_id,
            "username": self.username or "匿名用户",
            "content": self.content,
            "likes": self.likes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PendingReview(db.Model):
    """管理員審核隊列 — 用戶對 Qwen 識別結果的糾錯"""
    __tablename__ = "pending_reviews"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    record_id = db.Column(db.Integer, db.ForeignKey("recognition_records.id"), nullable=False)
    correct_name = db.Column(db.String(100), nullable=False)
    correct_anime = db.Column(db.String(100), nullable=True)
    char_key = db.Column(db.String(100), nullable=True)
    original_source = db.Column(db.String(50), nullable=False)  # qwen-open / qwen-verified
    qwen_verified = db.Column(db.Boolean, nullable=True)        # Qwen-VL 验证结果
    qwen_confidence = db.Column(db.Float, nullable=True)
    qwen_name = db.Column(db.String(100), nullable=True)
    qwen_reason = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default="pending")        # pending / approved / rejected / edited
    edited_name = db.Column(db.String(100), nullable=True)      # 管理員編輯後的角色名
    edited_anime = db.Column(db.String(100), nullable=True)     # 管理員編輯後的作品名
    edited_note = db.Column(db.Text, nullable=True)             # 管理員編輯備註
    same_entity = db.Column(db.Boolean, default=False)          # 原始與糾錯指向同一角色（繁簡/譯名不同）
    admin_verified = db.Column(db.Boolean, nullable=True)        # 核准後 Qwen 二次驗證結果
    admin_verify_confidence = db.Column(db.Float, nullable=True)  # 二次驗證置信度
    admin_verify_reason = db.Column(db.Text, nullable=True)       # 二次驗證理由（含「管理員已確認...」）
    training_saved = db.Column(db.Boolean, default=False)         # 是否已保存到訓練集
    reviewed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    record = db.relationship("RecognitionRecord", backref="pending_reviews")

    def to_dict(self):
        return {
            "id": self.id,
            "record_id": self.record_id,
            "correct_name": self.correct_name,
            "correct_anime": self.correct_anime,
            "char_key": self.char_key,
            "original_source": self.original_source,
            "qwen_verified": self.qwen_verified,
            "qwen_confidence": self.qwen_confidence,
            "qwen_name": self.qwen_name,
            "qwen_reason": self.qwen_reason,
            "status": self.status,
            "edited_name": self.edited_name,
            "edited_anime": self.edited_anime,
            "edited_note": self.edited_note,
            "same_entity": self.same_entity,
            "admin_verified": self.admin_verified,
            "admin_verify_confidence": self.admin_verify_confidence,
            "admin_verify_reason": self.admin_verify_reason,
            "training_saved": self.training_saved,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ==============================
# 模型加载（懒加载 + 支持热切换）
# ==============================
_model_cache = None
_aux_cache = None
_active_model_path_cache = None  # 上次加载的模型路径，用于检测切换


def get_model():
    """
    获取主识别模型（懒加载，支持在线学习热切换）
    
    优先从 active_model.json 读取自动训练的模型，
    否则回退到搜索 best_model.pth
    """
    global _model_cache, _active_model_path_cache

    # 检查是否有自动训练模型
    try:
        from module5_autotrain.auto_trainer import get_active_model_path
        active_path = get_active_model_path()
        if active_path and os.path.exists(active_path):
            if _active_model_path_cache != active_path:
                # 模型已更新，重新加载
                try:
                    from module2_model.evaluator import AnimeEvaluator
                    _model_cache = AnimeEvaluator(active_path)
                    _active_model_path_cache = active_path
                    logger.info(f"識別模型已載入（自動訓練）: {active_path}")
                except Exception as e:
                    logger.warning(f"自動訓練模型載入失敗: {e}")
            return _model_cache
    except ImportError:
        pass  # 自动训练模块不存在，走旧逻辑

    if _model_cache is None:
        best_model_path = Path(MODELS_DIR)
        model_files = list(best_model_path.rglob("best_model.pth"))
        
        if model_files:
            try:
                from module2_model.evaluator import AnimeEvaluator
                _model_cache = AnimeEvaluator(str(model_files[0]))
                _active_model_path_cache = str(model_files[0])
                logger.info(f"識別模型已載入: {model_files[0]}")
            except Exception as e:
                logger.warning(f"模型載入失敗: {e}，將使用模擬模式")
        else:
            logger.warning("未找到訓練好的模型，將使用模擬模式")
    
    return _model_cache


def get_aux():
    """获取辅助识别器（懒加载）"""
    global _aux_cache
    if _aux_cache is None:
        try:
            from module2_model.aux_recognizer import get_aux_recognizer
            _aux_cache = get_aux_recognizer()
            if _aux_cache.is_available():
                logger.info("輔助識別器已就緒（danbooru-pretrained）")
            else:
                logger.info("輔助識別器不可用（將僅使用主模型）")
        except Exception as e:
            logger.warning(f"輔助識別器初始化失敗: {e}")
    return _aux_cache


def _merge_aux_results(results: list, image_path: str) -> tuple:
    """将 danbooru 辅助识别结果融合到现有结果中（去重按置信度排序）"""
    try:
        aux = get_aux()
        if aux and aux.is_available():
            aux_results = aux.predict(image_path, top_k=5)
            if aux_results:
                name_map = {r.get("name", ""): i for i, r in enumerate(results)}
                for aux_r in aux_results:
                    aux_name = aux_r["name"]
                    if aux_name in name_map:
                        idx = name_map[aux_name]
                        if aux_r["confidence"] > results[idx]["confidence"]:
                            results[idx] = aux_r
                            results[idx]["rank"] = idx + 1
                    else:
                        aux_r["rank"] = len(results) + 1
                        results.append(aux_r)
                        name_map[aux_name] = len(results) - 1
                results.sort(key=lambda r: r["confidence"], reverse=True)
                for i, r in enumerate(results):
                    r["rank"] = i + 1
                return results, True
    except Exception as e:
        logger.warning(f"輔助識別失敗（忽略）: {e}")
    return results, False


def recognize_with_fallback(image_path: str) -> tuple:
    """
    两层识别策略（Qwen-VL 开放识别 + 本地模型兜底）
    
    Layer 1: Qwen-VL 开放识别（主力，不限已知角色库）
      - 自由识别任意动漫角色
      - 若角色在已知库中 → 同时运行本地模型做交叉验证
      - 若角色不在已知库中 → 直接采用 Qwen 结果
    Layer 2: 本地模型 + aux（Qwen 不可用或返回空时兜底）
    
    返回：
        (results: list, used_aux: bool, is_anime: bool, qwen_used: bool, recognition_source: str)
        
        recognition_source 取值：
          - "qwen-open"      Qwen 开放识别（角色不在已知库）
          - "qwen-verified"  Qwen 识别 + 本地模型验证（角色在已知库）
          - "local-only"     仅本地模型（Qwen 不可用/失败）
          - "mock"           模拟兜底
    """
    is_anime = True
    qwen_used = False
    recognition_source = "local-only"

    # ===== Layer 1: Qwen-VL 开放识别 =====
    try:
        from module2_model.qwen_recognizer import get_qwen_recognizer
        qwen = get_qwen_recognizer()
        if qwen.is_available():
            qwen_used = True
            qwen_results = qwen.recognize(image_path, top_k=5)

            if qwen_results:
                # 检测非动漫
                if qwen_results[0].get("is_anime") is False:
                    logger.info(f"[Qwen-VL] 判定非動漫: {qwen_results[0].get('anime', '')}")
                    return qwen_results, False, False, True, "qwen-open"

                # 检查是否有角色在已知库中
                known_chars = [r for r in qwen_results if r.get("known_to_db")]
                unknown_chars = [r for r in qwen_results if not r.get("known_to_db")]

                logger.info(
                    f"[Qwen-VL] 開放識別: {len(qwen_results)}個候選 "
                    f"(已知{len(known_chars)} + 新{len(unknown_chars)}) | "
                    f"Top1={qwen_results[0]['name']} ({qwen_results[0]['confidence']:.0f}%)"
                )

                # 如果有已知角色，运行本地模型做交叉验证
                if known_chars:
                    model = get_model()
                    if model:
                        try:
                            local_results = model.predict_single(image_path, top_k=5)
                            for r in local_results:
                                r["source"] = "local"
                            # 将本地模型结果合并（用于丰富候选列表）
                            qwen_results = _merge_qwen_local(
                                qwen_results, local_results, known_chars
                            )
                        except Exception as e:
                            logger.warning(f"[本地驗證] 失敗: {e}")

                # 如果 Qwen 只返回了少量候选，用 aux 补充
                if len(qwen_results) < 3:
                    qwen_results, used_aux = _merge_aux_results(qwen_results, image_path)
                    recognition_source = "qwen-verified" if known_chars else "qwen-open"
                    return qwen_results, used_aux, True, True, recognition_source

                recognition_source = "qwen-verified" if known_chars else "qwen-open"
                return qwen_results, False, True, True, recognition_source

            else:
                # Qwen 返回空 — 無法識別，降級到本地模型
                logger.info("[Qwen-VL] 未能識別任何角色，降級到本地模型")
    except Exception as e:
        logger.warning(f"[Qwen-VL] 識別異常，降級到本地模型: {e}")

    # ===== Layer 2: 本地模型 + 辅助识别器 =====
    recognition_source = "local-only"
    model = get_model()

    if model:
        try:
            results = model.predict_single(image_path, top_k=5)
            for r in results:
                r["source"] = "local"
                r["known_to_db"] = True  # 本地模型只能识别已知角色
        except Exception as e:
            logger.warning(f"主模型推理失敗: {e}，切換到模擬模式")
            results = mock_predict(image_path)
            recognition_source = "mock"
    else:
        results = mock_predict(image_path)
        recognition_source = "mock"

    results, used_aux = _merge_aux_results(results, image_path)
    return results, used_aux, True, qwen_used, recognition_source


def _merge_qwen_local(qwen_results: list, local_results: list, known_chars: list) -> list:
    """
    将本地模型结果与 Qwen 结果融合（用于已知角色交叉验证）
    
    策略：
    - Qwen 结果保留为主（Qwen 的开放识别能力更强）
    - 本地模型结果补充到候选列表（去重）
    - 对于同时出现在两边的角色，取较高置信度
    """
    qwen_names = {r.get("name", ""): i for i, r in enumerate(qwen_results)}
    qwen_key_set = {r.get("character_key", "") for r in qwen_results}
    
    # 将本地模型识别的已知角色补充到 Qwen 结果中
    for local_r in local_results:
        local_key = local_r.get("character_key", "")
        local_name = local_r.get("name", "")
        
        if local_key in qwen_key_set:
            # 已存在：保留较高置信度
            continue
        if local_name in qwen_names:
            continue
        
        # 新候选：附加本地模型结果
        local_r["rank"] = len(qwen_results) + 1
        local_r["known_to_db"] = True
        qwen_results.append(local_r)
    
    # 按置信度重排
    qwen_results.sort(key=lambda r: r.get("confidence", 0), reverse=True)
    for i, r in enumerate(qwen_results):
        r["rank"] = i + 1
    
    logger.info(
        f"[交叉驗證] Qwen {len(qwen_names)}個 + 本地 {len(local_results)}個 "
        f"→ 融合後 {len(qwen_results)}個候選"
    )
    return qwen_results


def mock_predict(image_path: str) -> list:
    """
    模拟预测（无模型时的占位响应）
    用于演示和开发测试
    """
    import random
    from config import ANIME_CHARACTERS, CLASS_NAMES

    # 檢測當前語系
    locale = request.cookies.get("animeid_lang", DEFAULT_LOCALE)

    # 随机选取几个角色作为模拟结果
    sample_chars = random.sample(CLASS_NAMES, min(5, len(CLASS_NAMES)))
    confidences = sorted([random.uniform(10, 95) for _ in range(5)], reverse=True)
    # 归一化
    total = sum(confidences)
    confidences = [round(c / total * 100, 2) for c in confidences]

    results = []
    for rank, (char_key, conf) in enumerate(zip(sample_chars, confidences), 1):
        results.append({
            "rank": rank,
            "character_key": char_key,
            "name": get_char_name(char_key, locale),
            "anime": get_anime_name(char_key, locale),
            "confidence": conf,
            "class_id": CLASS_NAMES.index(char_key) if char_key in CLASS_NAMES else 0,
        })
    return results


# ==============================
# 工具函数
# ==============================
def allowed_file(filename: str) -> bool:
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def log_action(action_type: str, record_id=None, character_key=None, detail=None):
    """记录用户行为"""
    try:
        log = UserActionLog(
            action_type=action_type,
            record_id=record_id,
            character_key=character_key,
            detail=json.dumps(detail, ensure_ascii=False) if detail else None,
            client_ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent", "")[:500],
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        logger.error(f"日誌記錄失敗: {e}")


# ==============================
# 路由 - 页面
# ==============================
@app.route("/")
def index():
    """首页：简洁主页，含网站介绍与识别入口（弹窗模式）"""
    log_action("view", detail={"page": "home"})
    return render_template("index.html")


@app.route("/wall")
def character_wall():
    """角色墙页面（支持筛选）+ 3D球体侧边栏"""
    page = request.args.get("page", 1, type=int)
    per_page = 24

    # 获取所有作品列表（去重+归一化+过滤，供筛选下拉/标签使用）
    from sqlalchemy import distinct, or_ as _or
    # 排除非動漫記錄和垃圾值
    exclude_animes = {"", "未知", "非动漫图片", "None", None}
    raw_animes = db.session.query(
        distinct(RecognitionRecord.top1_anime)
    ).filter(
        RecognitionRecord.is_anime.is_(True),       # 只看動漫圖片
        RecognitionRecord.top1_anime.isnot(None),
        RecognitionRecord.top1_anime != ''
    ).order_by(RecognitionRecord.top1_anime).all()

    # 歸一化 + 去重
    seen_normalized = set()
    anime_list = []
    display_map = {}  # 原始名 → 規範顯示名
    for (raw_name,) in raw_animes:
        if raw_name in exclude_animes:
            continue
        if _NORMALIZER_AVAILABLE:
            norm_name, _ = normalize_anime(raw_name)
        else:
            norm_name = raw_name.strip()
        if not norm_name or norm_name in exclude_animes or norm_name in seen_normalized:
            continue
        seen_normalized.add(norm_name)
        anime_list.append(norm_name)
        display_map[raw_name] = norm_name
    anime_list.sort()

    # 獲取記錄（支持篩選參數）
    q = request.args.get("q", "").strip()
    anime = request.args.get("anime", "").strip()
    min_conf = request.args.get("min_conf", 0, type=int)
    sort = request.args.get("sort", "newest")

    query = RecognitionRecord.query.filter(
        RecognitionRecord.is_anime.is_(True)
    )

    if q:
        like = f"%{q}%"
        query = query.filter(
            _or(
                RecognitionRecord.top1_character_name.like(like),
                RecognitionRecord.top1_anime.like(like),
                RecognitionRecord.all_characters.like(like),
            )
        )
    if anime:
        # 作品篩選：同時匹配歸一化前後的名稱（兼容舊數據）
        query = query.filter(
            _or(
                RecognitionRecord.top1_anime == anime,
                RecognitionRecord.top1_anime.like(f"%{anime}%"),
            )
        )
    if min_conf > 0:
        query = query.filter(RecognitionRecord.top1_confidence >= min_conf)
    if sort == "confidence":
        query = query.order_by(RecognitionRecord.top1_confidence.desc())
    elif sort == "likes":
        query = query.order_by(RecognitionRecord.like_character.desc())
    else:
        query = query.order_by(RecognitionRecord.created_at.desc())

    records = query.paginate(page=page, per_page=per_page, error_out=False)

    # 側邊欄：最近 50 條識別記錄（含非動漫，按時間倒序）
    sidebar_records = RecognitionRecord.query.order_by(
        RecognitionRecord.created_at.desc()
    ).limit(50).all()

    # 為每條記錄解析 all_characters（角色牆卡片需要）
    # 並從 UserFeedback 動態計算每個角色的點讚計數（取代 JSON 裡的靜態值）
    from sqlalchemy import func
    record_chars = {}
    # 先收集當前頁面所有有 all_characters 的 record_id，批量查詢 UserFeedback
    multi_record_ids = [r.id for r in records.items if r.all_characters]
    fb_lookup = {}
    if multi_record_ids:
        fb_rows = db.session.query(
            UserFeedback.record_id,
            UserFeedback.character_key,
            UserFeedback.feedback_type,
            func.count(UserFeedback.id).label("cnt")
        ).filter(
            UserFeedback.record_id.in_(multi_record_ids),
            UserFeedback.character_key.isnot(None),
            UserFeedback.character_key != ""
        ).group_by(
            UserFeedback.record_id,
            UserFeedback.character_key,
            UserFeedback.feedback_type
        ).all()
        for row in fb_rows:
            key = (row[0], row[1], row[2])  # (record_id, character_key, feedback_type)
            fb_lookup[key] = row[3]

    for r in records.items:
        if r.all_characters:
            try:
                chars = json.loads(r.all_characters)
                # 動態填入點讚計數 + 多語言本地化
                for char in chars:
                    ck = char.get("character_key", "") or char.get("name", "")
                    # 多語言本地化（優先使用 Qwen 返回的 i18n，其次 ANIME_CHARACTERS）
                    _localize_char_for_wall(char, locale=detect_locale())
                    if ck:
                        char["like_accuracy_count"] = fb_lookup.get((r.id, ck, "like_accuracy"), 0)
                        char["like_character_count"] = fb_lookup.get((r.id, ck, "like_character"), 0)
                    else:
                        char.setdefault("like_accuracy_count", 0)
                        char.setdefault("like_character_count", 0)
                record_chars[r.id] = chars
            except (json.JSONDecodeError, TypeError):
                record_chars[r.id] = None
        else:
            # 單角色記錄：建立虛擬 char dict 並本地化，讓模板統一從 record_chars 拿顯示名
            char_key = r.top1_character_key or ""
            # 從 top5_results 提取 i18n 資料（供 _localize_char_for_wall 使用）
            _top5_i18n_name = {}
            _top5_i18n_anime = {}
            if r.top5_results:
                try:
                    _parsed_top5 = json.loads(r.top5_results)
                    if _parsed_top5:
                        _top5_i18n_name = _parsed_top5[0].get("name_i18n", {}) or {}
                        _top5_i18n_anime = _parsed_top5[0].get("anime_i18n", {}) or {}
                except (json.JSONDecodeError, TypeError):
                    pass
            virtual_char = {
                "name": r.top1_character_name or "",
                "character_key": char_key,
                "anime": r.top1_anime or "",
                "confidence": r.top1_confidence or 0,
                "name_i18n": _top5_i18n_name,
                "anime_i18n": _top5_i18n_anime,
            }
            _localize_char_for_wall(virtual_char, locale=detect_locale())
            # 填入點讚計數
            if char_key:
                virtual_char["like_accuracy_count"] = fb_lookup.get((r.id, char_key, "like_accuracy"), 0)
                virtual_char["like_character_count"] = fb_lookup.get((r.id, char_key, "like_character"), 0)
            else:
                virtual_char.setdefault("like_accuracy_count", 0)
                virtual_char.setdefault("like_character_count", 0)
            record_chars[r.id] = [virtual_char]

    log_action("view", detail={"page": "wall", "wall_page": page})
    return render_template("wall.html", records=records, anime_list=anime_list,
                           sidebar_records=sidebar_records, record_chars=record_chars)


def _localize_char_for_wall(char: dict, locale: str = None):
    """為角色牆卡片單個角色進行多語言本地化"""
    from config import ANIME_CHARACTERS
    if locale is None:
        try:
            locale = detect_locale()
        except RuntimeError:
            locale = "zh-TW"

    char_key = char.get("character_key", "")
    char_name = char.get("name", "")
    dbg = os.path.join(BASE_DIR, "logs", "wall_i18n_debug.log")

    # 優先使用 Qwen 返回的 i18n 欄位
    qwen_name_i18n = char.get("name_i18n")
    if qwen_name_i18n and isinstance(qwen_name_i18n, dict) and any(v for v in qwen_name_i18n.values() if v):
        # Qwen 已返回多語譯名 → 使用它
        i18n_name = qwen_name_i18n.get(locale.replace("-", "_").lower(), "")
        if not i18n_name:
            for k in [locale, locale.lower(), "zh_tw" if "tw" in locale.lower() else ("zh_cn" if "cn" in locale.lower() else "")]:
                i18n_name = qwen_name_i18n.get(k, "")
                if i18n_name: break
        if i18n_name:
            char["_display_name"] = i18n_name
        else:
            char["_display_name"] = char_name

        i18n_anime = char.get("anime_i18n") or {}
        anime_val = i18n_anime.get(locale.replace("-", "_").lower(), "") if isinstance(i18n_anime, dict) else ""
        if not anime_val and isinstance(i18n_anime, dict):
            for k in [locale, locale.lower(), "zh_tw" if "tw" in locale.lower() else ("zh_cn" if "cn" in locale.lower() else "")]:
                anime_val = i18n_anime.get(k, "")
                if anime_val: break
        char["_display_anime"] = anime_val or char.get("anime", "")
        with open(dbg, "a", encoding="utf-8") as f:
            f.write(f"[QWEN-I18N] {char_name} → {char['_display_name']} ({locale})\n")
        return

    # 其次從 ANIME_CHARACTERS 讀取（已知角色）
    if char_key and char_key in ANIME_CHARACTERS:
        from config import get_char_name, get_anime_name
        char["_display_name"] = get_char_name(char_key, locale)
        char["_display_anime"] = get_anime_name(char_key, locale)
        with open(dbg, "a", encoding="utf-8") as f:
            f.write(f"[ANIME-DB] {char_name}(key={char_key}) → {char['_display_name']} ({locale})\n")
        return

    # 後備：通過名稱模糊匹配 ANIME_CHARACTERS
    matched_ck = None
    for ck, info in ANIME_CHARACTERS.items():
        names = info.get("name", {})
        if isinstance(names, dict):
            for lang_name in names.values():
                if lang_name == char_name:
                    matched_ck = ck
                    break
        elif isinstance(names, str) and names == char_name:
            matched_ck = ck
        if matched_ck:
            break

    if matched_ck:
        from config import get_char_name, get_anime_name
        char["_display_name"] = get_char_name(matched_ck, locale)
        char["_display_anime"] = get_anime_name(matched_ck, locale)
        char["character_key"] = matched_ck
        with open(dbg, "a", encoding="utf-8") as f:
            f.write(f"[NAME-MATCH] {char_name} → {char['_display_name']} ({locale}, matched={matched_ck})\n")
        return

    # 兜底：保留原始名稱（繁體環境下嘗試簡→繁轉換）
    char["_display_name"] = char_name
    char["_display_anime"] = char.get("anime", "")
    if locale and "tw" in locale.lower() and _s2t_converter:
        try:
            char["_display_name"] = _s2t_converter.convert(char["_display_name"])
            char["_display_anime"] = _s2t_converter.convert(char["_display_anime"])
        except Exception:
            pass
    with open(dbg, "a", encoding="utf-8") as f:
        f.write(f"[FALLBACK] {char_name} ({locale}) — 無匹配\n")


@app.route("/upload")
def upload_page():
    """上传识别页面"""
    return render_template("upload.html")


@app.route("/record/<int:record_id>")
def record_detail(record_id: int):
    """识别记录详情页（角色名/番剧名根据语言在地化）"""
    record = RecognitionRecord.query.get_or_404(record_id)
    top5 = json.loads(record.top5_results) if record.top5_results else []

    # 如果有用户纠错信息，将其作为修正后的 Top-1 插入 top5 前面
    if record.user_corrected_name:
        corrected_entry = {
            "rank": 0,  # 0 表示用户纠错
            "character_key": "",
            "name": record.user_corrected_name,
            "anime": record.user_corrected_anime or record.top1_anime or "",
            "confidence": 100,
            "source": "user-corrected",
            "reason": "用户纠错",
        }
        # 找到是否已存在 Qwen 验证过的版本（替换而非重复）
        has_verified = any(
            item.get("source") == "qwen-vl" and item.get("name") == record.user_corrected_name
            for item in top5
        )
        if not has_verified:
            top5 = [corrected_entry] + [item for item in top5 if item.get("name") != record.user_corrected_name]

    # ---- 計算每個角色的點讚數並嵌入 all_chars_list（多人識別場景） ----
    all_chars_list = []
    if record.all_characters:
        try:
            all_chars_list = json.loads(record.all_characters)
        except Exception:
            all_chars_list = []

    # ===== 在地化：根據使用者語言轉換名稱 =====
    locale = detect_locale()
    top5, all_chars_list = localize_record_data(record, top5, all_chars_list, locale)

    for char in all_chars_list:
        ck = char.get("character_key", "") or char.get("name", "")
        char["like_accuracy_count"] = UserFeedback.query.filter_by(
            record_id=record_id, feedback_type="like_accuracy", character_key=ck
        ).count()
        char["like_character_count"] = UserFeedback.query.filter_by(
            record_id=record_id, feedback_type="like_character", character_key=ck
        ).count()

    log_action("view", record_id=record_id)
    return render_template("detail.html", record=record, top5=top5, all_chars=all_chars_list, current_locale=locale)


@app.route("/history")
def history():
    """识别记录历史页：展示所有识别记录（含非动漫），时间轴/Feed 风格"""
    page = request.args.get("page", 1, type=int)
    per_page = 20
    
    query = RecognitionRecord.query.order_by(
        RecognitionRecord.created_at.desc()
    )
    
    records = query.paginate(page=page, per_page=per_page, error_out=False)
    
    log_action("view", detail={"page": "history", "page_num": page})
    return render_template("history.html", records=records)


# ==============================
# 路由 - API
# ==============================
@app.route("/api/recognize", methods=["POST"])
def api_recognize():
    """
    角色识别API
    
    支持两种输入方式：
    1. 表单上传文件（multipart/form-data，字段名 image）
    2. JSON传入图像URL（{"image_url": "..."}）
    
    返回：
    {
        "success": true,
        "record_id": 1,
        "top1": {"name": "...", "anime": "...", "confidence": 95.2},
        "top5": [...]
    }
    """
    image_filename = None
    image_url_input = None
    temp_path = None

    try:
        # ===== 方式1：文件上传 =====
        if "image" in request.files:
            file = request.files["image"]
            if file.filename == "":
                return jsonify({"success": False, "error": "未選擇檔案"}), 400
            if not allowed_file(file.filename):
                return jsonify({"success": False, "error": "不支援的檔案類型"}), 400

            # 生成安全文件名
            ext = file.filename.rsplit('.', 1)[1].lower()
            image_filename = f"{uuid.uuid4().hex}.{ext}"
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], image_filename)
            file.save(save_path)
            temp_path = save_path

        # ===== 方式2：URL输入 =====
        elif request.is_json and "image_url" in request.json:
            image_url_input = request.json["image_url"]
            req = Request(image_url_input, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=10) as resp:
                data = resp.read()
            
            img = Image.open(io.BytesIO(data)).convert("RGB")
            image_filename = f"{uuid.uuid4().hex}.jpg"
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], image_filename)
            img.save(save_path, "JPEG", quality=95)
            temp_path = save_path

        else:
            return jsonify({"success": False, "error": "請上傳圖像檔案或提供圖像URL"}), 400

        # ===== 模型推理（含辅助识别 fallback）=====
        results, used_aux, is_anime, qwen_used, recognition_source = recognize_with_fallback(temp_path)
        top1 = results[0] if results else {}

        # ===== 提取多人角色数据 =====
        char_count = 1
        all_characters_json = None
        # 从 Qwen 结果中提取 character_count
        if top1.get("_character_count"):
            char_count = top1["_character_count"]
            # 清理内部字段
            top1.pop("_character_count", None)
        # 如果 characters 列表有多个不同角色（非候选），存储为 all_characters
        if len(results) >= 2:
            # 檢測是否為真正的多人角色（名稱不同）vs 同角色多候選
            # 過濾掉低置信度雜訊（<10% 通常為誤檢測）
            unique_names = set()
            all_chars = []
            CONFIDENCE_THRESHOLD = 10.0
            for r in results:
                name = r.get("name", "")
                conf = r.get("confidence", 0) or 0
                if name and name not in unique_names and name != "非动漫圖片" and conf >= CONFIDENCE_THRESHOLD:
                    unique_names.add(name)
                    all_chars.append({
                        "name": name,
                        "anime": r.get("anime", ""),
                        "confidence": r.get("confidence", 0),
                        "character_key": r.get("character_key", ""),
                        "source": r.get("source", ""),
                        "reason": r.get("reason", ""),
                    })
            if len(all_chars) >= 2:
                char_count = max(char_count, len(all_chars))
                all_characters_json = json.dumps(all_chars, ensure_ascii=False)
                logger.info(f"[多人識別] 檢測到 {len(all_chars)} 個角色: {', '.join(c['name'] for c in all_chars)}")

        # ===== 番剧名称归一化 =====
        raw_anime = top1.get("anime", "")
        if raw_anime:
            normalized_anime, _ = normalize_anime(raw_anime)
            top1["anime"] = normalized_anime
        # 也归一化 top5 中的番剧名
        for r in results:
            if r.get("anime"):
                normalized, _ = normalize_anime(r["anime"])
                r["anime"] = normalized
        
        # ===== i18n 数据 API 查询（Qwen 识别后，用真实 API 查询官方译名）=====
        if _API_I18N_HELPER_AVAILABLE:
            try:
                results, all_characters_json = enrich_results_with_api_i18n(results, all_characters_json)
                logger.info(f"[API-i18n] 已为识别结果补充真实 i18n 数据（非 LLM 翻译）")
            except Exception as e:
                logger.warning(f"[API-i18n] i18n 查询失败，继续使用无 i18n 数据: {e}")
        
        # ===== 保存识别记录 =====
        record = RecognitionRecord(
            is_anime=is_anime,
            image_filename=image_filename,
            image_url=image_url_input,
            top1_character_key=top1.get("character_key"),
            top1_character_name=top1.get("name"),
            top1_anime=top1.get("anime"),
            top1_confidence=top1.get("confidence"),
            top5_results=json.dumps(results, ensure_ascii=False),
            all_characters=all_characters_json,
            character_count=char_count,
            recognition_source=recognition_source,
            client_ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent", "")[:500],
        )
        db.session.add(record)
        db.session.commit()

        # ===== 高置信度结果自动回流到训练集 =====
        auto_saved = False
        if is_anime and results:
            # 多人图片：为每个角色分别保存
            if all_characters_json:
                all_chars = json.loads(all_characters_json)
                for char_info in all_chars[:3]:  # 最多保存3个角色
                    conf = char_info.get("confidence", 0)
                    if recognition_source.startswith("qwen"):
                        if conf > 85:
                            _auto_save_for_training(record, char_info, source="qwen-auto")
                            auto_saved = True
            else:
                conf = top1.get("confidence", 0)
                if recognition_source == "qwen-open" and conf > 85:
                    auto_saved = _auto_save_for_training(record, top1, source="qwen-auto")
                elif recognition_source == "qwen-verified" and conf > 90:
                    auto_saved = _auto_save_for_training(record, top1, source="qwen-auto")

        # 检查是否触发自动训练
        if auto_saved:
            try:
                labels_file = os.path.join(DATA_DIR, "user_labeled", "labels.json")
                if os.path.exists(labels_file):
                    with open(labels_file, "r", encoding="utf-8") as f:
                        labels_data = json.load(f)
                    _check_auto_train_trigger(top1.get("character_key", ""), len(labels_data))
            except Exception:
                pass

        log_action(
            "recognize",
            record_id=record.id,
            character_key=top1.get("character_key"),
            detail={"confidence": top1.get("confidence"), "image_url": image_url_input, "source": recognition_source}
        )

        logger.info(
            f"識別完成: {top1.get('name')} ({top1.get('confidence', 0):.1f}%) | "
            f"來源: {recognition_source} | 訓練回流: {auto_saved} | 記錄ID: {record.id}"
        )

        # ===== 在地化識別結果（根據使用者語言）=====
        locale = detect_locale()
        top1 = localize_recognition_result(top1, locale)
        results = localize_recognition_results(results, locale)

        return jsonify({
            "success": True,
            "record_id": record.id,
            "top1": top1,
            "top5": results,
            "used_aux": used_aux,
            "qwen_used": qwen_used,
            "recognition_source": recognition_source,
            "redirect": url_for("record_detail", record_id=record.id),
        })

    except URLError as e:
        logger.error(f"URL下載失敗: {e}")
        return jsonify({"success": False, "error": f"圖像URL下載失敗: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"識別失敗: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"识别处理失败: {str(e)}"}), 500

@app.errorhandler(Exception)
def handle_exception(e):
    """全局異常處理器 - 防止進程崩潰導致連線重置"""
    logger.error(f"[全局異常] {e}", exc_info=True)
    return jsonify({"success": False, "error": "伺服器內部錯誤，請重試"}), 500


@app.route("/api/like/<int:record_id>", methods=["POST"])
def api_like(record_id: int):
    """點讚接口（支援按角色維度）

    支援兩種模式：
    - 全局模式（char_key 為空）：針對整張圖的點讚（單人識別或舊兼容）
    - 角色模式（char_key 有值）：多人識別中針對特定角色的點讚

    邏輯：
    - 以 UserFeedback 表為唯一真相來源，每次重新 count
    - 同一 IP + 同一角色 → toggle（刪除 or 新增）
    - 已糾錯記錄不允許點讚「識別正確」
    """
    logger.info(f"[DEBUG /api/like] record_id={record_id}, body={request.get_data(as_text=True)}")
    record = RecognitionRecord.query.get_or_404(record_id)

    data = request.get_json(silent=True) or {}
    like_type = data.get("type", "accuracy")
    if like_type not in ("accuracy", "character"):
        like_type = "accuracy"
    char_key = data.get("char_key") or None  # None = 全局模式

    logger.info(f"[DEBUG /api/like] parsed: like_type={like_type}, char_key={char_key}")

    # 已糾錯的記錄不允許點讚「識別正確」（僅限全局模式）
    if like_type == "accuracy" and not char_key and (record.correction_approved or record.user_corrected_name):
        return jsonify({"success": False, "error": "此識別結果已被糾錯，無法點讚"}), 400

    # 多人模式：檢查該角色是否已被糾錯
    if like_type == "accuracy" and char_key:
        if record.all_characters:
            try:
                all_chars_json = json.loads(record.all_characters)
                for c in all_chars_json:
                    c_key = c.get("character_key", "") or c.get("name", "")
                    if c_key == char_key and c.get("corrected"):
                        return jsonify({"success": False, "error": f"角色「{c.get('original_name', char_key)}」已被糾錯，無法點讚"}), 400
            except (json.JSONDecodeError, TypeError):
                pass

    feedback_type_str = f"like_{like_type}"
    client_ip = request.remote_addr

    # 查找此 IP 對 此記錄+此類型+此角色 的點讚記錄
    query_filter = {
        "record_id": record_id,
        "feedback_type": feedback_type_str,
        "client_ip": client_ip,
    }
    if char_key:
        query_filter["character_key"] = char_key

    existing_list = UserFeedback.query.filter_by(**query_filter).all()

    if existing_list:
        # 已點讚 → 取消
        for fb in existing_list:
            db.session.delete(fb)
        db.session.commit()
        liked = False
    else:
        # 未點讚 → 新增
        feedback = UserFeedback(
            record_id=record_id,
            feedback_type=feedback_type_str,
            character_key=char_key,
            client_ip=client_ip,
        )
        db.session.add(feedback)
        db.session.commit()
        liked = True

    # ---- 重新計算各層級計數 ----
    # 全局計數（所有角色的合計，不含 char_key 的）
    global_acc_count = UserFeedback.query.filter_by(
        record_id=record_id, feedback_type="like_accuracy", character_key=None
    ).count()
    global_char_count = UserFeedback.query.filter_by(
        record_id=record_id, feedback_type="like_character", character_key=None
    ).count()

    # 該角色的計數（如果提供了 char_key）
    char_acc_count = 0
    char_char_count = 0
    if char_key:
        char_acc_count = UserFeedback.query.filter_by(
            record_id=record_id, feedback_type="like_accuracy", character_key=char_key
        ).count()
        char_char_count = UserFeedback.query.filter_by(
            record_id=record_id, feedback_type="like_character", character_key=char_key
        ).count()

    # 更新 record 全局欄位（向後兼容）
    total_acc = global_acc_count + sum(
        UserFeedback.query.filter_by(record_id=record_id, feedback_type="like_accuracy", character_key=c).count()
        for c in _get_record_char_keys(record)
    )
    total_char = global_char_count + sum(
        UserFeedback.query.filter_by(record_id=record_id, feedback_type="like_character", character_key=c).count()
        for c in _get_record_char_keys(record)
    )
    record.like_accuracy = total_acc
    record.like_character = total_char
    db.session.commit()

    # 訓練回流：全局 accuracy 首次點讚
    training_saved = False
    if liked and like_type == "accuracy" and not char_key and global_acc_count == 1:
        try:
            top1_data = {
                "character_key": record.top1_character_key,
                "name": record.top1_character_name,
                "anime": record.top1_anime or "未知",
                "confidence": record.confidence_score or 95.0,
            }
            training_saved = _auto_save_for_training(record, top1_data, source="user-confirmed-correct")
        except Exception as e:
            logger.warning(f"[訓練回流] 識別正確保存失敗: {e}")

    log_action(f"like_{like_type}", record_id=record_id, character_key=char_key or record.top1_character_key)
    logger.info(f"[DEBUG /api/like] response: liked={liked}, global={json.dumps({'like_accuracy': global_acc_count, 'like_character': global_char_count})}, char={json.dumps({'char_key': char_key, 'like_accuracy': char_acc_count, 'like_character': char_char_count}) if char_key else None}")

    return jsonify({
        "success": True,
        "liked": liked,
        "global": {"like_accuracy": global_acc_count, "like_character": global_char_count},
        "char": {"char_key": char_key, "like_accuracy": char_acc_count, "like_character": char_char_count} if char_key else None,
        "like_accuracy": total_acc,
        "like_character": total_char,
        "training_saved": training_saved,
    })


def _get_record_char_keys(record):
    """從 all_characters JSON 中提取所有 character_key 列表"""
    try:
        if record.all_characters:
            chars = json.loads(record.all_characters)
            return [c.get("character_key", "") for c in chars if c.get("character_key")]
    except Exception:
        pass
    return []


def _apply_correction_to_record(record, correct_name: str, correct_anime: str, char_key: str, source: str = "user-correction") -> bool:
    """
    將糾錯應用到 RecognitionRecord，並保存訓練數據。
    返回 True 如果訓練數據保存成功。
    
    此函數被以下場景共用：
    - 非 Qwen 來源的用戶糾錯（直接應用）
    - Qwen 背景驗證通過後的自動應用
    - 管理員核准後的應用
    """
    # 1. 應用糾錯到記錄
    record.top1_character_name = correct_name
    record.user_corrected_name = correct_name
    record.correction_approved = True
    if correct_anime:
        record.top1_anime = correct_anime
        record.user_corrected_anime = correct_anime
    elif char_key in ANIME_CHARACTERS:
        auto_anime = get_anime_name(char_key, locale='zh-TW')
        if auto_anime and auto_anime != '未知':
            record.top1_anime = auto_anime

    # 2. 更新 top5_results
    try:
        top5 = json.loads(record.top5_results) if record.top5_results else []
    except (json.JSONDecodeError, TypeError):
        top5 = []
    corrected_entry = {
        "rank": 0,
        "character_key": char_key,
        "name": correct_name,
        "anime": correct_anime or record.top1_anime,
        "confidence": 100.0,
        "source": source,
        "known_to_db": char_key in ANIME_CHARACTERS,
        "reason": f"糾錯應用: {correct_name}",
    }
    # 移除舊的 corrected entry（若有）
    top5 = [item for item in top5 if item.get("source") not in ("user-correction", "admin-approved", "admin-verified")]
    top5.insert(0, corrected_entry)
    record.top5_results = json.dumps(top5, ensure_ascii=False)
    record.top1_character_key = char_key

    # 3. 更新 all_characters 中的對應角色（多人識別場景）
    if record.all_characters:
        try:
            all_chars = json.loads(record.all_characters)
            for char in all_chars:
                if char.get("character_key") == char_key or char.get("name") == record.top1_character_name:
                    if not char.get("corrected"):
                        char["original_name"] = char.get("name")
                    char["name"] = correct_name
                    char["corrected"] = True
                    if correct_anime:
                        char["anime"] = correct_anime
                    break
            record.all_characters = json.dumps(all_chars, ensure_ascii=False)
        except Exception as e:
            logger.error(f"應用糾錯後更新 all_characters 失敗: {e}")

    # 4. 保存訓練數據
    corrected_top1 = {
        "character_key": char_key,
        "name": correct_name,
        "anime": correct_anime or record.top1_anime or "未知",
        "confidence": 100.0,
    }
    training_saved = _auto_save_for_training(record, corrected_top1, source=source)

    # 5. 檢查自動訓練觸發
    if training_saved:
        try:
            labels_file = os.path.join(DATA_DIR, "user_labeled", "labels.json")
            if os.path.exists(labels_file):
                with open(labels_file, "r", encoding="utf-8") as f:
                    labels_data = json.load(f)
                _check_auto_train_trigger(char_key, len(labels_data))
        except Exception as e:
            logger.error(f"檢查自動訓練觸發失敗: {e}")

    db.session.commit()
    return training_saved


def _verify_correction_in_background(review_id: int, image_path: str, correct_name: str, correct_anime: str, char_key: str):
    """在背景執行 Qwen 驗證，通過後自動應用糾錯（跳過管理員）"""
    try:
        from module2_model.qwen_recognizer import get_qwen_recognizer
        qwen = get_qwen_recognizer()
        if not qwen.is_available():
            logger.warning(f"[背景驗證] Qwen 不可用: review_id={review_id}")
            return

        logger.info(f"[背景驗證] 開始: review_id={review_id}, 使用者糾錯={correct_name}")
        qwen_result = qwen.verify_correction(image_path, correct_name, correct_anime)

        # 在 app context 中更新 DB
        with app.app_context():
            review = PendingReview.query.get(review_id)
            if not review:
                logger.warning(f"[背景驗證] review 不存在: review_id={review_id}")
                return

            # 記錄 Qwen 驗證結果
            review.qwen_verified = qwen_result.get("verified")
            review.qwen_confidence = qwen_result.get("confidence")
            review.qwen_name = qwen_result.get("qwen_name")
            review.qwen_reason = qwen_result.get("reason")

            verified = qwen_result.get("verified")
            confidence = qwen_result.get("confidence", 0)

            # ★ 核心邏輯：Qwen 確認 → 自動應用，跳過管理員
            if verified is True and confidence >= 70:
                record = review.record
                if record:
                    training_saved = _apply_correction_to_record(
                        record, correct_name, correct_anime or "", char_key, source="user-correction"
                    )
                    review.status = "approved"          # 標記為已核准（自動）
                    review.reviewed_at = datetime.utcnow()
                    review.training_saved = training_saved
                    logger.info(
                        f"[背景驗證] ✅ Qwen 確認正確，已自動應用糾錯: "
                        f"review_id={review_id}, {record.top1_character_name} → {correct_name}"
                    )
                else:
                    logger.warning(f"[背景驗證] record 不存在: record_id={review.record_id}")
            else:
                logger.info(
                    f"[背景驗證] ⏳ Qwen 未確認（verified={verified}, conf={confidence}），"
                    f"留待管理員審核: review_id={review_id}"
                )

            db.session.commit()

    except Exception as e:
        logger.error(f"[背景驗證] 失敗: review_id={review_id}, error={e}", exc_info=True)


def _verify_after_approval(review_id: int, image_path: str, final_name: str, final_anime: str, final_key: str, record_id: int):
    """管理員核准後的背景任務：Qwen 二次驗證 → 確認後存入訓練集"""
    try:
        from module2_model.qwen_recognizer import get_qwen_recognizer
        qwen = get_qwen_recognizer()

        logger.info(f"[核准後驗證] 開始: review_id={review_id}, 核准角色={final_name}")

        # 執行 Qwen 二次驗證
        if qwen.is_available():
            verify_result = qwen.confirm_after_admin_approval(image_path, final_name, final_anime)
            verified = verify_result.get("verified")
            confidence = verify_result.get("confidence")
            reason = verify_result.get("reason")
        else:
            verified = None  # Qwen 不可用，標記為未驗證
            confidence = None
            reason = "Qwen-VL不可用，跳過二次驗證"

        # 在 app context 中更新 DB + 保存訓練數據
        with app.app_context():
            review = PendingReview.query.get(review_id)
            if not review:
                logger.warning(f"[核准後驗證] review 不存在: review_id={review_id}")
                return

            # 記錄二次驗證結果
            review.admin_verified = verified
            review.admin_verify_confidence = confidence
            review.admin_verify_reason = reason

            # 判斷是否保存到訓練集
            should_save = False
            if verified is True and confidence >= 70:
                should_save = True
            elif verified is None:
                # Qwen 不可用時，管理員已核准就信任管理員判斷
                should_save = True
                reason = reason or "管理員已進行確認，Qwen 不可用時默認採信管理員核准"

            if should_save:
                record = RecognitionRecord.query.get(record_id)
                if record:
                    corrected_top1 = {
                        "character_key": final_key,
                        "name": final_name,
                        "anime": final_anime or (record.top1_anime if record else "未知"),
                        "confidence": 100.0,
                    }
                    training_saved = _auto_save_for_training(
                        record, corrected_top1, source="admin-verified"
                    )
                    review.training_saved = training_saved

                    # 檢查自動訓練觸發
                    if training_saved:
                        try:
                            labels_file = os.path.join(DATA_DIR, "user_labeled", "labels.json")
                            if os.path.exists(labels_file):
                                with open(labels_file, "r", encoding="utf-8") as f:
                                    labels_data = json.load(f)
                                _check_auto_train_trigger(final_key, len(labels_data))
                        except Exception as e:
                            logger.error(f"[核准後驗證] 檢查自動訓練觸發失敗: {e}")
            else:
                logger.info(
                    f"[核准後驗證] Qwen 未確認（verified={verified}, conf={confidence}），"
                    f"不保存訓練數據: {final_name}"
                )

            db.session.commit()
            logger.info(
                f"[核准後驗證] 完成: review_id={review_id}, "
                f"admin_verified={verified}, training_saved={review.training_saved}"
            )

    except Exception as e:
        logger.error(f"[核准後驗證] 失敗: review_id={review_id}, error={e}", exc_info=True)
        # 嘗試記錄失敗狀態
        try:
            with app.app_context():
                review = PendingReview.query.get(review_id)
                if review:
                    review.admin_verified = False
                    review.admin_verify_reason = f"二次驗證異常: {str(e)}"
                    db.session.commit()
        except Exception:
            pass


@app.route("/api/correct/<int:record_id>", methods=["POST"])
def api_correct(record_id: int):
    """
    纠错接口（Path C 增强版）
    
    请求体：{"correct_name": "正确的角色名", "correct_anime": "作品名"}
    
    流程：
    1. 保存纠错记录到 DB
    2. 将用户纠错的图片复制到训练集 data/user_labeled/{character_key}/
    3. 记录标注元数据到 data/user_labeled/labels.json
    """
    record = RecognitionRecord.query.get_or_404(record_id)
    data = request.json or {}
    correct_name = data.get("correct_name", "").strip()
    correct_anime = data.get("correct_anime", "").strip()
    original_name = data.get("original_name", "").strip()  # 多人纠错时的原始角色名

    if not correct_name:
        return jsonify({"success": False, "error": "請提供正確的角色名稱"}), 400

    # ===== 新增：保存 Qwen 原始结果到 qwen_raw_results =====
    # 在修改 top5_results 之前，先保存原始结果（只保存一次）
    if not record.qwen_raw_results and record.top5_results:
        # 只有 qwen-based 的结果才需要保存
        original_source = record.recognition_source or ""
        is_qwen_based = original_source in ("qwen-open", "qwen-verified", "qwen-vl")
        if is_qwen_based:
            record.qwen_raw_results = record.top5_results
            logger.info(f"[纠错] 已保存 Qwen 原始结果到 qwen_raw_results (record_id={record_id})")

    # ===== 判断是否多人角色纠错 =====
    is_multi_correction = bool(original_name) and original_name != record.top1_character_name

    # ===== 1. 记录纠错次数和反馈 =====
    record.corrections += 1
    record.is_correct = False

    feedback = UserFeedback(
        record_id=record_id,
        feedback_type="correction",
        correct_name=correct_name,
        client_ip=request.remote_addr,
    )
    db.session.add(feedback)

    # ===== 1.5 多人角色纠错：更新 all_characters 和 top5_results 中的特定条目 =====
    if is_multi_correction:
        try:
            all_chars = json.loads(record.all_characters) if record.all_characters else []
            for char in all_chars:
                if char.get("name") == original_name:
                    # 保留原始識別名稱，供其他用戶參考
                    if not char.get("corrected"):
                        char["original_name"] = original_name
                    char["name"] = correct_name
                    char["corrected"] = True
                    if correct_anime:
                        char["anime"] = correct_anime
                    record.all_characters = json.dumps(all_chars, ensure_ascii=False)
                    break

            top5_results = json.loads(record.top5_results) if record.top5_results else []
            for item in top5_results:
                if item.get("name") == original_name:
                    item["name"] = correct_name
                    if correct_anime:
                        item["anime"] = correct_anime
                    break
            record.top5_results = json.dumps(top5_results, ensure_ascii=False)
        except Exception as e:
            logger.error(f"多人角色糾錯更新失敗: {e}")

        db.session.commit()
        log_action("correct", record_id=record_id, detail={
            "original_name": original_name,
            "corrected": correct_name,
            "multi_char": True,
        })
        return jsonify({
            "success": True,
            "message": f"已将「{original_name}」纠正为「{correct_name}」，感谢反馈！",
            "multi_char": True,
        })

    # ===== 以下是原有逻辑：主角色纠错 =====

    # ===== 1.4 映射中文名 → character_key（必须在 Qwen 验证前计算）=====
    try:
        from config import ANIME_CHARACTERS
        char_key = None
        for ck, info in ANIME_CHARACTERS.items():
            names = info["name"]
            if isinstance(names, dict):
                # 多語系結構：匹配所有語言的名稱
                if correct_name in names.values():
                    char_key = ck
                    break
            elif names == correct_name:
                char_key = ck
                break
        if not char_key:
            import re
            char_key = re.sub(r'[^\w]', '_', correct_name.lower())
    except Exception:
        char_key = correct_name

    # ===== 1.5 準備圖片路徑（供背景驗證使用）=====
    image_path = os.path.join(app.config["UPLOAD_FOLDER"], record.image_filename)
    
    # ===== 2. 判断原始来源：大模型识别的结果需要人工审核 =====
    # 优先读 DB 栏位；旧纪录为 NULL 时从 top5_results[0].source 解析
    original_source = record.recognition_source or ""
    if not original_source and record.top5_results:
        try:
            _top5 = json.loads(record.top5_results)
            if _top5:
                original_source = _top5[0].get("source", "")
        except (json.JSONDecodeError, TypeError):
            pass
    is_qwen_based = original_source in ("qwen-open", "qwen-verified", "qwen-vl")

    if is_qwen_based:
        # 大模型识别的结果被用户纠错 → 提交管理后台审核
        # 先建立 PendingReview（不含 Qwen 結果），Qwen 驗證改為背景任務
        review = PendingReview(
            record_id=record_id,
            correct_name=correct_name,
            correct_anime=correct_anime if correct_anime else None,
            char_key=char_key,
            original_source=original_source,
            # qwen_verified 等欄位先留空，背景任務完成後更新
        )
        db.session.add(review)
        db.session.flush()  # 取得 review.id
        
        # 啟動背景驗證任務（非同步執行，不阻塞回應）
        if os.path.exists(image_path):
            bg_thread = threading.Thread(
                target=_verify_correction_in_background,
                args=(review.id, image_path, correct_name, correct_anime, char_key),
                daemon=True
            )
            bg_thread.start()
            logger.info(f"[糾錯] 已啟動背景 Qwen 驗證: review_id={review.id}")
        else:
            logger.warning(f"[糾錯] 圖片檔案不存在，跳過背景驗證: {image_path}")
        
        # 保存纠错名到 record 元数据（供审核参考），但不更新显示字段
        record.user_corrected_name = correct_name
        if correct_anime:
            record.user_corrected_anime = correct_anime
        
        db.session.commit()
        
        log_action("correct", record_id=record_id, detail={
            "original": record.top1_character_name,
            "corrected": correct_name,
            "original_source": original_source,
            "submitted_for_review": True,
            "review_id": review.id,
        })
        
        return jsonify({
            "success": True,
            "message": "糾錯已提交管理後台審核，感謝您的反饋！",
            "submitted_for_review": True,
            "review_id": review.id,
            # 不再返回 qwen_verified 等欄位（背景任務執行中）
        })

    # ===== 3. 非 Qwen 来源：直接应用纠错（原有逻辑）=====

    # update display fields
    record.user_corrected_name = correct_name
    record.top1_character_name = correct_name
    record.top1_character_key = char_key
    if correct_anime:
        record.top1_anime = correct_anime
        record.user_corrected_anime = correct_anime
    elif char_key in ANIME_CHARACTERS:
        # 自動從角色庫補全番名
        auto_anime = get_anime_name(char_key, locale='zh-TW')
        if auto_anime and auto_anime != '未知':
            record.top1_anime = auto_anime

    db.session.commit()

    # 归一化番剧名称
    if correct_anime:
        correct_anime, _ = normalize_anime(correct_anime)
    elif record.top1_anime:
        correct_anime, _ = normalize_anime(record.top1_anime)

    # 构建纠错后的 top1 信息
    corrected_top1 = {
        "character_key": char_key,
        "name": correct_name,
        "anime": correct_anime or record.top1_anime or "未知",
        "confidence": 100.0,  # 用户纠错视为100%准确
    }

    # ===== 4. 自动回流（用户纠错覆盖 qwen-auto）=====
    training_saved = _auto_save_for_training(record, corrected_top1, source="user-correction")

    # ===== 5. 检查是否触发自动训练 =====
    if training_saved:
        try:
            labels_file = os.path.join(DATA_DIR, "user_labeled", "labels.json")
            if os.path.exists(labels_file):
                with open(labels_file, "r", encoding="utf-8") as f:
                    labels_data = json.load(f)
                _check_auto_train_trigger(char_key, len(labels_data))
        except Exception as e:
            logger.error(f"檢查自動訓練觸發失敗: {e}")

    log_action("correct", record_id=record_id, detail={
        "original": record.top1_character_name,
        "corrected": correct_name,
        "training_saved": training_saved,

    })

    if training_saved:
        msg = "圖片已加入訓練集，感謝您的糾錯！"
    else:
        msg = "感謝您的糾錯！"
    return jsonify({
        "success": True,
        "message": msg,
        "training_saved": training_saved,
    })


# ==============================
# 管理員後臺（人工審核）
# ==============================

def admin_required(f):
    """管理員登入驗證裝飾器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/admin")
def admin_login():
    """管理員登入頁面"""
    if session.get("admin_authenticated"):
        return redirect(url_for("admin_reviews"))
    return render_template("admin_login.html")


@app.route("/admin/login", methods=["POST"])
def admin_login_post():
    """管理員登入"""
    password = request.form.get("password", "")
    # 未設置 ADMIN_PASSWORD 時一律拒絕登入，避免空密碼比對通過。
    if ADMIN_PASSWORD and password == ADMIN_PASSWORD:
        session["admin_authenticated"] = True
        return redirect(url_for("admin_reviews"))
    flash("密碼錯誤", "error")
    return redirect(url_for("admin_login"))


@app.route("/admin/logout")
def admin_logout():
    """管理員登出"""
    session.pop("admin_authenticated", None)
    return redirect(url_for("admin_login"))


@app.route("/admin/reviews")
@admin_required
def admin_reviews():
    """審核隊列頁面"""
    return render_template("admin_reviews.html")


@app.route("/api/admin/reviews")
@admin_required
def api_admin_reviews():
    """獲取審核列表（支援 status 篩選）"""
    status_filter = request.args.get("status", "pending")
    query = PendingReview.query.order_by(PendingReview.created_at.desc())
    if status_filter == "pending":
        # pending 包含 pending 和 edited（管理員已編輯但仍待審核）
        query = query.filter(PendingReview.status.in_(["pending", "edited"]))
    elif status_filter != "all":
        query = query.filter_by(status=status_filter)
    reviews = query.all()

    _req_locale = request.cookies.get("animeid_lang", DEFAULT_LOCALE)
    _i18n_key = _locale_to_i18n_key(_req_locale)

    results = []
    for r in reviews:
        item = r.to_dict()
        # 附加原始記錄資訊
        record = r.record
        orig_name = record.top1_character_name
        orig_anime = record.top1_anime

        # 本地化角色名/作品名 → 繁體中文（三層 fallback）
        if record.top1_character_key and record.top1_character_key in ANIME_CHARACTERS:
            orig_name = get_char_name(record.top1_character_key, _req_locale)
            orig_anime = get_anime_name(record.top1_character_key, _req_locale)
        else:
            _has_i18n = False
            try:
                top5 = json.loads(record.top5_results) if record.top5_results else []
                if top5 and top5[0].get("name_i18n"):
                    i18n_names = top5[0]["name_i18n"]
                    if isinstance(i18n_names, dict) and i18n_names.get(_i18n_key):
                        orig_name = i18n_names[_i18n_key]
                        _has_i18n = True
                if top5 and top5[0].get("anime_i18n"):
                    i18n_anime = top5[0]["anime_i18n"]
                    if isinstance(i18n_anime, dict) and i18n_anime.get(_i18n_key):
                        orig_anime = i18n_anime[_i18n_key]
                        _has_i18n = True
            except (json.JSONDecodeError, TypeError, IndexError):
                pass

            # Layer 3: 沒有任何 i18n → 簡→繁轉換
            if not _has_i18n and _s2t_converter:
                orig_name = _s2t_converter.convert(orig_name)
                orig_anime = _s2t_converter.convert(orig_anime)

        item["record"] = {
            "uuid": record.uuid,
            "image_url": record.image_url or f"/uploads/{record.image_filename}",
            "top1_name": orig_name,
            "top1_anime": orig_anime,
            "top1_confidence": record.top1_confidence,
            "top1_key": record.top1_character_key,
        }
        results.append(item)

    return jsonify({
        "success": True,
        "reviews": results,
        "total": len(results),
        "status_filter": status_filter,
    })


@app.route("/api/admin/reviews/<int:review_id>/approve", methods=["POST"])
@admin_required
def api_admin_approve(review_id: int):
    """核准糾錯 — 應用糾錯到記錄 + 背景執行 Qwen 二次驗證後存訓練"""
    review = PendingReview.query.get_or_404(review_id)
    if review.status not in ("pending", "edited"):
        return jsonify({"success": False, "error": "該審核項目已處理"}), 400

    record = review.record

    # 管理員編輯過的用編輯值，否則用用戶原始糾錯值
    final_name = review.edited_name or review.correct_name
    final_anime = review.edited_anime or review.correct_anime
    # 如果名稱變了，重新解析 character_key；否則沿用原 key
    if final_name != review.correct_name:
        try:
            from module2_model.qwen_recognizer import _resolve_character_key
            final_key = _resolve_character_key(final_name)
        except ImportError:
            final_key = review.char_key
    else:
        final_key = review.char_key

    # 應用糾錯到記錄（使用最終值：管理員編輯值 > 用戶原始糾錯值）
    record.top1_character_name = final_name
    record.user_corrected_name = final_name
    record.correction_approved = True
    if final_anime:
        record.top1_anime = final_anime
        record.user_corrected_anime = final_anime
    elif final_key in ANIME_CHARACTERS:
        auto_anime = get_anime_name(final_key, locale='zh-TW')
        if auto_anime and auto_anime != '未知':
            record.top1_anime = auto_anime

    # 更新 top5_results
    try:
        top5 = json.loads(record.top5_results) if record.top5_results else []
    except (json.JSONDecodeError, TypeError):
        top5 = []
    corrected_entry = {
        "rank": 0,
        "character_key": final_key,
        "name": final_name,
        "anime": final_anime or record.top1_anime,
        "confidence": 100.0,
        "source": "admin-approved",
        "known_to_db": final_key in ANIME_CHARACTERS,
        "reason": f"管理員核准: 用戶糾錯 {final_name}",
    }
    top5.insert(0, corrected_entry)
    record.top5_results = json.dumps(top5, ensure_ascii=False)
    record.top1_character_key = final_key

    # ===== 更新 all_characters 中的對應角色（多人識別場景）=====
    if record.all_characters:
        try:
            all_chars = json.loads(record.all_characters)
            target_key = review.char_key or ""
            for char in all_chars:
                # 優先按 character_key 匹配，其次按名稱匹配
                if (char.get("character_key") == target_key and target_key) or \
                   char.get("name") == review.correct_name:
                    if not char.get("corrected"):
                        char["original_name"] = char.get("name")
                    char["name"] = final_name
                    char["corrected"] = True
                    if final_anime:
                        char["anime"] = final_anime
                    break
            record.all_characters = json.dumps(all_chars, ensure_ascii=False)
        except Exception as e:
            logger.error(f"批准後更新 all_characters 失敗: {e}")

    # ===== 啟動背景任務：Qwen 二次驗證 → 確認後存訓練集 =====
    image_path = os.path.join(app.config["UPLOAD_FOLDER"], record.image_filename)
    thread = threading.Thread(
        target=_verify_after_approval,
        args=(review_id, image_path, final_name, final_anime or "", final_key, record.id),
        daemon=True,
    )
    thread.start()

    # 標記審核結果（訓練數據由背景任務處理）
    review.status = "approved"
    review.reviewed_at = datetime.utcnow()
    db.session.commit()

    log_action("admin_approve", record_id=record.id, detail={
        "review_id": review.id,
        "corrected_to": final_name,
        "original_correction": review.correct_name,
        "admin_edited": bool(review.edited_name),
        "training_pending": True,  # 訓練數據由背景 Qwen 驗證後保存
    })

    logger.info(f"管理員核准糾錯: review#{review.id}, {record.top1_character_name} → {final_name}（二次驗證進行中）")
    return jsonify({
        "success": True,
        "message": f"已核准 {final_name}，正在進行 Qwen 二次驗證...",
        "training_status": "pending_verification",
    })


@app.route("/api/admin/reviews/<int:review_id>/reject", methods=["POST"])
@admin_required
def api_admin_reject(review_id: int):
    """駁回糾錯"""
    review = PendingReview.query.get_or_404(review_id)
    if review.status not in ("pending", "edited"):
        return jsonify({"success": False, "error": "該審核項目已處理"}), 400

    review.status = "rejected"
    review.reviewed_at = datetime.utcnow()
    db.session.commit()

    log_action("admin_reject", record_id=review.record_id, detail={
        "review_id": review.id,
        "rejected_correction": review.correct_name,
    })

    logger.info(f"管理員駁回糾錯: review#{review.id}, {review.correct_name}")
    return jsonify({
        "success": True,
        "message": f"已駁回糾錯: {review.correct_name}",
    })


@app.route("/api/admin/reviews/<int:review_id>/edit", methods=["POST"])
@admin_required
def api_admin_edit(review_id: int):
    """編輯審核項目 — 管理員修改糾錯前後的名稱/作品（處理譯名差異、繁簡統一）"""
    review = PendingReview.query.get_or_404(review_id)
    if review.status not in ("pending", "edited"):
        return jsonify({"success": False, "error": "該審核項目已處理，無法編輯"}), 400

    data = request.get_json(silent=True) or {}

    edited_name = data.get("edited_name", "").strip()
    edited_anime = data.get("edited_anime", "").strip()
    edited_note = data.get("edited_note", "").strip()

    changed = False
    if edited_name and edited_name != review.correct_name:
        # 重新解析 char_key
        try:
            from module2_model.qwen_recognizer import _resolve_character_key
            review.char_key = _resolve_character_key(edited_name)
        except ImportError:
            pass
        review.edited_name = edited_name
        changed = True

    if edited_anime and edited_anime != (review.correct_anime or ""):
        review.edited_anime = edited_anime
        changed = True

    if edited_note:
        review.edited_note = edited_note
        changed = True

    if changed:
        review.status = "edited"  # 標記為已編輯（仍待審核）
        db.session.commit()
        logger.info(
            f"管理員編輯審核: review#{review.id}, "
            f"{review.correct_name} → {review.edited_name or '(未改)'}"
        )
        return jsonify({
            "success": True,
            "message": "已儲存編輯，待審核",
            "review": review.to_dict(),
        })
    else:
        return jsonify({
            "success": False,
            "error": "未檢測到變更",
        }), 400


@app.route("/api/admin/reviews/<int:review_id>/same-entity", methods=["POST"])
@admin_required
def api_admin_same_entity(review_id: int):
    """
    一鍵標記「前後一致」：原始識別結果與用戶糾錯指向同一角色
    僅因繁簡轉換、譯名差異、別名等原因導致名稱不同
    """
    review = PendingReview.query.get_or_404(review_id)
    if review.status not in ("pending", "edited"):
        return jsonify({"success": False, "error": "該審核項目已處理"}), 400

    record = review.record

    # 標記為同一實體
    review.same_entity = True
    # 使用糾錯後的名稱作為規範名稱（用戶提供的通常是更標準/常見的寫法）
    # 但保留原始識別名稱記錄在 reason 中供歸一化系統使用
    final_name = review.edited_name or review.correct_name
    final_anime = review.edited_anime or review.correct_anime
    final_key = review.char_key

    # 應用糾錯名稱到記錄
    record.user_corrected_name = final_name
    if final_anime:
        record.user_corrected_anime = final_anime

    # 更新 top5_results 加入 same_entity 標記
    try:
        top5 = json.loads(record.top5_results) if record.top5_results else []
    except (json.JSONDecodeError, TypeError):
        top5 = []

    # 找到原始 top1 並記錄別名關係
    original_name = record.top1_character_name
    same_entity_entry = {
        "rank": 0,
        "character_key": final_key,
        "name": final_name,
        "anime": final_anime or record.top1_anime,
        "confidence": 100.0,
        "source": "admin-same-entity",
        "known_to_db": final_key in ANIME_CHARACTERS,
        "reason": f"前後一致：原始「{original_name}」與糾錯「{final_name}」為同一角色（繁簡/譯名差異）",
        "same_entity_original": original_name,   # 歸一化系統可用的元數據
    }
    top5.insert(0, same_entity_entry)
    record.top5_results = json.dumps(top5, ensure_ascii=False)
    record.top1_character_key = final_key

    # 如果糾錯名稱與原始名稱不同且是已知角色，用糾錯名稱覆蓋
    if final_name != original_name:
        record.top1_character_name = final_name

    # 保存訓練數據（標記為 same_entity，歸一化系統會視為同一角色的變體）
    corrected_top1 = {
        "character_key": final_key,
        "name": final_name,
        "anime": final_anime or record.top1_anime or "未知",
        "confidence": 100.0,
        "same_entity_original": original_name,
    }
    training_saved = _auto_save_for_training(record, corrected_top1, source="user-correction")

    # 標記審核完成
    review.status = "approved"
    review.reviewed_at = datetime.utcnow()
    review.edited_note = (review.edited_note or "") + " [前後一致]"
    db.session.commit()

    log_action("admin_same_entity", record_id=record.id, detail={
        "review_id": review.id,
        "original": original_name,
        "corrected_to": final_name,
        "same_entity": True,
        "training_saved": training_saved,
    })

    logger.info(
        f"管理員標記前後一致: review#{review.id}, "
        f"「{original_name}」⇔「{final_name}」（同一角色）"
    )
    return jsonify({
        "success": True,
        "message": f"已標記「前後一致」：「{original_name}」⇔「{final_name}」為同一角色",
        "training_saved": training_saved,
    })


# ===== 训练数据自动回流 =====


def _auto_save_for_training(record, top1: dict, source: str = "qwen-auto") -> bool:
    """
    将识别/纠错图片自动保存到 user_labeled/ 训练集

    参数：
        record: RecognitionRecord 数据库记录
        top1: Top-1 识别结果（含 character_key, name, anime, confidence）
        source: 数据来源 "qwen-auto" | "user-correction"

    返回：
        True 如果保存成功，False 如果跳过（去重/失败）
    """
    try:
        from config import DATA_DIR

        char_name = top1.get("name", "")
        char_key = top1.get("character_key", "")
        confidence = top1.get("confidence", 0)

        if not char_key or not char_name:
            logger.debug("[訓練回流] 缺少角色標識，跳過")
            return False

        # 目标目录
        labeled_dir = os.path.join(DATA_DIR, "user_labeled", char_key)
        os.makedirs(labeled_dir, exist_ok=True)

        # 复制图片
        src_path = os.path.join(app.config["UPLOAD_FOLDER"], record.image_filename)
        if not os.path.exists(src_path):
            logger.warning(f"[訓練回流] 源檔案不存在: {src_path}")
            return False

        import shutil
        dst_filename = f"{record.uuid}_{record.image_filename}"
        dst_path = os.path.join(labeled_dir, dst_filename)

        # ===== 去重与覆盖逻辑（source 優先級：user-correction > user-confirmed-correct > qwen-auto）=====
        labels_file = os.path.join(DATA_DIR, "user_labeled", "labels.json")
        labels_data = []
        if os.path.exists(labels_file):
            with open(labels_file, "r", encoding="utf-8") as f:
                labels_data = json.load(f)

        # 查找同一 UUID 的已有记录
        existing_idx = None
        for i, item in enumerate(labels_data):
            if item.get("uuid") == record.uuid:
                existing_idx = i
                break

        # 定義 source 權重：數值越大越權威，高權威不覆蓋低權威的已有記錄
        SOURCE_PRIORITY = {
            "qwen-auto": 1,
            "user-confirmed-correct": 2,
            "user-correction": 3,
            "admin-same-entity": 4,
            "admin-verified": 5,        # 管理員核准 + Qwen 二次驗證通過（最高權威）
        }

        if existing_idx is not None:
            existing_source = labels_data[existing_idx].get("source", "user-correction")
            old_pri = SOURCE_PRIORITY.get(existing_source, 99)
            new_pri = SOURCE_PRIORITY.get(source, 0)

            if new_pri <= old_pri:
                # 新来源不比旧来源权威 → 跳过
                logger.info(
                    f"[訓練回流] {char_name} 已有更高/相同權威記錄 "
                    f"(現有:{existing_source}={old_pri}, 新:{source}={new_pri})，跳過"
                )
                return False

            # 覆蓋舊記錄（新來源更權威）
            labels_data.pop(existing_idx)
            logger.info(f"[訓練回流] 覆蓋已有記錄: {char_name} (舊來源: {existing_source}, 新來源: {source})")

        # 复制文件
        if not os.path.exists(dst_path):
            shutil.copy2(src_path, dst_path)

        # 追加新记录
        labels_data.append({
            "record_id": record.id,
            "uuid": record.uuid,
            "image_file": dst_filename,
            "character_key": char_key,
            "character_name": char_name,
            "anime": top1.get("anime", "") or record.top1_anime or "未知",
            "confidence": round(confidence, 2) if confidence else None,
            "source": source,
            "saved_at": datetime.utcnow().isoformat(),
        })

        with open(labels_file, "w", encoding="utf-8") as f:
            json.dump(labels_data, f, ensure_ascii=False, indent=2)

        logger.info(
            f"[训练回流] {source} | {char_key}/{dst_filename} "
            f"({char_name}, conf={confidence:.0f}%) | 累计 {len(labels_data)} 张"
        )
        return True

    except Exception as e:
        logger.error(f"[訓練回流] 儲存失敗: {e}", exc_info=True)
        return False


# ===== 自动训练触发器 =====
_auto_train_enabled = True
_auto_train_threshold = 20   # 累计 N 张标注后触发训练（含 auto + correction）
_last_train_count = 0


def _check_auto_train_trigger(char_key: str, total_count: int):
    """检查是否需要触发自动训练"""
    global _last_train_count
    if not _auto_train_enabled:
        return

    new_since_last = total_count - _last_train_count
    if total_count >= _auto_train_threshold and new_since_last >= 5:
        logger.info(
            f"[自動訓練] 用戶標註已達 {total_count} 張，觸發背景訓練..."
        )
        try:
            from module5_autotrain.auto_trainer import trigger_training
            trigger_training()
            _last_train_count = total_count
        except Exception as e:
            logger.warning(f"[自動訓練] 觸發失敗: {e}")


@app.route("/api/wall", methods=["GET"])
def api_wall():
    """
    角色墙数据API（JSON格式）
    支持分页 + 筛选
    """
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 12, type=int)
    q = request.args.get("q", "").strip()
    anime = request.args.get("anime", "").strip()
    min_conf = request.args.get("min_conf", 0, type=int)
    sort = request.args.get("sort", "newest")

    query = RecognitionRecord.query.filter(
        RecognitionRecord.is_anime.is_(True)
    )

    # 关键字搜索（角色名 or 作品名 or 多人角色）
    from sqlalchemy import or_
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                RecognitionRecord.top1_character_name.like(like),
                RecognitionRecord.top1_anime.like(like),
                RecognitionRecord.all_characters.like(like),  # 搜索多人角色数据
            )
        )

    # 作品筛选
    if anime:
        query = query.filter(RecognitionRecord.top1_anime == anime)

    # 置信度筛选
    if min_conf > 0:
        query = query.filter(RecognitionRecord.top1_confidence >= min_conf)

    # 排序
    if sort == "confidence":
        query = query.order_by(RecognitionRecord.top1_confidence.desc())
    elif sort == "likes":
        query = query.order_by(RecognitionRecord.like_character.desc())
    else:
        query = query.order_by(RecognitionRecord.created_at.desc())

    records = query.paginate(page=page, per_page=per_page, error_out=False)

    # 構建歸一化的作品列表（與 index() 邏輯一致）
    exclude_animes = {"", "未知", "非动漫图片", "None", None}
    raw_animes = db.session.query(
        distinct(RecognitionRecord.top1_anime)
    ).filter(
        RecognitionRecord.is_anime.is_(True),
        RecognitionRecord.top1_anime.isnot(None),
        RecognitionRecord.top1_anime != ''
    ).all()

    seen_norm = set()
    api_anime_list = []
    for (raw_name,) in raw_animes:
        if raw_name in exclude_animes:
            continue
        norm_name = normalize_anime(raw_name)[0] if _NORMALIZER_AVAILABLE else raw_name.strip()
        if norm_name and norm_name not in exclude_animes and norm_name not in seen_norm:
            seen_norm.add(norm_name)
            api_anime_list.append(norm_name)
    api_anime_list.sort()

    return jsonify({
        "success": True,
        "total": records.total,
        "pages": records.pages,
        "current_page": page,
        "items": [r.to_dict() for r in records.items],
        "anime_list": api_anime_list,
    })


@app.route("/api/comments/<int:record_id>", methods=["GET"])
def api_comments(record_id):
    """获取某条识别记录的所有评论"""
    comments = Comment.query.filter_by(
        record_id=record_id, parent_id=None  # 只获取顶级评论
    ).order_by(Comment.created_at.desc()).all()

    def serialize_comment(c):
        d = c.to_dict()
        d["replies"] = [serialize_comment(r) for r in c.replies.order_by(Comment.created_at.asc()).all()]
        return d

    return jsonify({
        "success": True,
        "count": Comment.query.filter_by(record_id=record_id).count(),
        "comments": [serialize_comment(c) for c in comments],
    })


@app.route("/api/comments", methods=["POST"])
def api_create_comment():
    """新增评论"""
    data = request.get_json()
    if not data or not data.get("content"):
        return jsonify({"success": False, "error": "評論內容不能為空"}), 400

    record_id = data.get("record_id")
    if not record_id:
        return jsonify({"success": False, "error": "缺少 record_id"}), 400

    # 檢查記錄是否存在
    record = RecognitionRecord.query.get(record_id)
    if not record:
        return jsonify({"success": False, "error": "記錄不存在"}), 404

    # 简单防刷：获取客户端IP
    ip = request.remote_addr or "127.0.0.1"

    comment = Comment(
        record_id=record_id,
        parent_id=data.get("parent_id"),
        username=data.get("username", "匿名用户"),
        content=data["content"].strip(),
        client_ip=ip,
    )
    db.session.add(comment)
    db.session.commit()

    return jsonify({"success": True, "comment": comment.to_dict()})


@app.route("/api/comments/<int:comment_id>/like", methods=["POST"])
def api_like_comment(comment_id):
    """点赞评论"""
    comment = Comment.query.get(comment_id)
    if not comment:
        return jsonify({"success": False, "error": "评论不存在"}), 404

    comment.likes = (comment.likes or 0) + 1
    db.session.commit()

    return jsonify({"success": True, "likes": comment.likes})


@app.route("/api/stats", methods=["GET"])
def api_stats():
    """系统统计数据API"""
    total_records = RecognitionRecord.query.count()
    total_likes = db.session.query(db.func.sum(RecognitionRecord.like_character)).scalar() or 0
    total_corrections = db.session.query(db.func.sum(RecognitionRecord.corrections)).scalar() or 0

    # 平均置信度
    avg_conf = db.session.query(
        db.func.avg(RecognitionRecord.top1_confidence)
    ).filter(RecognitionRecord.top1_confidence.isnot(None)).scalar() or 0

    # 熱門角色Top10（按「喜歡角色」點讚數排序）
    # 統計所有 like_character（含全局模式 + 角色模式），正確解析顯示名稱
    all_likes = db.session.query(
        UserFeedback.record_id,
        UserFeedback.character_key,
    ).filter(
        UserFeedback.feedback_type == "like_character"
    ).all()

    def _resolve_api_name(record_id, char_key):
        """解析正確的顯示角色名"""
        rec = RecognitionRecord.query.get(record_id)
        if not rec:
            return char_key or "未知"
        if char_key:
            if rec.all_characters:
                try:
                    chars = json.loads(rec.all_characters)
                    for c in chars:
                        ck = c.get("character_key", "") or c.get("name", "")
                        if ck == char_key:
                            return c.get("name", char_key)
                except (json.JSONDecodeError, TypeError):
                    pass
            return char_key
        return rec.user_corrected_name or rec.top1_character_name or "未知"

    name_counter = {}
    for rid, ck in all_likes:
        dn = _resolve_api_name(rid, ck)
        name_counter[dn] = name_counter.get(dn, 0) + 1

    popular = []
    for display_name, count in sorted(name_counter.items(), key=lambda x: x[1], reverse=True)[:10]:
        anime_str = ""
        name_rec = RecognitionRecord.query.filter(
            _or(
                RecognitionRecord.top1_character_name == display_name,
                RecognitionRecord.user_corrected_name == display_name,
            )
        ).first()
        if name_rec:
            anime_str = name_rec.top1_anime or name_rec.user_corrected_anime or ""
        popular.append({
            "name": display_name,
            "anime": anime_str,
            "count": count,
            "key": display_name,
        })

    # 自动训练状态
    auto_train_status = {}
    try:
        from module5_autotrain.auto_trainer import get_auto_train_status
        auto_train_status = get_auto_train_status()
    except ImportError:
        pass

    return jsonify({
        "total_records": total_records,
        "total_likes": int(total_likes),
        "total_corrections": int(total_corrections),
        "avg_confidence": round(float(avg_conf), 2),
        "popular_characters": popular,
        "auto_train": auto_train_status,
    })


@app.route("/dashboard")
def dashboard():
    """数据看板页面"""
    return render_template("dashboard.html")


@app.route("/community")
def community():
    """社群页面"""
    # 热门评论记录（有评论的记录，按评论数排序）
    from sqlalchemy import func as sqlfunc
    hot_records = db.session.query(
        RecognitionRecord,
        sqlfunc.count(Comment.id).label("comment_count")
    ).outerjoin(
        Comment, Comment.record_id == RecognitionRecord.id
    ).group_by(
        RecognitionRecord.id
    ).order_by(
        sqlfunc.count(Comment.id).desc(),
        RecognitionRecord.like_character.desc()
    ).limit(8).all()

    # 最新上传
    latest_records = RecognitionRecord.query \
        .order_by(RecognitionRecord.created_at.desc()) \
        .limit(8).all()

    # 排行榜（按「喜歡角色」點讚數排序）
    # 統計所有 like_character 記錄（含全局模式 char_key=NULL + 角色模式）
    # 並正確解析顯示名稱（處理 all_characters 中 key 是錯誤識別名的情況）
    from sqlalchemy import or_ as _or2

    # ---- 步驟1：收集所有 like_character 記錄 ----
    all_char_likes = db.session.query(
        UserFeedback.record_id,
        UserFeedback.character_key,
    ).filter(
        UserFeedback.feedback_type == "like_character"
    ).all()

    # ---- 步驟2：解析名稱，統一歸一化 ----
    def _resolve_display_name(record_id, char_key):
        """根據 record_id + character_key 解析正確的顯示角色名"""
        rec = RecognitionRecord.query.get(record_id)
        if not rec:
            return char_key or "未知"

        if char_key:
            # 角色模式：在 all_characters 中查找 key 對應的正確 name
            if rec.all_characters:
                try:
                    chars = json.loads(rec.all_characters)
                    for c in chars:
                        ck = c.get("character_key", "") or c.get("name", "")
                        if ck == char_key:
                            return c.get("name", char_key)  # 返回正確的 name
                except (json.JSONDecodeError, TypeError):
                    pass
            # fallback: 直接用 key 本身
            return char_key
        else:
            # 全局模式：用糾錯後的名字或 top1 名字
            return rec.user_corrected_name or rec.top1_character_name or "未知"

    # 按解析後的名稱分組計數
    name_counter = {}
    for row in all_char_likes:
        rid, ck = row[0], row[1]
        display_name = _resolve_display_name(rid, ck)
        name_counter[display_name] = name_counter.get(display_name, 0) + 1

    # ---- 步驟3：補充作品信息，排序取 Top10 ----
    sorted_names = sorted(name_counter.items(), key=lambda x: x[1], reverse=True)[:10]
    top_liked = []
    seen_anime_cache = {}  # 避免重複查詢同一角色

    for display_name, likes_count in sorted_names:
        anime_str = ""
        if display_name not in seen_anime_cache:
            # 從記錄中找該角色的作品信息
            name_rec = RecognitionRecord.query.filter(
                _or2(
                    RecognitionRecord.top1_character_name == display_name,
                    RecognitionRecord.user_corrected_name == display_name,
                )
            ).first()
            if name_rec:
                anime_str = name_rec.top1_anime or name_rec.user_corrected_anime or ""
            else:
                # 嘗試在 all_characters 中搜索
                all_rec = RecognitionRecord.query.filter(RecognitionRecord.all_characters.like(f"%{display_name}%")).first()
                if all_rec:
                    try:
                        chars = json.loads(all_rec.all_characters)
                        for c in chars:
                            if c.get("name") == display_name and c.get("anime"):
                                anime_str = c["anime"]
                                break
                    except (json.JSONDecodeError, TypeError):
                        pass
            seen_anime_cache[display_name] = anime_str
        else:
            anime_str = seen_anime_cache[display_name]

        top_liked.append((display_name, anime_str, likes_count, 0))

    return render_template("community.html",
                           hot_records=hot_records,
                           latest_records=latest_records,
                           top_liked=top_liked)


@app.route("/api/echarts-data", methods=["GET"])
def api_echarts_data():
    """为ECharts提供完整图表数据"""
    try:
        from module4_analysis.analyzer import BehaviorAnalyzer
        from module4_analysis.visualizer import EChartsDataBuilder
        
        analyzer = BehaviorAnalyzer()
        echarts_data = EChartsDataBuilder.build_all(analyzer)
        return jsonify(echarts_data)
    except Exception as e:
        logger.error(f"ECharts数据生成失败: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/normalize/status", methods=["GET"])
def api_normalize_status():
    """归一化调度器状态（含网络验证状态）"""
    try:
        from module6_normalize.normalizer_scheduler import get_scheduler
        scheduler = get_scheduler()
        status = scheduler.get_status()
        return jsonify({"success": True, **status})
    except ImportError:
        return jsonify({"success": False, "error": "归一化模块未安装"}), 404


@app.route("/api/normalize/trigger", methods=["POST"])
def api_normalize_trigger():
    """手动触发一次番剧名称归一化（支持 API 验证参数）"""
    try:
        from module6_normalize.normalizer_scheduler import get_scheduler
        scheduler = get_scheduler()

        # 支持请求体中指定 use_api_verify
        data = request.get_json(silent=True) or {}
        use_api = data.get("use_api_verify", scheduler.use_api_verify)

        # 临时切换模式（仅本次执行）
        old_mode = scheduler.use_api_verify
        scheduler.use_api_verify = bool(use_api)

        result = scheduler.run_now()

        scheduler.use_api_verify = old_mode  # 恢复原模式

        return jsonify({"success": True, **result})
    except ImportError:
        return jsonify({"success": False, "error": "归一化模块未安装"}), 404


@app.route("/api/normalize/set-api-verify", methods=["POST"])
def api_normalize_set_api_verify():
    """开启/关闭网络验证"""
    try:
        from module6_normalize.normalizer_scheduler import get_scheduler
        scheduler = get_scheduler()
        data = request.get_json(force=True)
        enabled = bool(data.get("enabled", True))
        scheduler.use_api_verify = enabled
        return jsonify({"success": True, "use_api_verify": enabled})
    except ImportError:
        return jsonify({"success": False, "error": "归一化模块未安装"}), 404


@app.route("/api/auto-train/status", methods=["GET"])
def api_auto_train_status():
    """自动训练状态 API"""
    try:
        from module5_autotrain.auto_trainer import get_auto_train_status
        return jsonify({"success": True, **get_auto_train_status()})
    except ImportError:
        return jsonify({"success": False, "error": "自动训练模块未安装"}), 404


@app.route("/api/auto-train/trigger", methods=["POST"])
def api_auto_train_trigger():
    """手动触发自动训练"""
    try:
        from module5_autotrain.auto_trainer import trigger_training, get_auto_train_status
        status_before = get_auto_train_status()
        if status_before.get("is_training"):
            return jsonify({"success": False, "error": "训练已在进行中", "status": status_before})
        
        trigger_training()
        return jsonify({"success": True, "message": "训练已触发", "status": status_before})
    except ImportError:
        return jsonify({"success": False, "error": "自动训练模块未安装"}), 404


@app.route("/uploads/<filename>")
def uploaded_file(filename: str):
    """提供上传文件访问"""
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# ==============================
# 错误处理
# ==============================
@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "接口不存在"}), 404
    return render_template("error.html", code=404, message="页面未找到"), 404


@app.errorhandler(413)
def too_large(e):
    return jsonify({"success": False, "error": f"文件过大，最大支持 {MAX_UPLOAD_SIZE // 1024 // 1024}MB"}), 413


@app.errorhandler(500)
def server_error(e):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "服务器内部错误"}), 500
    return render_template("error.html", code=500, message="服务器错误"), 500


# ==============================
# 主入口
# ==============================
# ==============================
# 管理員記錄管理（識別記錄 CRUD）
# ==============================

@app.route("/admin/records")
@admin_required
def admin_records():
    """管理員記錄管理頁面"""
    return render_template("admin_records.html")


@app.route("/api/admin/records", methods=["GET"])
@admin_required
def api_admin_list_records():
    """列出所有識別記錄（支援搜尋/分頁）"""
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    search = request.args.get("search", "").strip()
    source = request.args.get("source", "").strip()

    query = RecognitionRecord.query

    if search:
        like_pattern = f"%{search}%"
        query = query.filter(
            db.or_(
                RecognitionRecord.top1_character_name.like(like_pattern),
                RecognitionRecord.top1_anime.like(like_pattern),
                RecognitionRecord.uuid.like(like_pattern),
            )
        )

    if source:
        query = query.filter(RecognitionRecord.recognition_source == source)

    query = query.order_by(RecognitionRecord.id.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    # 取得當前語系（預設繁體中文）
    _req_locale = request.cookies.get("animeid_lang", DEFAULT_LOCALE)
    _i18n_key = _locale_to_i18n_key(_req_locale)

    records = []
    for r in pagination.items:
        char_name = r.top1_character_name
        anime_name = r.top1_anime

        # 本地化角色名/作品名 → 繁體中文（三層 fallback）
        if r.top1_character_key and r.top1_character_key in ANIME_CHARACTERS:
            # Layer 1: 已知角色 → 從 ANIME_CHARACTERS 取譯名
            char_name = get_char_name(r.top1_character_key, _req_locale)
            anime_name = get_anime_name(r.top1_character_key, _req_locale)
        else:
            # Layer 2: Qwen 新角色有 i18n → 從 top5_results 取翻譯
            _has_i18n = False
            try:
                top5 = json.loads(r.top5_results) if r.top5_results else []
                if top5 and top5[0].get("name_i18n"):
                    i18n_names = top5[0]["name_i18n"]
                    if isinstance(i18n_names, dict) and i18n_names.get(_i18n_key):
                        char_name = i18n_names[_i18n_key]
                        _has_i18n = True
                if top5 and top5[0].get("anime_i18n"):
                    i18n_anime = top5[0]["anime_i18n"]
                    if isinstance(i18n_anime, dict) and i18n_anime.get(_i18n_key):
                        anime_name = i18n_anime[_i18n_key]
                        _has_i18n = True
            except (json.JSONDecodeError, TypeError, IndexError):
                pass

            # Layer 3: 沒有任何 i18n 資料 → 簡→繁轉換
            if not _has_i18n and _s2t_converter:
                char_name = _s2t_converter.convert(char_name)
                anime_name = _s2t_converter.convert(anime_name)

        records.append({
            "id": r.id,
            "uuid": r.uuid,
            "image_filename": r.image_filename,
            "image_url": r.image_url or f"/uploads/{r.image_filename}",
            "top1_character_name": char_name,
            "top1_anime": anime_name,
            "top1_confidence": r.top1_confidence,
            "recognition_source": r.recognition_source,
            "like_accuracy": r.like_accuracy,
            "like_character": r.like_character,
            "corrections": r.corrections,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return jsonify({
        "success": True,
        "records": records,
        "total": pagination.total,
        "page": page,
        "per_page": per_page,
        "pages": pagination.pages,
    })


@app.route("/api/admin/records/<int:record_id>", methods=["DELETE"])
@admin_required
def api_admin_delete_record(record_id: int):
    """刪除識別記錄（同時刪除圖片檔案）"""
    record = RecognitionRecord.query.get_or_404(record_id)

    # 刪除圖片檔案
    try:
        image_path = os.path.join(app.config["UPLOAD_FOLDER"], record.image_filename)
        if os.path.exists(image_path):
            os.remove(image_path)
            logger.info(f"已刪除圖片檔案: {image_path}")
    except Exception as e:
        logger.warning(f"刪除圖片檔案失敗: {e}")

    # 同時刪除相關的 PendingReview
    try:
        reviews = PendingReview.query.filter_by(record_id=record_id).all()
        for rv in reviews:
            db.session.delete(rv)
    except Exception:
        pass

    db.session.delete(record)
    db.session.commit()

    log_action("admin_delete_record", record_id=record_id)
    logger.info(f"管理員刪除記錄: record_id={record_id}, {record.top1_character_name}")

    return jsonify({"success": True, "message": f"已刪除記錄 #{record_id}"})


@app.route("/api/admin/records/<int:record_id>", methods=["PUT"])
@admin_required
def api_admin_update_record(record_id: int):
    """編輯識別記錄的角色資訊（前台顯示的名稱/作品）"""
    record = RecognitionRecord.query.get_or_404(record_id)
    data = request.get_json(silent=True) or {}

    changed = []
    new_name = data.get("top1_character_name", "").strip()
    new_anime = data.get("top1_anime", "").strip()

    if new_name and new_name != record.top1_character_name:
        old_name = record.top1_character_name
        record.top1_character_name = new_name
        try:
            from module2_model.qwen_recognizer import _resolve_character_key
            record.top1_character_key = _resolve_character_key(new_name)
        except Exception:
            pass
        changed.append(f"name: {old_name} → {new_name}")

    if "top1_anime" in data:
        old_anime = record.top1_anime
        record.top1_anime = new_anime or None
        changed.append(f"anime: {old_anime} → {new_anime}")

    if changed:
        db.session.commit()
        log_action("admin_update_record", record_id=record_id, detail={"changes": changed})
        logger.info(f"管理員更新記錄: record_id={record_id}, {', '.join(changed)}")
        return jsonify({"success": True, "message": "已更新", "changes": changed})

    return jsonify({"success": False, "error": "未偵測到變更"}), 400



# ===== i18n 数据补全 API =====
@app.route("/api/admin/enrich-i18n", methods=["POST"])
@admin_required
def api_admin_enrich_i18n():
    """
    手动触发 i18n 数据补全
    
    请求参数（JSON）：
        use_bangumi (bool): 是否使用 Bangumi API（默认 True）
        use_anilist (bool): 是否使用 AniList API（默认 True）
        use_llm (bool): 是否使用 LLM 翻译（默认 False）
    
    返回：
        {"success": True, "result": {"scanned": int, "enriched": int, "details": [...]}}
    """
    try:
        # 读取请求参数
        params = request.get_json(silent=True) or {}
        use_bangumi = params.get("use_bangumi", True)
        use_anilist = params.get("use_anilist", True)
        use_llm = params.get("use_llm", False)
        
        from module6_normalize.i18n_enricher import enrich_all_missing_i18n
        from module3_web.app import db
        
        result = enrich_all_missing_i18n(
            db.session,
            batch_size=100,
            use_bangumi=use_bangumi,
            use_anilist=use_anilist,
            use_llm=use_llm
        )
        
        return jsonify({"success": True, "result": result})
    except Exception as e:
        logger.error(f"[i18n补全] 手动触发失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/enrich-i18n/status", methods=["GET"])
@admin_required
def api_admin_enrich_i18n_status():
    """获取 i18n 补全调度器状态"""
    try:
        from module6_normalize.i18n_enrich_scheduler import get_i18n_enrich_scheduler
        scheduler = get_i18n_enrich_scheduler()
        return jsonify({"success": True, "status": scheduler.get_status()})
    except Exception as e:
        logger.error(f"[i18n补全] 获取状态失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="动漫角色识别系统Web服务")
    parser.add_argument("--init-db", action="store_true", help="初始化数据库")
    parser.add_argument("--host", default=FLASK_HOST)
    parser.add_argument("--port", type=int, default=FLASK_PORT)
    parser.add_argument("--debug", action="store_true", default=FLASK_DEBUG)
    args = parser.parse_args()

    with app.app_context():
        if args.init_db:
            db.create_all()
            _migrate_db()
            logger.info("数据库初始化完成")
        else:
            db.create_all()  # 自动创建表
            _migrate_db()  # 运行迁移

        # 初始化自动训练模块
        try:
            from module5_autotrain.auto_trainer import init_auto_trainer
            init_auto_trainer()
        except Exception as e:
            logger.warning(f"自动训练模块初始化失败: {e}")

        # 初始化番剧名称归一化调度器
        if _NORMALIZER_AVAILABLE:
            try:
                from module6_normalize.normalizer_scheduler import init_scheduler
                init_scheduler(app, interval_hours=6)
                logger.info("番剧名称归一化调度器已启动（每6小时）")
            except Exception as e:
                logger.warning(f"归一化调度器启动失败: {e}")

        # 初始化 i18n 数据补全调度器
        try:
            from module6_normalize.i18n_enrich_scheduler import init_i18n_enrich_scheduler
            init_i18n_enrich_scheduler(app, interval_hours=24, use_bangumi=False, use_anilist=False, use_llm=True)
            logger.info("i18n 数据补全调度器已启动（每24小时）")
        except Exception as e:
            logger.warning(f"i18n 补全调度器启动失败: {e}")

    print(f"\n{'='*60}")
    print(f"  动漫角色图像识别系统")
    print(f"  访问地址: http://{args.host if args.host != '0.0.0.0' else 'localhost'}:{args.port}")
    print(f"{'='*60}\n")

    # 排除 site-packages 等外部目錄，避免 torch/numpy 等套件變更觸發無意義重啟
    # 注意：Werkzeug 的 exclude_patterns 使用 fnmatch（glob）語法，不是 regex
    # 但 exclude_patterns 在某些 Werkzeug 版本中無效，因此同時設置 use_reloader=False
    _exclude = [
        '**/site-packages/**',
        '**/Python313/Lib/site-packages/**',
    ]
    app.run(
        host=args.host, port=args.port,
        debug=args.debug, use_reloader=False,  # 關閉 reloader 避免 torch 文件變更導致重啟
        exclude_patterns=_exclude,
    )
