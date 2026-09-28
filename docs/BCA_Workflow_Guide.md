# B→C→A 分布式訓練工作流指南

## 概述

這個工作流讓你使用三台設備協同工作，持續提升動漫角色識別模型的準確率：

- **設備 B**（爬取+標注）：從 Danbooru 爬取圖片，用 Qwen-VL 自動標注
- **設備 C**（訓練）：使用標注數據訓練本地模型（MobileNetV2）
- **設備 A**（運行服務）：運行識別服務，使用訓練好的模型

---

## 步驟 1：設備 B - 爬取圖片 + 自動標注

### 1.1 安裝依賴

```bash
pip install requests pillow
```

### 1.2 獲取更多角色標籤（可選，用於擴展到 10,000 個角色）

```bash
# 從 Danbooru API 獲取熱門角色標籤
python scripts/fetch_danbooru_tags.py --limit 5000 --min-count 500

# 這會生成 config/danbooru_tags.json
# 你需要手動編輯，添加中文角色名
```

### 1.3 導入角色到爬取列表（可選）

```bash
# 將 Danbooru 標籤導入到爬取列表
python scripts/import_tags_to_crawl_list.py --input config/danbooru_tags.json --limit 1000

# 這會更新 config/characters_to_crawl.json
# ⚠️ 注意：需要人工審核並添加正確的中文角色名！
```

### 1.4 批量爬取（支持斷點續爬）

```bash
# 查看爬取進度
python scripts/batch_crawl.py --status

# 開始批量爬取（會自動從第一個 pending 角色開始）
python scripts/batch_crawl.py

# 如果中斷，重新運行即可繼續（自動跳過已完成的角色）
python scripts/batch_crawl.py --resume  # 這是默認行為

# 只處理高優先級角色（priority=1）
python scripts/batch_crawl.py --priority 1

# 限制處理數量（測試用）
python scripts/batch_crawl.py --limit 10

# 重置所有狀態（慎用）
python scripts/batch_crawl.py --reset
```

### 1.5 檢查爬取結果

爬取完成後，檢查以下目錄：

```
data/
├── crawled/              # 爬取的原始圖片（按角色分類）
│   ├── 雷姆/
│   ├── 艾米莉亞/
│   └── ...
├── auto_labels.json      # Qwen-VL 自動標注結果
└── user_labeled/        # 訓練數據（將複製到設備 C）
    ├── images/           # 圖片
    └── labels.csv       # 標注文件
```

### 1.6 複製數據到設備 C

```bash
# 方法 1：使用 U 盤/移動硬盤
# 複製整個 data/ 目錄到設備 C

# 方法 2：使用網路共享（如果設備在同一局域網）
# 在設備 B 上共享 data/ 目錄，然後在設備 C 上掛載

# 方法 3：使用雲盤（Google Drive, Dropbox 等）
# 上傳 data/ 目錄到雲盤，然後在設備 C 下載
```

---

## 步驟 2：設備 C - 訓練模型

### 2.1 準備數據

確保設備 C 上有以下文件：

```
F:\Projects\AnimeID\anime-recognition-system\
├── data\
│   ├── user_labeled\    # 從設備 B 複製過來
│   │   ├── images\
│   │   └── labels.csv
│   └── train\          # 現有訓練數據（如果有）
├── config.py
├── module2_model\
├── module5_autotrain\
└── scripts\
```

### 2.2 檢查類別一致性

```bash
# 確保設備 C 的 CLASS_NAMES 與設備 A 相同！
# 檢查 config.py 中的 ANIME_CHARACTERS
```

### 2.3 運行訓練

```bash
# 完整訓練（推薦）
python scripts/train_on_device_c.py --data-dir ../data --output-dir ../models/auto_v1

# 這會：
# 1. 檢查類別一致性
# 2. 統計訓練數據
# 3. 運行訓練（15 epochs）
# 4. 保存模型到 output-dir
```

### 2.4 檢查訓練結果

訓練完成後，檢查以下文件：

```
models/
├── auto_v1\
│   ├── anime_recognition_mobilenetv2_best.h5   # 最佳模型
│   ├── anime_recognition_mobilenetv2_final.h5  # 最終模型
│   ├── class_names.json                        # 類別名稱
│   └── training_history.png                   # 訓練曲線
```

### 2.5 複製模型到設備 A

```bash
# 方法 1：使用 U 盤/移動硬盤
# 複製 models/auto_v1/ 目錄到設備 A

# 方法 2：使用網路共享
# 在設備 C 上共享 models/ 目錄，然後在設備 A 掛載

# 方法 3：使用雲盤
# 上傳 models/auto_v1/ 到雲盤，然後在設備 A 下載
```

---

## 步驟 3：設備 A - 替換模型

### 3.1 準備新模型

確保設備 A 上有新模型文件：

```
F:\Projects\AnimeID\anime-recognition-system\
├── models\
│   ├── auto_v1\                 # 從設備 C 複製過來
│   │   ├── anime_recognition_mobilenetv2_best.h5
│   │   └── class_names.json
│   └── current\                 # 當前使用的模型（將被備份）
```

### 3.2 運行模型替換腳本

```bash
# 自動備份舊模型並替換為新模型
python scripts/replace_model_on_device_a.py

# 這會：
# 1. 備份當前模型到 models/backup/YYYYMMDD_HHMMSS/
# 2. 驗證新模型文件完整性
# 3. 替換模型文件
# 4. 提示重啟服務
```

