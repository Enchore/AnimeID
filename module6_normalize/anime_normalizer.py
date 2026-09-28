"""
anime_normalizer.py - 番剧名称自动归一化（含网络验证）

处理以下差异：
- 书名号/括号： 《Re:从零开始的异世界生活》 → Re:从零开始的异世界生活
- 繁简转换： 從零 → 从零
- 简称/别名： Re:从零开始 → Re:从零开始的异世界生活
- 标点差异： Re从零开始的异世界生活 → Re:从零开始的异世界生活
- 多余空格/后缀： 进击的巨人 The Final Season → 进击的巨人

网络验证层（Layer 4）：
- 通过 AniList GraphQL API 验证模糊匹配的番剧是否真正相同
- 本地缓存 API 结果，避免重复请求
- 网络不可用时优雅降级为本地匹配
"""
import re
import os
import json
import logging
import time
import urllib.request
import urllib.error
from typing import Tuple, Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# ===== AniList API 配置 =====
ANILIST_API_URL = "https://graphql.anilist.co"
ANILIST_CACHE_FILE = os.path.join(os.path.dirname(__file__), "anilist_cache.json")
ANILIST_RATE_LIMIT_SLEEP = 0.4  # 每次请求间隔（秒），避免触发速率限制
_last_api_call_time = 0.0

# 内存缓存：{query_name: {"id": int, "titles": List[str], "canonical": str}}
_anilist_cache: Dict[str, Optional[Dict[str, Any]]] = {}
_anilist_cache_loaded = False

# ===== Bangumi API 配置 =====
BANGUMI_API_BASE = "https://api.bgm.tv"
BANGUMI_CACHE_FILE = os.path.join(os.path.dirname(__file__), "bangumi_cache.json")
BANGUMI_RATE_LIMIT_SLEEP = 0.5  # 每次请求间隔（秒），避免触发速率限制
_last_bangumi_call_time = 0.0

# 内存缓存：{query_name: {"id": int, "titles": List[str], "canonical": str}}
_bangumi_cache: Dict[str, Optional[Dict[str, Any]]] = {}
_bangumi_cache_loaded = False

# 全局開關：是否使用 Bangumi API（網路連不上時可停用）
USE_BANGUMI_API: bool = False  # 預設停用（網路連不上 api.bgm.tv）



def _ensure_cache_loaded():
    """延迟加载 AniList 缓存文件"""
    global _anilist_cache_loaded, _anilist_cache
    if _anilist_cache_loaded:
        return
    if os.path.exists(ANILIST_CACHE_FILE):
        try:
            with open(ANILIST_CACHE_FILE, "r", encoding="utf-8") as f:
                _anilist_cache = json.load(f)
            logger.info(f"[AniList] 已加载缓存：{len(_anilist_cache)} 条")
        except Exception as e:
            logger.warning(f"[AniList] 缓存加载失败: {e}")
            _anilist_cache = {}
    _anilist_cache_loaded = True


def _save_anilist_cache():
    """持久化 AniList 缓存到文件"""
    try:
        with open(ANILIST_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_anilist_cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"[AniList] 缓存保存失败: {e}")


def _rate_limited_call():
    """保证请求间隔，避免触发 AniList 速率限制"""
    global _last_api_call_time
    elapsed = time.time() - _last_api_call_time
    if elapsed < ANILIST_RATE_LIMIT_SLEEP:
        time.sleep(ANILIST_RATE_LIMIT_SLEEP - elapsed)
    _last_api_call_time = time.time()



def _contains_chinese(text: str) -> bool:
    """
    检测文本是否包含中文字符
    用于判断是否需要跳过 AniList API 调用（AniList 不支持中文搜索）
    """
    if not text:
        return False
    return any('一' <= c <= '鿿' for c in text)




