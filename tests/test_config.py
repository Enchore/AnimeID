"""全局配置的结构性检查。

這裡只依賴標準庫，不需要 torch / flask，因此可以在任何環境快速跑完。
一旦有人改動 config.py 的結構（例如新增角色但漏填某個語系），這裡會立刻報錯。
"""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import config  # noqa: E402

EXPECTED_LOCALES = {"zh-CN", "zh-TW", "ja", "en", "ko", "fr", "es", "vi", "th"}


@pytest.mark.parametrize(
    "name", ["BASE_DIR", "DATA_DIR", "MODELS_DIR", "LOGS_DIR", "RAW_DIR"]
)
def test_path_constants_are_absolute(name):
    """路徑常數必須是絕對路徑。

    早期版本曾出現相對路徑，導致從不同工作目錄啟動時資料讀不到。
    """
    value = getattr(config, name)
    assert isinstance(value, str), f"{name} 應為字串，實際為 {type(value).__name__}"
    assert os.path.isabs(value), f"{name} 應為絕對路徑，實際為 {value}"


def test_image_preprocessing_constants():
    """影像預處理參數必須與訓練時一致，否則載入 checkpoint 後精度會崩。"""
    assert config.IMAGE_SIZE == 224
    assert len(config.MEAN) == 3
    assert len(config.STD) == 3


def test_character_table_is_populated():
    characters = config.ANIME_CHARACTERS
    assert isinstance(characters, dict)
    assert len(characters) > 0, "角色表不應為空"


@pytest.mark.parametrize("key", sorted(config.ANIME_CHARACTERS))
def test_character_locales_are_complete(key):
    """每個角色都必須提供全部 9 種語系。

    前端會直接按語系代碼取值，缺一個鍵就會在切換語言時顯示空白。
    """
    entry = config.ANIME_CHARACTERS[key]
    assert "name" in entry, f"{key} 缺少 name 欄位"
    assert "anime" in entry, f"{key} 缺少 anime 欄位"
    missing = EXPECTED_LOCALES - set(entry["name"].keys())
    assert not missing, f"{key} 缺少語系: {sorted(missing)}"