### 3.3 重啟服務

```bash
# 停止當前服務（Ctrl+C）

# 重新啟動
python -m module3_web.app

# 檢查新模型是否載入成功
# 查看日誌：Loading local model from models/current/anime_recognition_mobilenetv2_best.h5
```

---

## 自動化建議

### 方案 1：使用定時任務（推薦）

**設備 B**（每天凌晨 2:00 自動爬取）：
```bash
# Windows 任務計劃程式
schtasks /create /sc daily /st 02:00 /tn "AnimeID_Crawl" /tr "python F:\Projects\AnimeID\anime-recognition-system\scripts\batch_crawl.py"
```

**設備 C**（每天凌晨 4:00 自動訓練）：
```bash
# 檢查是否有新數據，如果有則訓練
schtasks /create /sc daily /st 04:00 /tn "AnimeID_Train" /tr "python F:\Projects\AnimeID\anime-recognition-system\scripts\train_on_device_c.py"
```

**設備 A**（每天凌晨 6:00 自動檢查並替換模型）：
```bash
# 檢查是否有新模型，如果有則替換並重啟
schtasks /create /sc daily /st 06:00 /tn "AnimeID_ReplaceModel" /tr "python F:\Projects\AnimeID\anime-recognition-system\scripts\replace_model_on_device_a.py"
```

### 方案 2：使用腳本自動傳輸文件

創建一個傳輸腳本（使用 robocopy 或 rsync）：

**設備 B → 設備 C**：
```bash
# 每天自動同步 data/ 目錄到設備 C
robocopy F:\Projects\AnimeID\anime-recognition-system\data\ \\DEVICE-C\AnimeID\data\ /E /COPYALL /R:3 /W:5
```

**設備 C → 設備 A**：
```bash
# 訓練完成後自動同步模型到設備 A
robocopy F:\Projects\AnimeID\anime-recognition-system\models\auto_v1\ \\DEVICE-A\AnimeID\models\new\ /E /COPYALL /R:3 /W:5
```

---

## 監控和維護

### 檢查爬取進度

```bash
# 在設備 B 上
python scripts/batch_crawl.py --status

# 輸出示例：
# 📊 爬取進度
# ================================================
#   總角色數：200
#   ✅ 已完成：50
#   ❌ 失敗：2
#   ⏳ 待處理：148
#   進度：25.0%
```

### 檢查訓練歷史

```bash
# 在設備 C 上
cat F:\Projects\AnimeID\anime-recognition-system\models\auto_v1\training_log.txt
```

### 檢查模型版本

```bash
# 在設備 A 上
python -c "from config import *; print('Current model:', MODEL_PATH)"
```

---

## 故障排除

### 問題 1：爬取速度慢

**原因**：Danbooru API 限速，Qwen-VL API 限速

**解決**：
- 增加 `time.sleep()` 間隔
- 使用多個 Qwen API Key 輪詢
- 減少每個角色的爬取數量

### 問題 2：訓練準確率低

**原因**：數據量不足，類別不平衡，圖片質量差

**解決**：
- 增加每個角色的圖片數量（目標：每個角色 200+ 張）
- 使用數據增強（翻轉、旋轉、色彩調整）
- 手動審核標注結果，刪除錯誤標注

### 問題 3：模型替換後服務無法啟動

**原因**：類別不一致，模型文件損壞

**解決**：
- 檢查 `class_names.json` 是否與設備 A 的 `ANIME_CHARACTERS` 一致
- 檢查模型文件是否完整（文件大小 > 0）
- 檢查日誌中的錯誤信息

---

## 下一步計劃

1. **短期（1-2 周）**：
   - 爬取 200 個熱門角色的圖片（每個角色 100-200 張）
   - 訓練並替換模型
   - 檢查識別準確率提升

2. **中期（1-2 月）**：
   - 擴展到 1,000 個角色
   - 優化爬取和標注流程
   - 優化訓練超參數

3. **長期（3-6 月）**：
   - 擴展到 10,000 個角色
   - 實作持續學習（online learning）
   - 實作 A/B 測試（比較不同模型的準確率）

---

## 常見問題

### Q1：需要多少圖片才能訓練出準確的模型？

**A**：建議每個角色至少 100-200 張圖片，總數據量 10,000-20,000 張。

### Q2：如何判斷爬取的圖片質量？

**A**：檢查 `data/crawled/<角色名>/` 目錄，手動查看圖片。刪除低質量圖片（模糊、錯誤角色、不含角色等）。

### Q3：訓練需要多長時間？

**A**：取決於數據量和硬體。典型配置：
- 數據量：10,000 張圖片
- 硬體：GPU (NVIDIA GTX 1660 或更好）
- 時間：約 30-60 分鐘（15 epochs）

### Q4：可以同時在多台設備上爬取嗎？

**A**：可以，但需要修改腳本以支持分布式爬取（避免重複爬取同一個角色）。

---

## 聯系方式

如果遇到問題，請提供以下信息：
- 錯誤日誌（完整的錯誤信息）
- 配置文件內容（`config.py`, `config/characters_to_crawl.json`）
- 系統信息（操作系統，Python 版本，GPU 型號）

---

**最後更新**：2026-06-22
**作者**：AnimeID 開發團隊
