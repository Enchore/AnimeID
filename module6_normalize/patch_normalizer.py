"""
修补 anime_normalizer.py，添加 Bangumi API 支援
"""
import re

filepath = r"F:\Projects\AnimeID\anime-recognition-system\module6_normalize\anime_normalizer.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# ===== 1. 在 ANILIST 配置之后添加 Bangumi API 配置 =====
bangumi_config = '''
# ===== Bangumi API 配置 =====
BANGUMI_API_BASE = "https://api.bgm.tv"
BANGUMI_CACHE_FILE = os.path.join(os.path.dirname(__file__), "bangumi_cache.json")
BANGUMI_RATE_LIMIT_SLEEP = 0.5  # 每次请求间隔（秒），避免触发速率限制
_last_bangumi_call_time = 0.0

# 内存缓存：{query_name: {"id": int, "titles": List[str], "canonical": str}}
_bangumi_cache: Dict[str, Optional[Dict[str, Any]]] = {}
_bangumi_cache_loaded = False
'''

# 在 _anilist_cache_loaded = False 之后插入
marker1 = "_anilist_cache_loaded = False"
if marker1 in content and "BANGUMI_API_BASE" not in content:
    idx = content.index(marker1) + len(marker1)
    content = content[:idx] + "\n" + bangumi_config + content[idx:]

# ===== 2. 添加 Bangumi 缓存加载/保存/速率限制函数（在 _search_anilist 函数之前） =====
bangumi_helpers = '''

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
'''

# 在 _search_anilist 函数定义之前插入
marker2 = "def _search_anilist(anime_name: str) -> Optional[Dict[str, Any]]:"
if marker2 in content and "def _ensure_bangumi_cache_loaded" not in content:
    idx = content.index(marker2)
    content = content[:idx] + bangumi_helpers + "\n" + content[idx:]

# ===== 3. 添加 _search_bangumi() 函数（在 _search_anilist 函数之后） =====
search_bangumi_func = '''

def _search_bangumi(anime_name: str) -> Optional[Dict[str, Any]]:
    """
    通过 Bangumi API 搜索番剧
    
    返回媒体对象（含 id、所有标题）或 None
    
    缓存机制：
    - 内存缓存（快速查询）
    - 文件缓存（跨进程持久化）
    - None 也会被缓存（避免重复查询未找到的番剧）
    """
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
'''

# 在 _search_anilist 函数结束之后插入（在 _verify_same_anime_via_api 函数之前）
marker3 = "def _verify_same_anime_via_api(name1: str, name2: str) -> Optional[bool]:"
if marker3 in content and "def _search_bangumi" not in content:
    idx = content.index(marker3)
    content = content[:idx] + search_bangumi_func + "\n" + content[idx:]

# ===== 4. 添加 Bangumi 验证和获取规范名函数 =====
bangumi_verify_funcs = '''

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
'''

# 在 _verify_same_anime_via_api 函数之后插入（在 get_canonical_via_api 函数之前）
marker4 = "def get_canonical_via_api(anime_name: str) -> Tuple[str, bool]:"
if marker4 in content and "def _verify_same_anime_via_bangumi" not in content:
    idx = content.index(marker4)
    content = content[:idx] + bangumi_verify_funcs + "\n" + content[idx:]

# ===== 5. 修改 _verify_same_anime_via_api() 以支持多 API =====
# 替换整个函数
old_verify_func = '''def _verify_same_anime_via_api(name1: str, name2: str) -> Optional[bool]:
    """
    通过 AniList GraphQL API 验证两个番剧名是否指向同一部番剧
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
    
    return None  # 无法确认'''