def _ensure_bangumi_cache_loaded():
    """延迟加载 Bangumi 缓存文件"""
    global _bangumi_cache_loaded, _bangumi_cache
    if _bangumi_cache_loaded:
        return
    if os.path.exists(BANGUMI_CACHE_FILE):
        try:
            with open(BANGUMI_CACHE_FILE, "r", encoding="utf-8") as f:
                _bangumi_cache = json.load(f)
            logger.info(f"[Bangumi] 已加载缓存：{len(_bangumi_cache)} 条")
        except Exception as e:
            logger.warning(f"[Bangumi] 缓存加载失败: {e}")
            _bangumi_cache = {}
    _bangumi_cache_loaded = True


def _save_bangumi_cache():
    """持久化 Bangumi 缓存到文件"""
    try:
        with open(BANGUMI_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_bangumi_cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"[Bangumi] 缓存保存失败: {e}")


def _bangumi_rate_limited_call():
    """保证请求间隔，避免触发 Bangumi 速率限制"""
    global _last_bangumi_call_time
    elapsed = time.time() - _last_bangumi_call_time
    if elapsed < BANGUMI_RATE_LIMIT_SLEEP:
        time.sleep(BANGUMI_RATE_LIMIT_SLEEP - elapsed)
    _last_bangumi_call_time = time.time()

def _search_anilist(anime_name: str) -> Optional[Dict[str, Any]]:
    """
    通过 AniList GraphQL API 搜索番剧
    
    注意：AniList 的 search 参数不支持中文，如果输入是中文，直接返回 None
    
    返回媒体对象（含 id、所有标题）或 None
    
    缓存机制：
    - 内存缓存（快速查询）
    - 文件缓存（跨进程持久化）
    - None 也会被缓存（避免 repeated 查询未找到的番剧）
    """
    if not anime_name or not anime_name.strip():
        return None
    
    _anime_name_stripped = anime_name.strip()
    
    _ensure_cache_loaded()
    
    query_key = _anime_name_stripped
    if query_key in _anilist_cache:
        return _anilist_cache[query_key]

    # 构造 GraphQL 请求
    graphql_query = """
    query ($search: String) {
        Media(search: $search, type: ANIME) {
            id
            title {
                romaji
                english
                native
                chinese
            }
            synonyms
        }
    }
    """
    variables = {"search": query_key}
    payload = json.dumps({
        "query": graphql_query,
        "variables": variables
    }).encode("utf-8")

    req = urllib.request.Request(
        ANILIST_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AnimeID-Normalizer/1.0"
        },
        method="POST"
    )

    try:
        _rate_limited_call()
        with urllib.request.urlopen(req, timeout=8) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            media = result.get("data", {}).get("Media")
            if media:
                # 提取所有标题
                titles: List[str] = []
                title_obj = media.get("title", {})
                for key in ["romaji", "english", "native", "chinese"]:
                    val = title_obj.get(key)
                    if val:
                        titles.append(val)
                synonyms = media.get("synonyms", []) or []
                titles.extend(synonyms)
                titles = [t for t in titles if t]  # 去 None

                # 选择规范名：优先中文，其次 romaji
                canonical = (
                    title_obj.get("chinese")
                    or title_obj.get("romaji")
                    or title_obj.get("english")
                    or title_obj.get("native")
                    or query_key
                )

                entry = {
                    "id": media["id"],
                    "titles": titles,
                    "canonical": canonical
                }
                _anilist_cache[query_key] = entry
                _save_anilist_cache()
                logger.debug(f"[AniList] 命中: '{query_key}' → ID={media['id']}, canonical='{canonical}'")
                return entry
            else:
                # 未找到，缓存 None 避免重复查询
                _anilist_cache[query_key] = None
                _save_anilist_cache()
                logger.debug(f"[AniList] 未找到: '{query_key}'")
                return None
    except urllib.error.URLError as e:
        logger.warning(f"[AniList] 网络错误 '{query_key}': {e}")
        return None
    except Exception as e:
        logger.warning(f"[AniList] 查询错误 '{query_key}': {e}")
        return None




