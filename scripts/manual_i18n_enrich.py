"""
手動執行：i18n 補全（**不是** pytest 測試）

本檔案原名 `test_i18n_enrich.py`，放在專案根目錄。由於檔名以 `test_` 開頭，
pytest 會把它當成測試收集，而它在 import 階段就會建立 Flask app context 並呼叫
`enrich_all_missing_i18n(..., use_llm=True)` 發送**真實的 LLM 請求** ——
導致任何 CI 環境在沒有 API 憑證時收集階段直接崩潰。

因此改名並移至 scripts/：
- 它是需要人工確認、會打外部 API 的維運腳本，不適合進自動化測試
- 自動化測試請放 tests/，且只能測離線邏輯

用法（需先設定好 LLM API 憑證）：
    python scripts/manual_i18n_enrich.py
"""
import sys
import os

# 添加專案路徑（scripts/ 下執行時需要回到專案根目錄）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 匯入 Flask app
from module3_web.app import app, db

# 建立應用上下文
with app.app_context():
    print("=" * 60)
    print("測試 i18n 補全功能")
    print("=" * 60)

    # 執行補全（停用 Bangumi 和 AniList，啟用 LLM）
    from module6_normalize.i18n_enricher import enrich_all_missing_i18n

    result = enrich_all_missing_i18n(
        db.session,
        batch_size=100,
        use_bangumi=False,  # Bangumi API 連不上
        use_anilist=False,  # AniList 不支援中文
        use_llm=True  # 啟用 LLM 翻譯
    )

    print(f"\n測試結果：")
    print(f"  掃描：{result.get('scanned', 0)} 條")
    print(f"  補全：{result.get('enriched', 0)} 條")

    if result.get('details'):
        print(f"\n詳細記錄（前 10 條）：")
        for i, detail in enumerate(result['details'][:10], 1):
            char_name = detail.get('char_name', 'N/A')
            anime_name = detail.get('anime_name', 'N/A')
            print(f"  {i}. {char_name} ({anime_name})")

    if result.get('errors'):
        print(f"\n錯誤（前 5 條）：")
        for i, error in enumerate(result['errors'][:5], 1):
            print(f"  {i}. {error}")

    print("\n" + "=" * 60)
