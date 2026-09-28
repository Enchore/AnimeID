"""
添加缺失的常見角色到 config.py 的 ANIME_CHARACTERS
"""
import re

filepath = r"F:\Projects\AnimeID\anime-recognition-system\config.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 新角色定義
new_characters = '''
    # ===== 鬼滅之刃 / Demon Slayer =====
    "nezuko_kamado": {
        "name": {
            "zh-CN": "禰豆子", "zh-TW": "竈门祢豆子",
            "ja": "竈鬥子·竈門", "en": "Nezuko Kamado",
            "ko": "네즈코 카마도",
            "fr": "Nezuko Kamado", "es": "Nezuko Kamado",
            "vi": "Nezuko Kamado", "th": "เนะซุโกะ คามาโดะ",
        },
        "anime": {
            "zh-CN": "鬼滅之刃", "zh-TW": "鬼滅之刃",
            "ja": "鬼滅の刃", "en": "Demon Slayer",
            "ko": "귀멸의 칼날",
            "fr": "Demon Slayer", "es": "Demon Slayer",
            "vi": "Demon Slayer", "th": "ดேมอน สเลเยอร์",
        }
    },
    # ===== 東方Project =====
    "remilia_scarlet": {
        "name": {
            "zh-CN": "蕾米莉亞·斯卡雷特", "zh-TW": "蕾米莉亞·斯卡雷特",
            "ja": "レミリア·スカーレット", "en": "Remilia Scarlet",
            "ko": "레밀리아 스카렛",
            "fr": "Remilia Scarlet", "es": "Remilia Scarlet",
            "vi": "Remilia Scarlet", "th": "เรมิลี亚 สการ์เลต",
        },
        "anime": {
            "zh-CN": "東方Project", "zh-TW": "東方Project",
            "ja": "東方Project", "en": "Touhou Project",
            "ko": "동방Project",
            "fr": "Touhou Project", "es": "Touhou Project",
            "vi": "Touhou Project", "th": "โทโฮว Project",
        }
    },
    # ===== Re:從零開始的異世界生活 =====
    "beatrice_rezero": {
        "name": {
            "zh-CN": "貝蒂·布萊克貝爾", "zh-TW": "貝姬·布萊克貝爾",
            "ja": "ベアトリス", "en": "Beatrice",
            "ko": "베아트리체",
            "fr": "Beatrice", "es": "Beatrice",
            "vi": "Beatrice", "th": "เบอาทริซ",
        },
        "anime": {
            "zh-CN": "Re:從零開始的異世界生活", "zh-TW": "Re:從零開始的異世界生活",
            "ja": "Re:ゼロから始める異世界生活", "en": "Re:Zero",
            "ko": "Re:제로부터 시작하는 이세계 생활",
            "fr": "Re:Zero", "es": "Re:Zero",
            "vi": "Re:Zero", "th": "Re:Zero",
        }
    },
'''

# 找到 ANIME_CHARACTERS 字典的結束位置（最後一個 }）
# 策略：找到 "}" + 換行 + "# 支援的語言列表" 之前的位置
marker = '}\n\n# 支援的語言列表'
if marker in content:
    idx = content.index(marker)
    # 在 } 和 換行 之間插入新角色
    # 原來是：...},\n\n# 支援的語言列表
    # 修改後：...,\n{新角色}\n}\n\n# 支援的語言列表
    
    # 在 idx 之前插入（在最後一個 }, 之後插入新角色）
    # idx 是 } 的位置
    insert_pos = idx + 1  # 跳過 }
    
    # 檢查前一個字符是否是 ,
    if content[insert_pos] != ',':
        # 需要添加 ,
        content = content[:insert_pos] + ',' + content[insert_pos:]
        insert_pos += 1
    
    # 插入新角色
    content = content[:insert_pos] + '\n' + new_characters + '\n' + content[insert_pos:]
    
    print("✅ 已添加新角色到 ANIME_CHARACTERS:")
    print("  1. 禰豆子（竈门祢豆子）")
    print("  2. 蕾米莉亞（蕾米莉亚·斯卡雷特）")
    print("  3. 貝蒂（貝姬·布萊克貝爾）")
else:
    print("❌ 未找到標記，無法自動添加")
    print("請手動添加以下角色到 config.py 的 ANIME_CHARACTERS:")
    print(new_characters)

# 保存
with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("\n✅ config.py 已更新！")
print("\n請重啟 Flask 應用使更改生效。")