new_verify_func = '''def _verify_same_anime_via_api(name1: str, name2: str) -> Optional[bool]:
    """
    通过 API 验证两个番剧名是否指向同一部番剧
    自动选择 API：中文用 Bangumi，非中文用 AniList
    
    返回：
        True  → 确认是同一部
        False → 确认是不同番剧
        None  → 无法确认（API 未找到或网络错误）
    """
    # 判断两个名称的语言
    is_chinese1 = _contains_chinese(name1)
    is_chinese2 = _contains_chinese(name2)
    
    # 如果两个都是中文，用 Bangumi
    if is_chinese1 and is_chinese2:
        return _verify_same_anime_via_bangumi(name1, name2)
    
    # 如果都不是中文，用 AniList
    if not is_chinese1 and not is_chinese2:
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
        return None
    
    # 混合情况：一个中文，一个非中文
    # 尝试用 Bangumi 查中文，用 AniList 查非中文，然后比较 ID
    bg_result = None
    al_result = None
    
    if is_chinese1:
        bg_result = _search_bangumi(name1)
    else:
        al_result = _search_anilist(name1)
        
    if is_chinese2:
        bg_result2 = _search_bangumi(name2)
    else:
        al_result2 = _search_anilist(name2)
    
    # 比较两个结果（如果都找到了）
    if bg_result and al_result2:
        # 检查 Bangumi 结果中的标题是否匹配 AniList 查询的名称
        for title in bg_result["titles"]:
            if name2 in title or title in name2:
                return True
        return False
    if al_result and bg_result2:
        for title in al_result["titles"]:
            if name1 in title or title in name1:
                return True
        return False
    
    return None  # 无法确认'''

if old_verify_func in content:
    content = content.replace(old_verify_func, new_verify_func)

# ===== 6. 修改 get_canonical_via_api() 以支持多 API =====
old_get_canonical = '''def get_canonical_via_api(anime_name: str) -> Tuple[str, bool]:
    """
    通过 AniList API 获取番剧的规范名称
    返回：(规范名, 是否成功查询到)
    """
    entry = _search_anilist(anime_name)
    if entry:
        return entry["canonical"], True
    return anime_name, False'''

new_get_canonical = '''def get_canonical_via_api(anime_name: str) -> Tuple[str, bool]:
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
        return anime_name, False'''

if old_get_canonical in content:
    content = content.replace(old_get_canonical, new_get_canonical)

# ===== 7. 移除 _search_anilist() 中的中文检测逻辑 =====
# 替换 _search_anilist 函数开头部分
old_chinese_check = '''    # 检测是否为中文文本（AniList API 不支持中文搜索）
    _anime_name_stripped = anime_name.strip()
    if _contains_chinese(_anime_name_stripped):
        logger.debug(f"[AniList] 跳过中文查询: '{_anime_name_stripped}' (AniList 不支持中文搜索)")
        return None'''

new_no_chinese_check = '''    _anime_name_stripped = anime_name.strip()'''

if old_chinese_check in content:
    content = content.replace(old_chinese_check, new_no_chinese_check)
print("✅ anime_normalizer.py 修补完成！")
print("添加的功能：")
bangumi_stats_func = '''

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
'''

# 在 get_anilist_cache_stats 函数之后插入
marker5 = "def get_anilist_cache_stats() -> Dict[str, Any]:"
if marker5 in content and "def get_bangumi_cache_stats" not in content:
    # 找到该函数的结束位置（下一个 def 或文件结束）
    idx = content.index(marker5)
    # 找到函数结束（通过缩进判断）
    lines = content[idx:].split("\n")
    end_idx = idx
    for i, line in enumerate(lines):
        if i > 0 and line and not line.startswith("    ") and not line.startswith("\t") and not line.strip().startswith("#"):
            # 可能是下一个函数或顶层代码
            if line.startswith("def ") or line.startswith("class "):
                end_idx = idx + len("\n".join(lines[:i]))
                break
    else:
        end_idx = len(content)
    
    content = content[:end_idx] + bangumi_stats_func + content[end_idx:]

# 保存修改后的内容
with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("✅ anime_normalizer.py 修补完成！")
print("添加的功能：")
print("  1. Bangumi API 配置和缓存")
print("  2. _search_bangumi() 搜索函数")
print("  3. _verify_same_anime_via_bangumi() 验证函数")
print("  4. get_canonical_via_bangumi() 获取规范名函数")
print("  5. 修改了 _verify_same_anime_via_api() 和 get_canonical_via_api() 支持多 API")
print("  6. 移除了 _search_anilist() 中的中文跳过逻辑")
print("  7. 添加了 get_bangumi_cache_stats() 导出函数")