def _search_bangumi(anime_name: str) -> Optional[Dict[str, Any]]:
    """
    通过 Bangumi API 搜索番剧
    
    返回媒体对象（含 id、所有标题）或 None
    
    缓存机制：
    - 内存缓存（快速查询）
    - 文件缓存（跨进程持久化）
    - None 也会被缓存（避免重复查询未找到的番剧）
    """
    # 检查全局開關
    if not USE_BANGUMI_API:
        return None
    
    if not anime_name or not anime_name.strip():
        return None
    
    _anime_name_stripped = anime_name.strip()
    
    _ensure_bangumi_cache_loaded()
    
    query_key = _anime_name_stripped
    if query_key in _bangumi_cache:
        return _bangumi_cache[query_key]
    
    # 构造搜索请求：使用 /search/subject/ 端点
    # 文档：https://apidocs.bgm.tv/
    search_url = f"{BANGUMI_API_BASE}/search/subject/{urllib.request.quote(_anime_name_stripped)}?type=2&responseGroup=medium"
    # type=2 表示番剧（Anime），responseGroup=medium 返回基本信息
    
    req = urllib.request.Request(
        search_url,
        headers={
            "User-Agent": "AnimeID-Normalizer/1.0 (contact: admin@example.com)",
            "Accept": "application/json",
        },
        method="GET"
    )
    
    try:
        _bangumi_rate_limited_call()
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            # Bangumi 搜索返回列表：[{"id": ..., "name": ..., "name_cn": ...}, ...]
            if isinstance(result, list) and len(result) > 0:
                # 取第一个匹配结果
                subject = result[0]
                subject_id = subject.get("id")
                if not subject_id:
                    _bangumi_cache[query_key] = None
                    _save_bangumi_cache()
                    return None
                
                # 获取详细信息（包含多个标题）
                detail_url = f"{BANGUMI_API_BASE}/subject/{subject_id}?responseGroup=large"
                req_detail = urllib.request.Request(
                    detail_url,
                    headers={
                        "User-Agent": "AnimeID-Normalizer/1.0 (contact: admin@example.com)",
                        "Accept": "application/json",
                    },
                    method="GET"
                )
                _bangumi_rate_limited_call()
                with urllib.request.urlopen(req_detail, timeout=10) as resp_detail:
                    detail = json.loads(resp_detail.read().decode("utf-8"))
                    
                    # 提取所有标题
                    titles: List[str] = []
                    # 日文名
                    if detail.get("name"):
                        titles.append(detail["name"])
                    # 中文名
                    if detail.get("name_cn"):
                        titles.append(detail["name_cn"])
                    # 别名（通称）
                    if detail.get("alias"):
                        titles.append(detail["alias"])
                    
                    # 规范名：优先中文名，其次日文名
                    canonical = (
                        detail.get("name_cn")
                        or detail.get("name")
                        or query_key
                    )
                    
                    entry = {
                        "id": subject_id,
                        "titles": titles,
                        "canonical": canonical
                    }
                    _bangumi_cache[query_key] = entry
                    _save_bangumi_cache()
                    logger.debug(f"[Bangumi] 命中: '{query_key}' → ID={subject_id}, canonical='{canonical}'")
                    return entry
            else:
                # 未找到，缓存 None 避免重复查询
                _bangumi_cache[query_key] = None
                _save_bangumi_cache()
                logger.debug(f"[Bangumi] 未找到: '{query_key}'")
                return None
    except urllib.error.URLError as e:
        logger.warning(f"[Bangumi] 网络错误 '{query_key}': {e}")
        return None
    except Exception as e:
        logger.warning(f"[Bangumi] 查询错误 '{query_key}': {e}")
        return None

def _verify_same_anime_via_api(name1: str, name2: str) -> Optional[bool]:
    """
    通过 AniList API 验证两个番剧名是否指向同一部番剧
    返回：
        True  → 确认是同一部
        False → 确认是不同番剧
        None  → 无法确认（API 未找到或网络错误）
    """
    r1 = _search_anilist(name1)
    r2 = _search_anilist(name2)

    if r1 and r2:
        return r1["id"] == r2["id"]

    # 如果其中一个找到了，检查另一个名字是否在标题列表中
    if r1:
        for title in r1["titles"]:
            if name2 in title or title in name2:
                return True
    if r2:
        for title in r2["titles"]:
            if name1 in title or title in name1:
                return True

    return None  # 无法确认




