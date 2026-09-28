import sqlite3
import json
import os

db_path = r"F:\Projects\AnimeID\anime-recognition-system\anime_system.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 檢查有 name_i18n 的記錄
cursor.execute('SELECT id, name, name_i18n FROM recognition_records WHERE name_i18n IS NOT NULL LIMIT 10')
rows = cursor.fetchall()

print('=== 現有記錄的 name_i18n 內容（前10筆）===' )
needs_fix = []
for row in rows:
    record_id, name, name_i18n_str = row
    try:
        name_i18n = json.loads(name_i18n_str)
        zh_tw = name_i18n.get('zh-TW', '(無)')
        zh_cn = name_i18n.get('zh-CN', '(無)')
        print(f'ID {record_id}: {name}')
        print(f'  zh-CN: {zh_cn}')
        print(f'  zh-TW: {zh_tw}')
        
        # 檢查 zh-TW 是否等於 zh-CN（表示是簡體中文）
        if zh_tw != '(無)' and zh_cn != '(無)' and zh_tw == zh_cn:
            print(f'  ⚠️  zh-TW 與 zh-CN 相同（可能是簡體中文，需要修復）')
            needs_fix.append(record_id)
        elif zh_tw == '(無)':
            print(f'  ⚠️  zh-TW 為空（需要補全）')
            needs_fix.append(record_id)
        print()
    except Exception as e:
        print(f'ID {record_id}: JSON 解析失敗: {e}')
        print()

# 統計
cursor.execute('SELECT COUNT(*) FROM recognition_records WHERE name_i18n IS NOT NULL')
total = cursor.fetchone()[0]

cursor.execute('''
    SELECT COUNT(*) FROM recognition_records 
    WHERE name_i18n IS NOT NULL 
    AND json_extract(name_i18n, '$.zh-TW') IS NOT NULL
    AND json_extract(name_i18n, '$.zh-TW') != json_extract(name_i18n, '$.zh-CN')
''')
zh_tw_correct = cursor.fetchone()[0]

print(f'\n統計：')
print(f'  總共有 {total} 筆有 name_i18n')
print(f'  其中 zh-TW 與 zh-CN 不同的有 {zh_tw_correct} 筆')
print(f'  可能需要修復的有 {total - zh_tw_correct} 筆')

if needs_fix:
    print(f'\n前10筆中需要修復的 ID: {needs_fix}')

conn.close()
