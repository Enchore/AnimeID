import json, os

base = r"F:\Projects\AnimeID\anime-recognition-system\module3_web\static\i18n"

history_keys = {
    "history.title": {
        "zh-TW": "識別記錄",
        "zh-CN": "识别记录",
        "en": "Recognition History",
        "ja": "Recognition History",
        "ko": "Recognition History",
        "fr": "Recognition History",
        "es": "Recognition History",
        "vi": "Recognition History",
        "th": "Recognition History",
    },
    "history.subtitle_before": {
        "zh-TW": "所有識別歷史（含非動漫圖片），共 ",
        "zh-CN": "所有识别历史（含非动漫图片），共 ",
        "en": "All recognition history (including non-anime), total ",
        "ja": "All recognition history (including non-anime), total ",
        "ko": "All recognition history (including non-anime), total ",
        "fr": "All recognition history (including non-anime), total ",
        "es": "All recognition history (including non-anime), total ",
        "vi": "All recognition history (including non-anime), total ",
        "th": "All recognition history (including non-anime), total ",
    },
    "history.subtitle_after": {
        "zh-TW": " 條",
        "zh-CN": " 条",
        "en": " records",
        "ja": " records",
        "ko": " records",
        "fr": " records",
        "es": " records",
        "vi": " records",
        "th": " records",
    },
    "history.not_anime": {
        "zh-TW": "非動漫",
        "zh-CN": "非动漫",
        "en": "Not Anime",
        "ja": "Not Anime",
        "ko": "Not Anime",
        "fr": "Not Anime",
        "es": "Not Anime",
        "vi": "Not Anime",
        "th": "Not Anime",
    },
    "history.source_qwen": {
        "zh-TW": "Qwen AI",
        "zh-CN": "Qwen AI",
        "en": "Qwen AI",
        "ja": "Qwen AI",
        "ko": "Qwen AI",
        "fr": "Qwen AI",
        "es": "Qwen AI",
        "vi": "Qwen AI",
        "th": "Qwen AI",
    },
    "history.source_local": {
        "zh-TW": "本地模型",
        "zh-CN": "本地模型",
        "en": "Local Model",
        "ja": "Local Model",
        "ko": "Local Model",
        "fr": "Local Model",
        "es": "Local Model",
        "vi": "Local Model",
        "th": "Local Model",
    },
    "history.empty_title": {
        "zh-TW": "暫無識別記錄",
        "zh-CN": "暂无识别记录",
        "en": "No Records Yet",
        "ja": "No Records Yet",
        "ko": "No Records Yet",
        "fr": "No Records Yet",
        "es": "No Records Yet",
        "vi": "No Records Yet",
        "th": "No Records Yet",
    },
    "history.empty_desc": {
        "zh-TW": "快去上傳第一張圖片開始識別吧！",
        "zh-CN": "快去上传第一张图片开始识别吧！",
        "en": "Upload your first image to start recognizing!",
        "ja": "Upload your first image to start recognizing!",
        "ko": "Upload your first image to start recognizing!",
        "fr": "Upload your first image to start recognizing!",
        "es": "Upload your first image to start recognizing!",
        "vi": "Upload your first image to start recognizing!",
        "th": "Upload your first image to start recognizing!",
    },
}

for lang in ["zh-TW", "zh-CN", "en", "ja", "ko", "fr", "es", "vi", "th"]:
    fp = os.path.join(base, f"{lang}.json")
    with open(fp, "r", encoding="utf-8") as f:
        data = json.load(f)
    added = 0
    for key, trans in history_keys.items():
        if key not in data:
            data[key] = trans[lang]
            added += 1
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")
    print(f"[OK] {lang}.json — 新增 {added} 個鍵")

print("\n全部完成！")