def _verify_same_anime_via_bangumi(name1: str, name2: str) -> Optional[bool]:
    """
    通过 Bangumi API 验证两个番剧名是否指向同一部番剧
    返回：
        True  → 确认是同一部
        False → 确认是不同番剧
        None  → 无法确认（API 未找到或网络错误）
    """
    r1 = _search_bangumi(name1)
    r2 = _search_bangumi(name2)
    
    if r1 and r2:
        return r1["id"] == r2["id"]
    
    # 如果其中一个找到了，检查另一个名字是否在标题列表中
    if r1:
        for title in r1["titles"]:
            if name2 in title or title in name2:
                return True
    if r2:
        for title in r2["titles"]:
            if name1 in title or title in name1:
                return True
    
    return None  # 无法确认


def get_canonical_via_bangumi(anime_name: str) -> Tuple[str, bool]:
    """
    通过 Bangumi API 获取番剧的规范名称
    返回：(规范名, 是否成功查询到)
    """
    entry = _search_bangumi(anime_name)
    if entry:
        return entry["canonical"], True
    return anime_name, False

def get_canonical_via_api(anime_name: str) -> Tuple[str, bool]:
    """
    通过 API 获取番剧的规范名称
    自动选择 API：中文用 Bangumi，非中文用 AniList
    
    返回：(规范名, 是否成功查询到)
    """
    if _contains_chinese(anime_name):
        # 中文：用 Bangumi
        return get_canonical_via_bangumi(anime_name)
    else:
        # 非中文：用 AniList
        entry = _search_anilist(anime_name)
        if entry:
            return entry["canonical"], True
        return anime_name, False


# ===== 导出：获取缓存统计 =====
def get_anilist_cache_stats() -> Dict[str, Any]:
    """返回 AniList API 缓存统计信息"""
    _ensure_cache_loaded()
    valid = sum(1 for v in _anilist_cache.values() if v is not None)
    return {
        "cache_size": len(_anilist_cache),
        "valid_entries": valid,
        "cache_file": ANILIST_CACHE_FILE,
    }

# ===== 基础清洗规则 =====

# ===== 导出：获取 Bangumi 缓存统计 =====
def get_bangumi_cache_stats() -> Dict[str, Any]:
    """返回 Bangumi API 缓存统计信息"""
    _ensure_bangumi_cache_loaded()
    valid = sum(1 for v in _bangumi_cache.values() if v is not None)
    return {
        "cache_size": len(_bangumi_cache),
        "valid_entries": valid,
        "cache_file": BANGUMI_CACHE_FILE,
    }

def _clean(anime_name: str) -> str:
    """基础清洗：去除书名号、多余括号、空格"""
    if not anime_name or not anime_name.strip():
        return ""
    name = anime_name.strip()
    # 去掉中文书名号
    name = re.sub(r'^《|》$', '', name)
    # 去掉英文引号
    name = name.strip('"\'').strip()
    # 去掉全角/半角括号包裹
    name = re.sub(r'^[（(].*?[）)]$', lambda m: m.group(0)[1:-1], name)
    return name


