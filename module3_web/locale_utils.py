"""
locale_utils.py - 多語系統一解析模組

提供：
- 從 Cookie / Query / Header 檢測使用者語系
- 從多語系 ANIME_CHARACTERS 解析在地化名稱
- Jinja2 模板過濾器註冊
"""
import opencc
from flask import request, g
from config import (
    ANIME_CHARACTERS, SUPPORTED_LOCALES, DEFAULT_LOCALE,
    get_char_name, get_anime_name, get_char_info_flat,
)

# 簡→繁轉換器（模組層級單例，避免每次請求重建）
_CC_S2TW = opencc.OpenCC('s2tw')


def detect_locale() -> str:
    """
    檢測當前請求的語系偏好

    優先級：
    1. Cookie (animeid_lang)  — 使用者主動選擇的語系
    2. URL 參數 (?lang=xx)     — 分享連結攜帶的語系
    3. 默認 zh-TW             — 不再讀取瀏覽器 Accept-Language，
                                 確保所有首次訪客都看到繁體中文
    """
    # 1. Cookie
    cookie_lang = request.cookies.get("animeid_lang")
    if cookie_lang and cookie_lang in SUPPORTED_LOCALES:
        return cookie_lang

    # 2. URL 參數
    query_lang = request.args.get("lang")
    if query_lang and query_lang in SUPPORTED_LOCALES:
        return query_lang

    # 3. 默認繁體中文（不讀取瀏覽器 Accept-Language）
    return DEFAULT_LOCALE


def get_locale() -> str:
    """取得當前請求的語系（快取在 g 中）"""
    if not hasattr(g, "locale"):
        g.locale = detect_locale()
    return g.locale


def localize_name(char_key: str, field: str = "name", locale: str = None) -> str:
    """
    取得在地化名稱

    參數：
        char_key: 角色 key（如 "naruto_uzumaki"）
        field: "name"（角色名）或 "anime"（番劇名）
        locale: 語系代碼，None 則使用當前請求語系

    返回：
        在地化名稱字串，找不到則返回 char_key 本身
    """
    if locale is None:
        try:
            locale = get_locale()
        except RuntimeError:
            # 不在請求上下文中（如背景任務）
            locale = DEFAULT_LOCALE

    if field == "anime":
        return get_anime_name(char_key, locale)
    return get_char_name(char_key, locale)


def register_template_filters(app):
    """
    向 Flask app 註冊 Jinja2 模板過濾器

    用法：
        {{ 'naruto_uzumaki' | local_char }}       → 在地化角色名
        {{ 'naruto_uzumaki' | local_anime }}       → 在地化番劇名
        {{ record.top1_character_key | local_char }} → 從 character_key 解析名稱
    """

    @app.template_filter("local_char")
    def filter_char_name(char_key):
        """Jinja2 過濾器：角色名稱在地化"""
        if not char_key:
            return "未知角色"
        locale = get_locale()
        return get_char_name(char_key, locale)

    @app.template_filter("local_anime")
    def filter_anime_name(char_key):
        """Jinja2 過濾器：番劇名稱在地化"""
        if not char_key:
            return ""
        locale = get_locale()
        return get_anime_name(char_key, locale)

    @app.template_filter("resolve_name")
    def filter_resolve_name(char_key, fallback_name=None):
        """
        智慧名稱解析：已知角色用在地化名稱，未知角色用儲存名稱

        用法：
            {{ record.top1_character_key | resolve_name(record.top1_character_name) }}
        """
        if not char_key:
            return fallback_name or "未知角色"
        locale = get_locale()
        if char_key in ANIME_CHARACTERS:
            return get_char_name(char_key, locale)
        return fallback_name or char_key

    @app.template_filter("resolve_anime")
    def filter_resolve_anime(char_key, fallback_anime=None):
        """
        智慧番劇名稱解析：已知角色用在地化番劇名，未知用儲存名稱

        用法：
            {{ record.top1_character_key | resolve_anime(record.top1_anime) }}
        """
        if not char_key:
            return fallback_anime or ""
        locale = get_locale()
        if char_key in ANIME_CHARACTERS:
            return get_anime_name(char_key, locale)
        return fallback_anime or ""

    @app.context_processor
    def inject_locale():
        """將語系變數注入所有模板"""
        return {
            "current_locale": get_locale(),
            "SUPPORTED_LOCALES": SUPPORTED_LOCALES,
            "DEFAULT_LOCALE": DEFAULT_LOCALE,
        }


# ===== 識別結果在地化 =====

def localize_recognition_result(result: dict, locale: str = None) -> dict:
    """
    將單筆識別結果在地化

    優先級：
    1. Qwen 返回的 name_i18n / anime_i18n（開放識別新角色，已有多語譯名）
    2. ANIME_CHARACTERS 中的多語譯名（已知角色）
    3. 以上皆無：保留原始 name / anime，不附加 i18n 欄位

    參數：
        result: 識別結果字典（含 name, anime, character_key 等）
        locale: 目標語系代碼，None 則自動偵測

    返回：
        新的結果字典（不修改原始字典）
    """
    if locale is None:
        try:
            locale = get_locale()
        except RuntimeError:
            locale = DEFAULT_LOCALE

    # 不修改原始字典，回傳副本
    result = dict(result)
    char_key = result.get("character_key", "")

    # 優先使用 Qwen 返回的多語譯名（開放識別新角色）
    qwen_name_i18n = result.get("name_i18n")
    qwen_anime_i18n = result.get("anime_i18n")

    if qwen_name_i18n and isinstance(qwen_name_i18n, dict) and qwen_name_i18n:
        # 輔助：優先讀標準格式（hyphen key），否則嘗試 Qwen 原始格式（underscore key）
        def _get_i18n_val(d, lang, default=""):
            if not isinstance(d, dict):
                return default
            return d.get(lang) or d.get(_locale_to_i18n_key(lang), default)

        result["name"] = _get_i18n_val(qwen_name_i18n, locale, result.get("name", ""))
        result["anime"] = _get_i18n_val(qwen_anime_i18n, locale, result.get("anime", "")) if qwen_anime_i18n else result.get("anime", "")
        # 保留完整 i18n（轉為標準格式）
        result["name_i18n"] = _normalize_i18n_dict(qwen_name_i18n)
        result["anime_i18n"] = _normalize_i18n_dict(qwen_anime_i18n) if qwen_anime_i18n else {}
    elif char_key and char_key in ANIME_CHARACTERS:
        # 已知角色：從 ANIME_CHARACTERS 讀取譯名
        result["name"] = get_char_name(char_key, locale)
        result["anime"] = get_anime_name(char_key, locale)
        result["name_i18n"] = ANIME_CHARACTERS[char_key]["name"]
        result["anime_i18n"] = ANIME_CHARACTERS[char_key]["anime"]
    # 以上皆無：保留原始 name / anime，不附加 i18n

    return result


