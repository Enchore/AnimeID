#!/usr/bin/env python3
"""檢查資料庫中所有記錄的 zh-TW 值"""

import sqlite3
import json

db_path = r"F:\Projects\AnimeID\anime-recognition-system\anime_system.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("""
    SELECT id, top5_results, all_characters 
    FROM recognition_records 
    WHERE top5_results IS NOT NULL
""")

rows = cursor.fetchall()
print(f'總共 {len(rows)} 筆記錄')
print('=' * 80)

for record_id, top5_str, all_char_str in rows:
    top5_results = json.loads(top5_str) if top5_str else []
    
    print(f'\n記錄 ID: {record_id}')
    print('-' * 80)
    
    # 檢查 top5_results 中的 zh-TW
    if top5_results and isinstance(top5_results, list):
        for i, item in enumerate(top5_results[:1]):  # 只顯示第一個（主要角色）
            if isinstance(item, dict):
                char_name = item.get('name', '')
                name_i18n = item.get('name_i18n', {})
                
                if isinstance(name_i18n, dict):
                    zh_tw = name_i18n.get('zh-TW', '(無)')
                    zh_cn = name_i18n.get('zh-CN', '')
                    
                    print(f'  角色: {char_name}')
                    print(f'  zh-CN: {zh_cn}')
                    print(f'  zh-TW: {zh_tw}')
                    
                    # 檢查是否可能不正確
                    if zh_tw != '(無)' and zh_tw == zh_cn:
                        print(f'  ⚠️  警告: zh-TW 與 zh-CN 相同（可能未轉換）')
                else:
                    print(f'  角色: {char_name}')
                    print(f'  name_i18n 格式錯誤: {name_i18n}')
    
    # 檢查 all_characters 中的 zh-TW
    if all_char_str:
        all_characters = json.loads(all_char_str)
        if all_characters and isinstance(all_characters, list):
            print(f'  多角色記錄: {len(all_characters)} 個角色')
            for char in all_characters[:2]:  # 只顯示前2個
                if isinstance(char, dict):
                    char_name = char.get('name', '')
                    name_i18n = char.get('name_i18n', {})
                    if isinstance(name_i18n, dict):
                        zh_tw = name_i18n.get('zh-TW', '(無)')
                        print(f'    - {char_name}: zh-TW={zh_tw}')

conn.close()