# ===== 繁→简 转换表（常用字） =====
_TRAD_TO_SIMP = {
    "從": "从", "異": "异", "戰": "战", "鬥": "斗", "靈": "灵",
    "龍": "龙", "寶": "宝", "華": "华", "麗": "丽", "夢": "梦",
    "愛": "爱", "戀": "恋", "樂": "乐", "時": "时", "間": "间",
    "進": "进", "擊": "击", "殺": "杀", "劍": "剑", "風": "风",
    "雲": "云", "遠": "远", "長": "长", "門": "门", "開": "开",
    "關": "关", "會": "会", "國": "国", "學": "学", "園": "园",
    "體": "体", "對": "对", "選": "选", "點": "点", "電": "电",
    "動": "动", "畫": "画", "話": "话", "說": "说", "記": "记",
    "術": "术", "團": "团", "後": "后", "過": "过", "經": "经",
    "網": "网", "聯": "联", "機": "机", "關": "关", "實": "实",
    "現": "现", "發": "发", "裏": "里", "裡": "里", "衛": "卫",
    "護": "护", "險": "险", "亂": "乱", "宮": "宫", "鳥": "鸟",
    "魚": "鱼", "蟲": "虫", "獸": "兽", "萬": "万", "億": "亿",
    "歲": "岁", "聲": "声", "聽": "听", "視": "视", "覺": "觉",
    "變": "变", "讓": "让", "識": "识", "議": "议", "設": "设",
    "計": "计", "語": "语", "數": "数", "據": "据", "碼": "码",
    "傳": "传", "轉": "转", "載": "载", "輸": "输", "輕": "轻",
    "鐵": "铁", "鋼": "钢", "銀": "银", "金": "金", "魔": "魔",
    "聖": "圣", "鬼": "鬼", "神": "神", "界": "界", "世": "世",
    "王": "王", "帝": "帝", "皇": "皇", "師": "师", "士": "士",
    "者": "者", "刃": "刃", "滅": "灭", "零": "零",
    "瑪": "玛", "爾": "尔", "薩": "萨", "亞": "亚", "魯": "鲁",
    "澤": "泽", "維": "维", "歐": "欧", "羅": "罗", "斯": "斯",
}


def _simplify(text: str) -> str:
    """将常见繁体字转为简体"""
    result = []
    for ch in text:
        result.append(_TRAD_TO_SIMP.get(ch, ch))
    return "".join(result)


# ===== 番剧同义名称映射（别名 → 规范名） =====
# 规范名必须与 config.py 的 ANIME_CHARACTERS 保持一致
_ANIME_ALIASES: dict[str, str] = {}