def _locale_to_i18n_key(locale: str) -> str:
    """
    將語系代碼轉換為 i18n 字典的 key

    對應 Qwen 返回的 name_i18n 格式：
        zh_tw, zh_cn, ja, ko, en
    """
    mapping = {
        "zh-TW": "zh_tw",
        "zh-CN": "zh_cn",
        "ja": "ja",
        "ko": "ko",
        "en": "en",
        "fr": "en",   # 其他語言使用英文譯名
        "es": "en",
        "vi": "en",
        "th": "en",
    }
    return mapping.get(locale, "en")


def _normalize_i18n_dict(qwen_i18n: dict) -> dict:
    """
    將 i18n 字典轉換為標準格式（9 種語系，hyphen 格式 key）
    同時支援輸入為底線格式（zh_tw）或連字元格式（zh-TW）
    """
    if not qwen_i18n or not isinstance(qwen_i18n, dict):
        return {}

    def _get(d, *keys):
        for k in keys:
            v = d.get(k)
            if v:
                return v
        return ""

    # zh-TW 值強制做簡→繁轉換（安全網：即使 DB 資料是簡體也會正確顯示）
    _zh_tw = _get(qwen_i18n, "zh_tw", "zh-TW")
    if _zh_tw:
        try:
            _zh_tw = _CC_S2TW.convert(_zh_tw)
        except Exception:
            pass

    return {
        "zh-TW": _zh_tw,
        "zh-CN": _get(qwen_i18n, "zh_cn", "zh-CN"),
        "ja":    _get(qwen_i18n, "ja", "ja"),
        "ko":    _get(qwen_i18n, "ko", "ko"),
        "en":    _get(qwen_i18n, "en", "en"),
        "fr":    _get(qwen_i18n, "en", "en"),
        "es":    _get(qwen_i18n, "en", "en"),
        "vi":    _get(qwen_i18n, "en", "en"),
        "th":    _get(qwen_i18n, "en", "en"),
    }


def localize_recognition_results(results: list, locale: str = None) -> list:
    """
    批次在地化識別結果列表

    參數：
        results: 識別結果字典列表
        locale: 目標語系代碼，None 則自動偵測

    返回：
        在地化後的新列表
    """
    if locale is None:
        try:
            locale = get_locale()
        except RuntimeError:
            locale = DEFAULT_LOCALE

    return [localize_recognition_result(r, locale) for r in results]


def localize_record_data(record, top5: list, all_chars: list, locale: str = None) -> tuple:
    """
    將資料庫讀出的識別記錄資料在地化
    （用於 record_detail 等需要從 DB 讀取後顯示的場景）

    參數：
        record:   RecognitionRecord ORM 物件
        top5:    從 record.top5_results JSON 解析出的列表
        all_chars: 從 record.all_characters JSON 解析出的列表
        locale:   目標語系，None 則自動偵測

    返回：
        (top5_localized, all_chars_localized)
    """
    if locale is None:
        try:
            locale = get_locale()
        except RuntimeError:
            locale = DEFAULT_LOCALE

    top5_loc = localize_recognition_results(top5, locale)

    all_chars_loc = []
    for char in all_chars:
        char_key = char.get("character_key", "")
        c = dict(char)

        # 優先使用 char 中已有的 name_i18n / anime_i18n（Qwen 開放識別返回）
        if char.get("name_i18n") and isinstance(char.get("name_i18n"), dict):
            # 已有 Qwen 返回的多語譯名：同時嘗試 hyphen 和 underscore 兩種 key 格式
            _ni = char["name_i18n"]
            _ai = char.get("anime_i18n")
            c["name"] = _ni.get(locale) or _ni.get(_locale_to_i18n_key(locale), char.get("name", ""))
            c["anime"] = (_ai.get(locale) or _ai.get(_locale_to_i18n_key(locale), char.get("anime", ""))) if _ai else char.get("anime", "")
            c["name_i18n"] = _normalize_i18n_dict(char["name_i18n"])
            c["anime_i18n"] = _normalize_i18n_dict(char.get("anime_i18n")) if char.get("anime_i18n") else {}
        elif char_key and char_key in ANIME_CHARACTERS:
            # 已知角色：從 ANIME_CHARACTERS 讀取譯名
            c["name"] = get_char_name(char_key, locale)
            c["anime"] = get_anime_name(char_key, locale)
            c["name_i18n"] = ANIME_CHARACTERS[char_key]["name"]
            c["anime_i18n"] = ANIME_CHARACTERS[char_key]["anime"]
        # 以上皆無：保留原始 name / anime

        all_chars_loc.append(c)

    return top5_loc, all_chars_loc
