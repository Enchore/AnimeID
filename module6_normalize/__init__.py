"""
module6_normalize - 番剧名称归一化模块

导出：
- normalize: 本地快速归一化（别名映射 + 繁简转换 + 模糊匹配）
- normalize_with_api: 含网络验证的归一化（通过 AniList API 确认）
- normalize_record_with_api: 供调度器使用的归一化函数（含异常处理）
- get_all_canonical_names: 获取所有已知规范番剧名
- add_alias: 动态添加别名映射
- reload_aliases: 重新加载别名映射
- get_anilist_cache_stats: 获取 AniList API 缓存统计
"""
from .anime_normalizer import (
    normalize,
    normalize_with_api,
    normalize_record_with_api,
    get_all_canonical_names,
    add_alias,
    reload_aliases,
    get_anilist_cache_stats,
)

__all__ = [
    "normalize",
    "normalize_with_api",
    "normalize_record_with_api",
    "get_all_canonical_names",
    "add_alias",
    "reload_aliases",
    "get_anilist_cache_stats",
]