# 动态从 config 构建映射
def _build_alias_map():
    """从 ANIME_CHARACTERS 中提取番剧名并构建规范名集合"""
    global _ANIME_ALIASES
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from config import ANIME_CHARACTERS
    except ImportError:
        # 如果在模块导入时 config 尚未加载，稍后延迟加载
        return

    canonical_names = set()
    for info in ANIME_CHARACTERS.values():
        anime_val = info.get("anime", "")
        if isinstance(anime_val, dict):
            # 多語言字典：優先取 zh-CN，回退 zh-TW
            name = anime_val.get("zh-CN", "") or anime_val.get("zh-TW", "") or ""
        else:
            name = str(anime_val) if anime_val else ""
        if name:
            canonical_names.add(name)

    # 基础硬编码映射（简称 → 全名）
    hardcoded = {
        # Re:从零开始的异世界生活 系列
        "re:从零开始的异世界生活": "Re:从零开始的异世界生活",
        "re：从零开始的异世界生活": "Re:从零开始的异世界生活",
        "re:从零开始": "Re:从零开始的异世界生活",
        "re：从零开始": "Re:从零开始的异世界生活",
        "Re:从零开始": "Re:从零开始的异世界生活",
        "Re：从零开始": "Re:从零开始的异世界生活",
        "Re:从零开始的异世界生活第二季": "Re:从零开始的异世界生活",
        "Re:从零开始的异世界生活 第二季": "Re:从零开始的异世界生活",
        "从零开始的异世界生活": "Re:从零开始的异世界生活",
        "从零开始": "Re:从零开始的异世界生活",
        "Re:Life in a different world from zero": "Re:从零开始的异世界生活",
        "Re:Zero": "Re:从零开始的异世界生活",
        "re:zero": "Re:从零开始的异世界生活",

        # 火影忍者 系列
        "Naruto": "火影忍者",
        "naruto": "火影忍者",
        "火影": "火影忍者",
        "火影忍者疾风传": "火影忍者",
        "火影忍者 疾风传": "火影忍者",
        "火影忍者剧场版": "火影忍者",
        "Boruto": "火影忍者",
        "博人传": "火影忍者",
        "BORUTO": "火影忍者",

        # 海贼王 系列
        "One Piece": "海贼王",
        "one piece": "海贼王",
        "ONE PIECE": "海贼王",
        "航海王": "海贼王",
        "海贼": "海贼王",
        "海贼王剧场版": "海贼王",

        # 进击的巨人 系列
        "Attack on Titan": "进击的巨人",
        "attack on titan": "进击的巨人",
        "进击的巨人最终季": "进击的巨人",
        "进击的巨人 The Final Season": "进击的巨人",
        "进击的巨人 最终季": "进击的巨人",
        "巨人": "进击的巨人",
        "进击": "进击的巨人",

        # 鬼灭之刃 系列
        "Demon Slayer": "鬼灭之刃",
        "demon slayer": "鬼灭之刃",
        "Kimetsu no Yaiba": "鬼灭之刃",
        "鬼灭": "鬼灭之刃",
        "鬼灭之刃 无限列车篇": "鬼灭之刃",
        "鬼灭之刃剧场版": "鬼灭之刃",
        "鬼滅之刃": "鬼灭之刃",

        # 我的英雄学院
        "My Hero Academia": "我的英雄学院",
        "my hero academia": "我的英雄学院",
        "僕のヒーローアカデミア": "我的英雄学院",
        "英雄学院": "我的英雄学院",
        "我的英雄": "我的英雄学院",
        "MHA": "我的英雄学院",

        # 龙珠 系列
        "Dragon Ball": "龙珠",
        "dragon ball": "龙珠",
        "龙珠Z": "龙珠",
        "龙珠超": "龙珠",
        "龙珠GT": "龙珠",
        "七龙珠": "龙珠",
        "ドラゴンボール": "龙珠",

        # 死神 系列
        "Bleach": "死神",
        "bleach": "死神",
        "死神 千年血战篇": "死神",
        "死神剧场版": "死神",
        "BLEACH": "死神",

        # 幸运星
        "Lucky Star": "幸运星",
        "lucky star": "幸运星",
        "らき☆すた": "幸运星",
        "Lucky☆Star": "幸运星",

        # 其他常见作品
        "刀剑神域": "刀剑神域",
        "Sword Art Online": "刀剑神域",
        "SAO": "刀剑神域",
        "魔法禁书目录": "魔法禁书目录",
        "某科学的超电磁炮": "某科学的超电磁炮",
        "Fate/Stay Night": "Fate系列",
        "Fate/stay night": "Fate系列",
        "Fate": "Fate系列",
        "fate": "Fate系列",
        "钢之炼金术师": "钢之炼金术师",
        "Fullmetal Alchemist": "钢之炼金术师",
        "一拳超人": "一拳超人",
        "One Punch Man": "一拳超人",
        "东京食尸鬼": "东京食尸鬼",
        "东京喰种": "东京食尸鬼",
        "约定的梦幻岛": "约定的梦幻岛",
        "The Promised Neverland": "约定的梦幻岛",
        "咒术回战": "咒术回战",
        "Jujutsu Kaisen": "咒术回战",
        "间谍过家家": "间谍过家家",
        "Spy x Family": "间谍过家家",
        "SPY×FAMILY": "间谍过家家",
        "更衣人偶坠入爱河": "更衣人偶坠入爱河",
        "恋上换装娃娃": "更衣人偶坠入爱河",
        "孤独摇滚": "孤独摇滚",
        "Bocchi the Rock!": "孤独摇滚",
        "我推的孩子": "我推的孩子",
        "Oshi no Ko": "我推的孩子",
        "葬送的芙莉莲": "葬送的芙莉莲",
        "Sousou no Frieren": "葬送的芙莉莲",

        # Chiikawa / 吉伊卡哇 系列
        "Chiikawa": "吉伊卡哇",
        "chiikawa": "吉伊卡哇",
        "Chikawa": "吉伊卡哇",
        "chiiwaka": "吉伊卡哇",  # 常見拼寫錯誤
        "Chiikaw": "吉伊卡哇",  # 常見拼寫錯誤
        "吉伊卡哇": "吉伊卡哇",
        "ちいかわ": "吉伊卡哇",
        "チイカワ": "吉伊卡哇",

        # 地獄少女
        "Hell Girl": "地獄少女",
        "hell girl": "地獄少女",
        "地狱少女": "地獄少女",
        "地獄少女": "地獄少女",
        "Jigoku Shoujo": "地獄少女",

        # 繁→简 兜底（常见繁体→简体单写）
        "鬼滅之刃": "鬼灭之刃",

        # Re:从零开始 补充（大写的完整名也作为 key）
        "Re:从零开始的异世界生活": "Re:从零开始的异世界生活",
        "Re:從零開始的異世界生活": "Re:从零开始的异世界生活",
        "從零開始的異世界生活": "Re:从零开始的异世界生活",
        "从零开始的异世界生活第二季": "Re:从零开始的异世界生活",
        "从零开始的异世界生活 第二季": "Re:从零开始的异世界生活",
    }

    _ANIME_ALIASES = hardcoded


