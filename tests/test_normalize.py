"""番劇名稱歸一化的離線行為測試。

注意：這裡只測 `normalize()`（本地別名映射 + 模糊比對），
**不測** `normalize_with_api()`，因為後者會真的打 AniList / Bangumi 網路 API，
在 CI 環境沒有憑證也沒有必要。
"""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from module6_normalize import get_all_canonical_names, normalize  # noqa: E402


def test_alias_resolves_to_canonical_name():
    """大寫拉丁別名必須被映射到規範中文名。"""
    assert normalize("NARUTO") == ("\u706b\u5f71\u5fcd\u8005", True)


def test_canonical_name_is_stable():
    """已經是規範名的輸入不應被再次改寫。"""
    assert normalize("\u706b\u5f71\u5fcd\u8005") == ("\u706b\u5f71\u5fcd\u8005", False)


def test_canonical_name_table_is_loaded():
    """別名表必須真的從 data/ 載入，而不是回傳空清單。"""
    names = get_all_canonical_names()
    assert isinstance(names, list)
    assert len(names) > 0, "規範名清單為空，別名表可能沒被載入"
    assert "\u706b\u5f71\u5fcd\u8005" in names


@pytest.mark.parametrize("query", ["NARUTO", "naruto", "\u706b\u5f71\u5fcd\u8005", "\u9b3c\u6ec5\u4e4b\u5203"])
def test_normalize_returns_contract_shape(query):
    """回傳契約固定為 (str, bool)，呼叫端依賴這個形別做後續判斷。"""
    result = normalize(query)
    assert isinstance(result, tuple), f"{query!r} 未回傳 tuple"
    assert len(result) == 2, f"{query!r} 回傳長度為 {len(result)}"
    name, changed = result
    assert isinstance(name, str) and name, f"{query!r} 的第一個回傳值應為非空字串"
    assert isinstance(changed, bool), f"{query!r} 的第二個回傳值應為 bool"


def test_unknown_input_does_not_raise():
    """沒見過的輸入要能安全通過，不能拋例外打斷批次處理。"""
    name, changed = normalize("\u9019\u662f\u4e00\u500b\u5b8c\u5168\u4e0d\u5b58\u5728\u7684\u756a\u5287\u540d")
    assert isinstance(name, str)
    assert isinstance(changed, bool)