import sys
from pathlib import Path

# 模块加载时构建映射
try:
    _build_alias_map()
except Exception as e:
    logger.debug(f"番剧别名映射延迟加载: {e}")


def normalize(anime_name: str) -> Tuple[str, bool]:
    """
    将番剧名称归一化为规范名

    参数：
        anime_name: 原始番剧名称

    返回：
        (canonical_name, was_normalized)
        - canonical_name: 归一化后的规范名
        - was_normalized: 是否发生了归一化（True=已修改, False=无需修改）
    """
    if not anime_name or not anime_name.strip():
        return "", False

    original = anime_name.strip()
    name = _clean(original)

    if not name:
        return original, False

    # ===== 第1层：精确匹配别名 =====
    if name in _ANIME_ALIASES:
        canonical = _ANIME_ALIASES[name]
        if canonical != original:
            return canonical, True
        return original, False

    # 第1.5层：小写匹配（英文别名）
    name_lower = name.lower()
    for alias, canonical in _ANIME_ALIASES.items():
        if alias.lower() == name_lower:
            if canonical != original:
                return canonical, True
            return original, False

    # ===== 第2层：繁→简 后再匹配 =====
    simplified = _simplify(name)
    if simplified != name:
        if simplified in _ANIME_ALIASES:
            canonical = _ANIME_ALIASES[simplified]
            if canonical != original:
                return canonical, True
            return original, False
        name = simplified

    # ===== 第3层：模糊匹配（最长公共前缀） =====
    # 去掉常见的季数/剧场版等后缀后再尝试
    name_no_suffix = re.sub(
        r'\s*(第[一二三四五六七八九十\d]+季|Season\s*\d+|剧场版|The\s+Final\s+Season|最终季|完结篇|第一[部季]|第二[部季]|第三[部季]).*$',
        '', name, flags=re.IGNORECASE
    ).strip()

    if name_no_suffix and name_no_suffix != name:
        # 再去掉后缀后尝试匹配
        name_no_suffix_clean = _simplify(name_no_suffix)
        if name_no_suffix_clean in _ANIME_ALIASES:
            canonical = _ANIME_ALIASES[name_no_suffix_clean]
            if canonical != original:
                return canonical, True
            return original, False

        # 在已知规范名集合中搜索近似的
        for canonical in set(_ANIME_ALIASES.values()):
            # 检查 name_no_suffix 是否为 canonical 的前缀（或反之）
            stripped_query = re.sub(r'[^\w\u4e00-\u9fff]', '', name_no_suffix_clean).lower()
            stripped_canon = re.sub(r'[^\w\u4e00-\u9fff]', '', canonical).lower()
            if stripped_query and stripped_canon:
                # 一方是另一方的子串
                if stripped_query in stripped_canon or stripped_canon in stripped_query:
                    # 确认不是太短（避免误匹配）
                    if len(stripped_query) >= 3 and len(stripped_canon) >= 3:
                        return canonical, True

    # ===== 无匹配，返回原名 =====
    return original, False


def normalize_with_api(anime_name: str, verify_fuzzy: bool = True) -> Tuple[str, bool, Optional[str]]:
    """
    通过 AniList API 辅助归一化番剧名称（网络验证层）

    参数：
        anime_name: 原始番剧名称
        verify_fuzzy: 是否对模糊匹配结果进行网络验证

    返回：
        (canonical_name, was_normalized, source)
        - source: "local_exact" | "local_fuzzy" | "api_verified" | "api_direct" | "api_failed" | None
        - 当 source="api_verified" 时表示经过网络确认，可信度最高
        - 当 source="api_direct" 时表示本地无匹配但通过 API 查到了规范名
        - 当 source=None 时表示未发生改变

    工作流程：
    1. 先执行本地归一化（快速路径）
    2. 若本地匹配成功：
       - 若 verify_fuzzy=True，调用 AniList API 验证结果是否真实
       - 验证通过 → 返回本地结果（source="api_verified"）
       - 验证不通过 → 以 API 结果为准（source="api_direct"）
    3. 若本地无匹配：
       - 调用 AniList API 直接查询规范名
       - 找到 → 返回 API 规范名（source="api_direct"）
       - 未找到 → 返回原名（source="api_failed"）
    """
    if not anime_name or not anime_name.strip():
        return "", False, None

    original = anime_name.strip()

    # ==== 第1步：本地快速归一化 ====
    local_canon, local_changed = normalize(original)

    # ==== 第2步：本地已匹配 → 网络验证 ====
    if local_changed and verify_fuzzy:
        # 用 API 验证 original → local_canon 是否是同一部番剧
        verification = _verify_same_anime_via_api(original, local_canon)
        if verification is True:
            # API 确认是同一部
            logger.debug(f"[归一化-API] 验证通过: '{original}' ≈ '{local_canon}'")
            return local_canon, True, "api_verified"
        elif verification is False:
            # API 确认是不同番剧！本地匹配有误
            logger.warning(
                f"[归一化-API] 本地匹配有误: '{original}' → '{local_canon}' (API验证: 不同番剧)"
            )
            # 以 original 通过 API 直接查询规范名为准
            api_canon, api_ok = get_canonical_via_api(original)
            if api_ok:
                return api_canon, (api_canon != original), "api_direct"
            # API 也查不到，退回原名
            return original, False, "api_failed"
        else:
            # API 无法确认（网络错误或未收录），信任本地结果
            logger.debug(f"[归一化-API] 无法验证: '{original}' ≈ '{local_canon}' (API不可用)")
            return local_canon, True, "api_verified"  # 仍标记为 verified（尽力而为）

    # ==== 第3步：本地无匹配 → API 直接查询 ====
    if not local_changed:
        api_canon, api_ok = get_canonical_via_api(original)
        if api_ok:
            logger.info(f"[归一化-API] API直接命中: '{original}' → '{api_canon}'")
            return api_canon, (api_canon != original), "api_direct"

    # ==== 第4步：本地有匹配但不验证，或 API 也查不到 ====
    if local_changed:
        return local_canon, True, "local_fuzzy"
    return original, False, None


# ===== 批量 API 归一化（供调度器使用）=====
def normalize_record_with_api(anime_name: str) -> Tuple[str, bool, Optional[str]]:
    """
    供调度器使用的归一化函数，自动处理网络验证
    与 normalize_with_api 相同，但增加了额外的异常处理
    """
    try:
        return normalize_with_api(anime_name, verify_fuzzy=True)
    except Exception as e:
        logger.warning(f"[归一化-API] 异常: {e}，降级为本地归一化")
        result, changed = normalize(anime_name)
        return result, changed, "local_fallback"


def get_all_canonical_names() -> list:
    """获取所有已知规范番剧名"""
    return sorted(set(_ANIME_ALIASES.values()))


def add_alias(alias: str, canonical: str):
    """动态添加别名映射（用于管理后台/API）"""
    global _ANIME_ALIASES
    _ANIME_ALIASES[alias.strip()] = canonical.strip()
    logger.info(f"[归一化] 新增别名: '{alias}' → '{canonical}'")


def reload_aliases():
    """重新加载别名映射（当 config 更新时）"""
    _build_alias_map()
    logger.info(f"[归一化] 别名映射已重载，共 {len(_ANIME_ALIASES)} 条")
