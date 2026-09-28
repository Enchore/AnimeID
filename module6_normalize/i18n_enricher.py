"""
i18n_enricher.py - i18n データ補完モジュール

機能：
- データベース中に不足している name_i18n / anime_i18n の認識記録をスキャン
- 既知のキャラクター：ANIME_CHARACTERS から多言語名を直接読み取り
- 新しいキャラクター（Qwen 発見）：Bangumi API → AniList API → LLM 翻訳で検索・補完
- バッチ処理と定期タスクをサポート

データソースの優先順位：
1. Bangumi API (bgm.tv) - 中国語アニメデータベース、データが最も完全
2. AniList API - 英語/日本語データ
3. LLM 翻訳 - フォールバック案
"""

import json
import os
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# サポートしている言語リスト（locale_utils.py と一致）
SUPPORTED_LOCALES = ["zh-CN", "zh-TW", "en", "ja", "ko", "fr", "es", "vi", "th"]

# ===== Qwen API 設定（qwen_recognizer.py の設定を再利用）=====
# 金鑰從環境變數讀取，禁止寫入程式碼（本倉庫為公開倉庫）。
# 設置方式：export DASHSCOPE_API_KEY=sk-xxxx
QWEN_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
QWEN_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
QWEN_TEXT_MODEL = "qwen-plus"  # テキストモデル（翻訳用、qwen-vl-max より安い）


def translate_with_qwen(text: str, text_type: str = "character") -> Optional[Dict[str, str]]:
    """
     Qwen API を使用してキャラクター/アニメ名を多言語に翻訳
    
    Args:
        text: 中国語名（キャラクターまたはアニメ）
        text_type: "character" または "anime"
    
    Returns:
        {"zh-CN": "...", "zh-TW": "...", "ja": "...", ...} または None
    """
    if not text or not text.strip():
        return None
    
    try:
        from openai import OpenAI
        import httpx
        
        client = OpenAI(
            api_key=QWEN_API_KEY,
            base_url=QWEN_API_BASE,
            timeout=httpx.Timeout(30.0, connect=10.0),
        )
        
        if text_type == "character":
            prompt = f"""以下のアニメキャラクター名を多言語に翻訳し、厳密な JSON 形式で返してください（markdown コードブロックは追加しないでください）：

キャラクター名：{text}

以下の言語を含む JSON を返してください：
- "zh-CN": 簡体字中国語（変更なし）
- "zh-TW": 繁体字中国語（台湾用語）
- "ja": 日本語原名
- "en": 英語訳名
- "ko": 韓国語訳名
- "fr": フランス語訳名
- "es": スペイン語訳名
- "vi": ベトナム語訳名
- "th": タイ語訳名

入力例："漩涡鸣人"
出力例：{{"zh-CN": "漩涡鸣人", "zh-TW": "漩渦鳴人", "ja": "うずまきナルト", "en": "Naruto Uzumaki", "ko": "나루토 우즈마키", "fr": "Naruto Uzumaki", "es": "Naruto Uzumaki", "vi": "Naruto Uzumaki", "th": "นารูโตะ อุซึมากิ"}}"""
        else:  # anime
            prompt = f"""以下のアニメ作品名を多言語に翻訳し、厳密な JSON 形式で返してください（markdown コードブロックは追加しないでください）：

作品名：{text}

以下の言語を含む JSON を返してください：
- "zh-CN": 簡体字中国語（変更なし）
- "zh-TW": 繁体字中国語（台湾用語）
- "ja": 日本語原名
- "en": 英語訳名
- "ko": 韓国語訳名
- "fr": フランス語訳名
- "es": スペイン語訳名
- "vi": ベトナム語訳名
- "th": タイ語訳名

入力例："火影忍者"
出力例：{{"zh-CN": "火影忍者", "zh-TW": "火影忍者", "ja": "NARUTO -ナルト-", "en": "Naruto", "ko": "나루토", "fr": "Naruto", "es": "Naruto", "vi": "Naruto", "th": "นารูโตะ"}}"""
        
        response = client.chat.completions.create(
            model=QWEN_TEXT_MODEL,
            messages=[
                {"role": "system", "content": "あなたはプロのアニメキャラクターと作品名翻訳アシスタントです。厳密な JSON 形式で返し、markdown コードブロックを追加しないでください。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
        )
        
        result = response.choices[0].message.content
        
        # JSON を解析（純粋なテキストまたは markdown コードブロックの可能性があります）
        import json
        import re
        
        result = result.strip()
        
        # 可能性のある markdown コードブロックを削除
        if result.startswith("```"):
            # コードブロック内容を抽出
            lines = result.split("\n")
            # 最初の ``` と最後の ``` を見つける
            start_idx = 0
            end_idx = len(lines)
            for i, line in enumerate(lines):
                if line.startswith("```"):
                    if start_idx == 0:
                        start_idx = i + 1
                    else:
                        end_idx = i
                        break
            result = "\n".join(lines[start_idx:end_idx]).strip()
        
        # JSON を解析試行
        try:
            i18n_dict = json.loads(result)
        except json.JSONDecodeError:
            # テキストから JSON を抽出試行
            json_match = re.search(r'\{[^{}]*\{?[^{}]*\}?[^{}]*\}', result, re.DOTALL)
            if json_match:
                try:
                    i18n_dict = json.loads(json_match.group())
                except json.JSONDecodeError:
                    logger.error(f"[i18n補完] Qwen が返した JSON の解析に失敗しました: {result[:200]}")
                    return None
            else:
                logger.error(f"[i18n補完] Qwen が返した形式が間違っています: {result[:200]}")
                return None
        
        # 検証して返す
        if i18n_dict and isinstance(i18n_dict, dict):
            # zh-CN が少なくともあることを確認
            if "zh-CN" not in i18n_dict:
                i18n_dict["zh-CN"] = text
            logger.info(f"[i18n補完] Qwen 翻訳成功: '{text}' → {list(i18n_dict.keys())}")
            return i18n_dict
        else:
            return None
        
    except Exception as e:
        logger.error(f"[i18n補完] Qwen 翻訳失敗 '{text}': {e}")
        return None


def _build_i18n_dict(char_key_or_name: str, is_known_character: bool) -> Optional[Dict[str, str]]:
    """
    i18n 辞書を構築
    
    Args:
        char_key_or_name: キャラクターキー（既知キャラクター）またはキャラクター名（新しいキャラクター）
        is_known_character: ANIME_CHARACTERS 内に存在する既知キャラクターかどうか
    
    Returns:
        {"zh-CN": "...", "zh-TW": "...", ...} または None
    """
    if is_known_character:
        # 既知キャラクター：ANIME_CHARACTERS から直接読み取り
        try:
            from module3_web.app import ANIME_CHARACTERS
            if char_key_or_name in ANIME_CHARACTERS:
                return ANIME_CHARACTERS[char_key_or_name]["name"]
        except Exception as e:
            logger.error(f"[i18n補完] ANIME_CHARACTERS の読み取りに失敗: {e}")
    else:
        # 新しいキャラクター：TODO - AniList API 検索を使用
        # 暫定的に None を返し、後で実装
        pass
    
    return None


def _find_key_by_name(char_name: str) -> "str | None":
    """
    キャラクター名を使用して ANIME_CHARACTERS 内で一致するキーを直接検索
    
    検索範囲：name 辞書内のすべての言語の値 + character_key 自体
    照合方式：正確一致（大文字小文字を無視）
    
    Returns:
        一致するキーまたは None
    """
    if not char_name:
        return None
    try:
        from module3_web.app import ANIME_CHARACTERS
        name_lower = char_name.lower().strip()
        for key, data in ANIME_CHARACTERS.items():
            # character_key を照合
            if key.lower() == name_lower:
                return key
            # name 辞書内のすべての言語を照合
            name_dict = data.get("name", {})
            if isinstance(name_dict, dict):
                for locale, n in name_dict.items():
                    if n and n.lower() == name_lower:
                        return key
            # name 文字列を照合（古い形式との互換性）
            if isinstance(name_dict, str) and name_dict.lower() == name_lower:
                return key
    except Exception as e:
        logger.debug(f"[_find_key_by_name] 検索失敗: {e}")
    return None


def _find_char_key_in_db(char_key: str, char_name: str) -> Optional[str]:
    """
    ANIME_CHARACTERS 内で一致するキャラクターキーを検索
    
    一致戦略：
    1. char_key と正確一致
    2. 正規化後一致（括弧内を削除、小文字化、区切り文字を置換）
    3. キャラクター名で一致（すべての言語の名前と照合）
    
    Returns:
        一致するキーまたは None
    """
    try:
        from module3_web.app import ANIME_CHARACTERS
        
        # 戦略1：正確一致
        if char_key and char_key in ANIME_CHARACTERS:
            return char_key
        
        # 戦略2：正規化一致
        if char_key:
            # 括弧内内容を削除：rem_(re:zero) → rem_
            import re
            normalized = re.sub(r'\([^)]*\)', '', char_key)
            # 小文字化して区切り文字を置換
            normalized = normalized.lower().replace(' ', '_').replace('-', '_').strip('_')
            
            # 一致試行
            for key in ANIME_CHARACTERS.keys():
                key_norm = key.lower().replace(' ', '_').replace('-', '_').strip('_')
                if normalized == key_norm:
                    return key
        
        # 戦略3：名前で一致
        if char_name:
            for key, data in ANIME_CHARACTERS.items():
                name_dict = data.get("name", {})
                for locale, name in name_dict.items():
                    if char_name == name or char_name in name:
                        return key
        
    except Exception as e:
        logger.error(f"[i18n補完] キャラクターキー検索失敗: {e}")
    
    return None


def enrich_record_i18n(record, db_session, anilist_search: bool = True) -> bool:
    """
    単一記録の i18n データを補完
    
    Args:
        record: RecognitionRecord オブジェクト
        db_session: SQLAlchemy session
        anilist_search: 新しいキャラクターを検索するために AniList API を使用するかどうか
    
    Returns:
        bool: 補完が行われたかどうか
    """
    if not record.top5_results:
        return False
    
    try:
        top5 = json.loads(record.top5_results) if isinstance(record.top5_results, str) else record.top5_results
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"[i18n補完] 記録#{record.id} の top5_results 解析に失敗")
        return False
    
    if not top5:
        return False
    
    changed = False
    
    # top5_results 内の各記録を処理
    for item in top5:
        # 既に i18n データがあるかどうかを確認
        has_name_i18n = bool(item.get("name_i18n"))
        has_anime_i18n = bool(item.get("anime_i18n"))
        
        if has_name_i18n and has_anime_i18n:
            continue  # 既に完全な i18n データがある場合はスキップ
        
        # キャラクター識別情報を取得
        char_key = item.get("char_key") or record.top1_character_key
        char_name = item.get("name") or record.top1_character_name
        
        # ANIME_CHARACTERS 内で一致するキャラクターキーを検索
        matched_key = _find_char_key_in_db(char_key, char_name)
        is_known = matched_key is not None
        
        # name_i18n を補完
        if not has_name_i18n:
            if is_known and matched_key:
                # 既知キャラクター：キャラクターライブラリから直接読み取り
                try:
                    from module3_web.app import ANIME_CHARACTERS
                    item["name_i18n"] = ANIME_CHARACTERS[matched_key]["name"]
                    changed = True
                    logger.info(f"[i18n補完] 記録#{record.id} name_i18n 補完 (既知キャラクター: {matched_key})")
                except Exception as e:
                    logger.error(f"[i18n補完] 記録#{record.id} name_i18n 読み取り失敗: {e}")
            elif anilist_search:
                # 新しいキャラクター：AniList API を使用して検索
                try:
                    name_i18n = search_character_i18n_anilist(char_name, item.get("anime"))
                    if name_i18n:
                        # 【新規追加】Wikipedia で zh-TW（台湾訳名）を補完/上書き
                        if char_name:
                            try:
                                wiki_i18n = search_character_i18n_wikipedia(char_name)
                                if wiki_i18n and "zh-TW" in wiki_i18n:
                                    # Wikipedia で台湾訳名が見つかった場合は上書き（優先使用）
                                    old_zh_tw = name_i18n.get("zh-TW", "")
                                    name_i18n["zh-TW"] = wiki_i18n["zh-TW"]
                                    if old_zh_tw != wiki_i18n["zh-TW"]:
                                        logger.info(f"[i18n補完] Wikipedia で zh-TW を上書き: {char_name} → {wiki_i18n['zh-TW']}")
                            except Exception as e:
                                logger.debug(f"[i18n補完] Wikipedia 検索失敗 '{char_name}': {e}")
                        
                        item["name_i18n"] = name_i18n
                        changed = True
                        logger.info(f"[i18n補完] 記録#{record.id} name_i18n 補完 (AniList: {char_name})")
                except Exception as e:
                    logger.error(f"[i18n補完] 記録#{record.id} AniList 検索失敗: {e}")
        
        # anime_i18n を補完
        if not has_anime_i18n:
            if is_known and matched_key:
                # 既知キャラクター：キャラクターライブラリから直接読み取り
                try:
                    from module3_web.app import ANIME_CHARACTERS
                    item["anime_i18n"] = ANIME_CHARACTERS[matched_key]["anime"]
                    changed = True
                    logger.info(f"[i18n補完] 記録#{record.id} anime_i18n 補完 (既知キャラクター: {matched_key})")
                except Exception as e:
                    logger.error(f"[i18n補完] 記録#{record.id} anime_i18n 読み取り失敗: {e}")
            elif anilist_search:
                # 新しいアニメ：AniList API を使用して検索
                try:
                    anime_i18n = search_anime_i18n_anilist(item.get("anime", ""))
                    if anime_i18n:
                        item["anime_i18n"] = anime_i18n
                        changed = True
                        logger.info(f"[i18n補完] 記録#{record.id} anime_i18n 補完 (AniList: {item.get('anime')})")
                except Exception as e:
                    logger.error(f"[i18n補完] 記録#{record.id} AniList アニメ検索失敗: {e}")
    
    # 変更があった場合はデータベースに保存
    if changed:
        record.top5_results = json.dumps(top5, ensure_ascii=False)
        if db_session:
            db_session.commit()
        return True
    
    return False


def _enrich_all_characters_i18n(record, db_session) -> bool:
    """
    単一記録の all_characters JSON 内の i18n データを補完
    
    ロジック：
    1. all_characters 内の各キャラクターを反復処理
    2. ANIME_CHARACTERS から読み取り試行（既知キャラクター）
    3. 同じ記録の top5_results から同名キャラクターを一致させて i18n をコピー（Qwen が既に識別済み）
    4. Bangumi/AniList API 検索試行（新しいキャラクター）
    
    Returns:
        bool: 変更があったかどうか
    """
    if not record.all_characters:
        return False
    
    try:
        all_chars = json.loads(record.all_characters) if isinstance(record.all_characters, str) else record.all_characters
        top5 = json.loads(record.top5_results) if isinstance(record.top5_results, str) else (record.top5_results or [])
    except (json.JSONDecodeError, TypeError):
        return False
    
    if not isinstance(all_chars, list) or len(all_chars) == 0:
        return False
    
    changed = False
    
    for char in all_chars:
        if not isinstance(char, dict):
            continue
        if char.get("name_i18n") and char.get("anime_i18n"):
            continue  # 既に完全な i18n がある場合はスキップ
        
        char_name = char.get("name", "")
        char_anime = char.get("anime", "")
        char_key = char.get("character_key", "")
        
        name_i18n = None
        anime_i18n = None
        
        # 戦略1：ANIME_CHARACTERS から読み取り（既知キャラクター）
        # 最初に character_key で一致試行
        matched_key = _find_char_key_in_db(char_key, char_name)
        # character_key が中国語名の場合（正しいキーではない）、キャラクター名で一致させる
        if not matched_key and char_name:
            matched_key = _find_key_by_name(char_name)
        if matched_key:
            try:
                from module3_web.app import ANIME_CHARACTERS
                name_i18n = name_i18n or ANIME_CHARACTERS[matched_key].get("name", {})
                anime_i18n = anime_i18n or ANIME_CHARACTERS[matched_key].get("anime", {})
            except Exception:
                pass
        
        # 戦略2：同じ記録の top5_results から一致して i18n をコピー
        if not name_i18n or not anime_i18n:
            for item in (top5 or []):
                if not isinstance(item, dict):
                    continue
                item_name = item.get("name", "")
                item_key = item.get("character_key", "")
                # 一致：名前が同じまたは character_key が同じ
                if (item_name and item_name == char_name) or (item_key and item_key == char_key):
                    if not name_i18n and item.get("name_i18n"):
                        name_i18n = item["name_i18n"]
                    if not anime_i18n and item.get("anime_i18n"):
                        anime_i18n = item["anime_i18n"]
                    break
        
        # 戦略3：Bangumi API（新しいキャラクター）
        if not name_i18n and char_name:
            name_i18n = search_character_i18n_bangumi(char_name, char_anime)
        if not anime_i18n and char_anime:
            anime_i18n = search_anime_i18n_bangumi(char_anime)
        
        # 戦略4：AniList API（新しいキャラクター、英語/日本語）
        if not name_i18n and char_name:
            name_i18n = search_character_i18n_anilist(char_name, char_anime)
        
        # 書き込み
        if name_i18n and not char.get("name_i18n"):
            char["name_i18n"] = name_i18n
            changed = True
        if anime_i18n and not char.get("anime_i18n"):
            char["anime_i18n"] = anime_i18n
            changed = True
    
    if changed:
        record.all_characters = json.dumps(all_chars, ensure_ascii=False)
        if db_session:
            db_session.commit()
        logger.info(f"[i18n補完] 記録#{record.id} ですでに all_characters i18n データを補完")
        return True
    
    return False


def enrich_record_i18n_multi_source(record, db_session=None, use_bangumi: bool = True, 
                                    use_anilist: bool = True, use_llm: bool = False) -> bool:
    """
    複数のデータソースを使用して単一記録の i18n データを補完
    
    データソース優先順位：
    1. Bangumi API（中国語データが最も完全）
    2. AniList API（英語/日本語データ）
    3. LLM 翻訳（フォールバック）
    
    Args:
        record: RecognitionRecord オブジェクト
        db_session: SQLAlchemy session
        use_bangumi: Bangumi API を使用するかどうか
        use_anilist: AniList API を使用するかどうか
        use_llm: LLM 翻訳を使用するかどうか（遅い、デフォルトは無効）
    
    Returns:
        bool: 補完が行われたかどうか
    """
    if not record.top5_results:
        return False
    
    # 【最適化】高速チェック：すべての item に既に完全な i18n がある場合は直接スキップ
    try:
        top5_check = json.loads(record.top5_results) if isinstance(record.top5_results, str) else record.top5_results
        if top5_check and isinstance(top5_check, list):
            all_complete = True
            for item in top5_check:
                if not isinstance(item, dict):
                    all_complete = False
                    break
                if not item.get("name_i18n") or not item.get("anime_i18n"):
                    all_complete = False
                    break
            
            if all_complete:
                logger.debug(f"[i18n補完] 記録#{record.id} は既に完全な i18n があります、スキップ")
                # top5 が完全でも、all_characters をまだチェック
                _enrich_all_characters_i18n(record, db_session)
                return False
    except (json.JSONDecodeError, TypeError):
        pass  # 解析失敗、正常なフローを継続
    
    try:
        top5 = json.loads(record.top5_results) if isinstance(record.top5_results, str) else record.top5_results
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"[i18n補完] 記録#{record.id} の top5_results 解析に失敗")
        return False
    
    if not top5:
        return False
    
    changed = False
    
    for item in top5:
        has_name_i18n = bool(item.get("name_i18n"))
        has_anime_i18n = bool(item.get("anime_i18n"))
        
        if has_name_i18n and has_anime_i18n:
            continue
        
        char_key = item.get("char_key") or record.top1_character_key
        char_name = item.get("name") or record.top1_character_name
        anime_name = item.get("anime") or record.top1_anime
        
        matched_key = _find_char_key_in_db(char_key, char_name)
        is_known = matched_key is not None
        
        # name_i18n を補完
        if not has_name_i18n:
            name_i18n = None
            
            if is_known and matched_key:
                # 既知キャラクター：キャラクターライブラリから直接読み取り
                try:
                    from module3_web.app import ANIME_CHARACTERS
                    name_i18n = ANIME_CHARACTERS[matched_key]["name"]
                except Exception as e:
                    logger.error(f"[i18n補完] ANIME_CHARACTERS の読み取りに失敗: {e}")
            else:
                # 新しいキャラクター：複数のデータソースを使用して検索
                if use_bangumi:
                    name_i18n = search_character_i18n_bangumi(char_name, anime_name)
                
                if not name_i18n and use_anilist:
                    name_i18n = search_character_i18n_anilist(char_name, anime_name)
                
                # 【無効化済み】LLM フォールバック——Qwen は幻覚/勝手な翻訳をするため、使用しない
                # if not name_i18n and use_llm:
                #     name_i18n = translate_with_qwen(char_name, text_type="character")
            
            if name_i18n:
                # Wikipedia で zh-TW（台湾訳名）を補完試行
                if "zh-TW" not in name_i18n and char_name:
                    try:
                        wiki_i18n = search_character_i18n_wikipedia(char_name)
                        if wiki_i18n and "zh-TW" in wiki_i18n:
                            name_i18n["zh-TW"] = wiki_i18n["zh-TW"]
                            logger.info(f"[i18n補完] Wikipedia で zh-TW を補完: {char_name} → {wiki_i18n['zh-TW']}")
                    except Exception as e:
                        logger.debug(f"[i18n補完] Wikipedia 検索失敗 '{char_name}': {e}")
                
                item["name_i18n"] = name_i18n
                changed = True
                logger.info(f"[i18n補完] 記録#{record.id} name_i18n 補完: {char_name}")
        
        # anime_i18n を補完
        if not has_anime_i18n and anime_name:
            anime_i18n = None
            
            if is_known and matched_key:
                # 既知キャラクター：キャラクターライブラリから直接読み取り
                try:
                    from module3_web.app import ANIME_CHARACTERS
                    anime_i18n = ANIME_CHARACTERS[matched_key]["anime"]
                except Exception as e:
                    logger.error(f"[i18n補完] ANIME_CHARACTERS の読み取りに失敗: {e}")
            else:
                # 新しいアニメ：複数のデータソースを使用して検索
                if use_bangumi:
                    anime_i18n = search_anime_i18n_bangumi(anime_name)
                
                if not anime_i18n and use_anilist:
                    anime_i18n = search_anime_i18n_anilist(anime_name)
                
                # 【無効化済み】LLM フォールバック——Qwen は幻覚/勝手な翻訳をするため、使用しない
                # if not anime_i18n and use_llm:
                #     anime_i18n = translate_with_qwen(anime_name, text_type="anime")
            
            if anime_i18n:
                item["anime_i18n"] = anime_i18n
                changed = True
                logger.info(f"[i18n補完] 記録#{record.id} anime_i18n 補完: {anime_name}")
    
    if changed:
        record.top5_results = json.dumps(top5, ensure_ascii=False)
        if db_session:
            db_session.commit()
    
    # all_characters も処理
    _enrich_all_characters_i18n(record, db_session)
    
    return changed


def enrich_all_missing_i18n(db_session, batch_size: int = 100, 
                             use_bangumi: bool = True, 
                             use_anilist: bool = True, 
                             use_llm: bool = False) -> dict:
    """
    すべての不足している i18n データの記録をバッチで補完
    
    データソース優先順位：
    1. Bangumi API（中国語データが最も完全）
    2. AniList API（英語/日本語データ）
    3. LLM 翻訳（フォールバック）
    
    Args:
        db_session: SQLAlchemy session
        batch_size: 每回処理する記録数
        use_bangumi: Bangumi API を使用するかどうか
        use_anilist: AniList API を使用するかどうか
        use_llm: LLM 翻訳を使用するかどうか
    
    Returns:
        {"scanned": int, "enriched": int, "details": [...]} 
    """
    from module3_web.app import RecognitionRecord
    
    scanned = 0
    enriched = 0
    details = []
    
    logger.info(f"[i18n補完] 不足している i18n データの記録のスキャンを開始... (bangumi={use_bangumi}, anilist={use_anilist}, llm={use_llm})")
    
    offset = 0
    while True:
        records = db_session.query(RecognitionRecord) \
            .filter(RecognitionRecord.top5_results.isnot(None)) \
            .filter(RecognitionRecord.top5_results != "") \
            .order_by(RecognitionRecord.id) \
            .offset(offset) \
            .limit(batch_size) \
            .all()
        
        if not records:
            break
        
        for record in records:
            scanned += 1
            
            try:
                if enrich_record_i18n_multi_source(
                    record, db_session, 
                    use_bangumi=use_bangumi, 
                    use_anilist=use_anilist, 
                    use_llm=use_llm
                ):
                    enriched += 1
                    details.append({
                        "record_id": record.id,
                        "character": record.top1_character_name,
                        "source": "known" if _find_char_key_in_db(record.top1_character_key, record.top1_character_name) else "unknown"
                    })
            except Exception as e:
                logger.error(f"[i18n補完] 記録#{record.id} 処理失敗: {e}", exc_info=True)
        
        offset += batch_size
        logger.info(f"[i18n補完] スキャン済み {scanned} 件、補完 {enriched} 件")
    
    logger.info(f"[i18n補完] スキャン完了: {scanned} 件の記録、{enriched} 件を補完")
    
    return {
        "scanned": scanned,
        "enriched": enriched,
        "details": details
    }


def search_character_i18n_anilist(character_name: str, anime_name: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    AniList API を使用してキャラクターの多言語名を検索
    
    Args:
        character_name: キャラクター名（中国語または日本語）
        anime_name: アニメ名（オプション、正確な一致のために使用）
    
    Returns:
        {"zh-CN": "...", "en": "...", ...} または None
    
    Note:
        現在の実装は AniList の Character 検索 API を使用
        注意：AniList の search パラメータは中国語をサポートしていないため、中国語キャラクター名は自動的にスキップされます
    """
    import urllib.request
    import urllib.error
    
    if not character_name or not character_name.strip():
        return None
    
    # 中国語テキストかどうかを検出（AniList API は中国語検索をサポートしていない）
    if _is_chinese(character_name):
        logger.debug(f"[i18n補完] AniList は中国語キャラクター名をスキップ: '{character_name}'")
        return None
    
    # GraphQL クエリを構築（キャラクター検索）
    graphql_query = """
    query ($search: String) {
        Character(search: $search) {
            id
            name {
                first
                last
                native
                alternative
            }
        }
    }
    """
    
    variables = {"search": character_name.strip()}
    payload = json.dumps({
        "query": graphql_query,
        "variables": variables
    }).encode("utf-8")
    
    req = urllib.request.Request(
        "https://graphql.anilist.co",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AnimeID-i18n-Enricher/1.0"
        },
        method="POST"
    )
    
    try:
        # レート制限
        time.sleep(0.4)
        
        with urllib.request.urlopen(req, timeout=8) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            character = result.get("data", {}).get("Character")
            
            if character:
                name_obj = character.get("name", {})
                
                # i18n 辞書を構築
                i18n = {}
                
                # 英語（first + last）
                first = name_obj.get("first", "")
                last = name_obj.get("last", "")
                if first and last:
                    i18n["en"] = f"{first} {last}"
                elif first:
                    i18n["en"] = first
                
                # 日本語（native）
                if name_obj.get("native"):
                    i18n["ja"] = name_obj["native"]
                
                # 中国語（alternative から繁体字中国語を zh-TW として試行）
                alternatives = name_obj.get("alternative", []) or []
                for alt in alternatives:
                    if any('\u4e00' <= c <= '\u9fff' for c in alt):  # 中国語文字が含まれている
                        # 繁体字かどうかを確認（繁体字特徴文字が含まれているか、例：「淚」「裡」「餚」）
                        is_traditional = any(c in alt for c in '淚裡餚臺體會無氣關於係說話這進點發')
                        if is_traditional:
                            i18n["zh-TW"] = alt
                            if "zh-CN" not in i18n:
                                i18n["zh-CN"] = alt  # 暫定的、Bangumi で上書きされる
                        else:
                            i18n["zh-CN"] = alt
                            # Wikipedia で台湾訳名を検索試行
                            wiki_i18n = search_character_i18n_wikipedia(alt)
                            if wiki_i18n and "zh-TW" in wiki_i18n:
                                i18n["zh-TW"] = wiki_i18n["zh-TW"]
                        break
                
                # 中国語がない場合は、キャラクター名で中国語ウィキ/データベースを検索（TODO）
                
                logger.info(f"[i18n補完] AniList でキャラクターが見つかりました: '{character_name}' → {i18n}")
                return i18n if i18n else None
            else:
                logger.debug(f"[i18n補完] AniList ではキャラクターが見つかりません: '{character_name}'")
                return None
                
    except urllib.error.URLError as e:
        logger.warning(f"[i18n補完] AniList ネットワークエラー '{character_name}': {e}")
        return None
    except Exception as e:
        logger.warning(f"[i18n補完] AniList 照会エラー '{character_name}': {e}")
        return None


def search_anime_i18n_anilist(anime_name: str) -> Optional[Dict[str, str]]:
    """
    AniList API を使用してアニメの多言語名を検索
    
    Args:
        anime_name: アニメ名
    
    Returns:
        {"zh-CN": "...", "en": "...", ...} または None
    """
    # 【簡略化済み】AniList API は中国語アニメ名のサポートが不十分なため、直接使用 Bangumi API
    # この関数は暫定的に None を返し、呼び出し側に search_anime_i18n_bangumi() を使用させる
    logger.debug(f"[i18n補完] アニメ i18n 検索 (AniList) は未実装です: '{anime_name}'")
    return None


def search_character_i18n_bangumi(character_name: str, anime_name: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    Bangumi API を使用してキャラクターの多言語名を検索
    
    Bangumi (bgm.tv) は中国語アニメコミュニティで、キャラクターデータが最も完全
    API ドキュメント：https://github.com/bangumi/api
    
    Args:
        character_name: キャラクター名（中国語/日本語/英語）
        anime_name: アニメ名（オプション、正確な一致のために使用）
    
    Returns:
        {"zh-CN": "...", "zh-TW": "...", "ja": "...", "en": "..."} または None
    
    API エンドポイント：
        - アニメ検索：GET https://api.bgm.tv/search/subject/{keywords}?type=2
        - アニメからキャラクター取得：GET https://api.bgm.tv/subject/{id}/characters
        - キャラクター詳細：GET https://api.bgm.tv/character/{id}
    """
    import urllib.request
    import urllib.error
    import urllib.parse
    import socket
    
    if not character_name or not character_name.strip():
        return None
    
    # ネットワーク接続性事前チェック（高速失敗）
    try:
        # ドメイン名を解析試行（2秒を超えない）
        socket.setdefaulttimeout(2)
        urllib.request.urlopen("https://api.bgm.tv/", timeout=2)
    except Exception as e:
        logger.debug(f"[i18n補完] Bangumi API に到達できないため、スキップ: {e}")
        return None
    
    # Step 1: アニメ名がある場合は、アニメ経由でキャラクターを検索（より正確）
    if anime_name:
        return _search_character_via_anime_bangumi(character_name, anime_name)
    
    # Step 2: キャラクター名のみの場合は、直接検索試行（正確でない可能性があります）
    # 注意：Bangumi API v0 にはキャラクターを直接検索するエンドポイントがないため、この方法は失敗する可能性があります
    logger.debug(f"[i18n補完] Bangumi キャラクター検索（アニメ名なし）: '{character_name}'")
    return None  # 暫定的に None を返し、呼び出し側の降格ロジックに依存


def _search_character_via_anime_bangumi(character_name: str, anime_name: str) -> Optional[Dict[str, str]]:
    """
    アニメ経由でキャラクターを検索（Bangumi API）
    
    フロー：
    1. アニメ検索で subject_id を取得
    2. アニメ詳細を取得（キャラクターリストを含む）
    3. キャラクターリストから目標キャラクターを一致
    """
    import urllib.request
    import urllib.parse
    
    try:
        # Step 1: アニメ検索
        time.sleep(0.4)
        
        keyword = urllib.parse.quote(anime_name.strip())
        search_url = f"https://api.bgm.tv/search/subject/{keyword}?type=2&responseGroup=medium"
        
        req = urllib.request.Request(
            search_url,
            headers={
                "User-Agent": "AnimeID-i18n-Enricher/1.0",
                "Accept": "application/json"
            },
            method="GET"
        )
        
        with urllib.request.urlopen(req, timeout=8) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            subjects = result.get("list", [])
            
            if not subjects:
                logger.debug(f"[i18n補完] Bangumi でアニメが見つかりません: '{anime_name}'")
                return None
            
            # 最初に一致したアニメを取得
            subject_id = subjects[0].get("id")
            if not subject_id:
                return None
            
            # Step 2: アニメ詳細を取得（キャラクターを含む）
            time.sleep(0.4)
            
            detail_url = f"https://api.bgm.tv/v0/subjects/{subject_id}?responseGroup=medium"
            req2 = urllib.request.Request(
                detail_url,
                headers={
                    "User-Agent": "AnimeID-i18n-Enricher/1.0",
                    "Accept": "application/json"
                },
                method="GET"
            )
            
            with urllib.request.urlopen(req2, timeout=8) as resp2:
                subject_detail = json.loads(resp2.read().decode("utf-8"))
                
                # キャラクターリストを取得（別途 characters エンドポイントが必要）
                return _fetch_characters_from_subject_bangumi(subject_id, character_name)
                
    except Exception as e:
        logger.warning(f"[i18n補完] Bangumi アニメ経由キャラクター検索失敗: {e}")
        return None


def _fetch_characters_from_subject_bangumi(subject_id: int, target_character: str) -> Optional[Dict[str, str]]:
    """
    アニメからキャラクター情報を取得（Bangumi API v0）
    
    API: GET /v0/subjects/{subject_id}/characters
    """
    import urllib.request
    
    try:
        time.sleep(0.4)
        
        url = f"https://api.bgm.tv/v0/subjects/{subject_id}/characters"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "AnimeID-i18n-Enricher/1.0",
                "Accept": "application/json"
            },
            method="GET"
        )
        
        with urllib.request.urlopen(req, timeout=8) as resp:
            characters = json.loads(resp.read().decode("utf-8"))
            
            # characters は配列、各要素は character オブジェクトを含む
            for item in (characters or []):
                char = item.get("character", {})
                name = char.get("name", "")
                name_cn = char.get("name_cn", "")
                
                # キャラクター名を一致（中国語/日本語/英語をサポート）
                if _match_character_name(name, name_cn, target_character):
                    # i18n 辞書を構築
                    i18n = {}
                    
                    if name_cn:
                        i18n["zh-CN"] = name_cn
                        # zh-TW は name_cn（簡体字）を直接使用せず、Wikipedia/AniList で補完予定
                    
                    # 日本語名（name フィールドは日本語の可能性があります）
                    if _is_japanese(name):
                        i18n["ja"] = name
                    elif name and not _is_chinese(name):
                        i18n["en"] = name  # 英語の可能性があります
                    
                    # キャラクター詳細情報を取得
                    char_id = char.get("id")
                    if char_id:
                        detail = _get_bangumi_character_detail(char_id)
                        if detail:
                            i18n.update(detail)
                    
                    logger.info(f"[i18n補完] Bangumi でキャラクターが見つかりました: '{target_character}' → {i18n}")
                    return i18n if i18n else None
            
            logger.debug(f"[i18n補完] Bangumi アニメ#{subject_id} 内でキャラクターが見つかりません: '{target_character}'")
            return None
            
    except Exception as e:
        logger.warning(f"[i18n補完] Bangumi キャラクターリスト取得失敗: {e}")
        return None


def _get_bangumi_character_detail(character_id: int) -> Optional[Dict[str, str]]:
    """
    Bangumi キャラクター詳細情報を取得
    
    API: GET /v0/characters/{character_id}
    """
    import urllib.request
    
    try:
        time.sleep(0.4)
        
        url = f"https://api.bgm.tv/v0/characters/{character_id}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "AnimeID-i18n-Enricher/1.0",
                "Accept": "application/json"
            },
            method="GET"
        )
        
        with urllib.request.urlopen(req, timeout=8) as resp:
            detail = json.loads(resp.read().decode("utf-8"))
            
            i18n = {}
            name = detail.get("name", "")
            name_cn = detail.get("name_cn", "")
            
            if name_cn:
                i18n["zh-CN"] = name_cn
                # zh-TW は name_cn（簡体字）を直接使用せず、Wikipedia/AniList で補完予定
            if name and not _is_chinese(name):
                if _is_japanese(name):
                    i18n["ja"] = name
                else:
                    i18n["en"] = name
            
            return i18n if i18n else None
            
    except Exception as e:
        logger.debug(f"[i18n補完] Bangumi キャラクター詳細取得失敗 (char#{character_id}): {e}")
        return None


def search_anime_i18n_bangumi(anime_name: str) -> Optional[Dict[str, str]]:
    """
    Bangumi API を使用してアニメの多言語名を検索
    
    Args:
        anime_name: アニメ名
    
    Returns:
        {"zh-CN": "...", "zh-TW": "...", "ja": "...", "en": "..."} または None
    """
    import urllib.request
    import urllib.parse
    
    if not anime_name or not anime_name.strip():
        return None
    
    try:
        time.sleep(0.4)
        
        keyword = urllib.parse.quote(anime_name.strip())
        search_url = f"https://api.bgm.tv/search/subject/{keyword}?type=2&responseGroup=medium"
        
        req = urllib.request.Request(
            search_url,
            headers={
                "User-Agent": "AnimeID-i18n-Enricher/1.0",
                "Accept": "application/json"
            },
            method="GET"
        )
        
        with urllib.request.urlopen(req, timeout=8) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            subjects = result.get("list", [])
            
            if not subjects:
                logger.debug(f"[i18n補完] Bangumi でアニメが見つかりません: '{anime_name}'")
                return None
            
            # 最初に一致したアニメを取得
            subject = subjects[0]
            
            i18n = {}
            name_cn = subject.get("name_cn", "")
            name = subject.get("name", "")
            
            if name_cn:
                i18n["zh-CN"] = name_cn
                # zh-TW は name_cn（簡体字）を直接使用せず、Wikipedia/AniList で補完予定
            
            # 詳細情報を取得して日本語名を取得
            subject_id = subject.get("id")
            if subject_id:
                detail = _get_bangumi_subject_detail(subject_id)
                if detail:
                    i18n.update(detail)
            
            # 日本語/英語が取得できなかった場合は、検索結果の name を使用
            if name and "ja" not in i18n and "en" not in i18n:
                if _is_japanese(name):
                    i18n["ja"] = name
                else:
                    i18n["en"] = name
            
            logger.info(f"[i18n補完] Bangumi でアニメが見つかりました: '{anime_name}' → {i18n}")
            return i18n if i18n else None
            
    except Exception as e:
        logger.warning(f"[i18n補完] Bangumi アニメ検索失敗 '{anime_name}': {e}")
        return None


def _get_bangumi_subject_detail(subject_id: int) -> Optional[Dict[str, str]]:
    """
    Bangumi アニメ詳細情報を取得
    
    API: GET /v0/subjects/{subject_id}
    """
    import urllib.request
    
    try:
        time.sleep(0.4)
        
        url = f"https://api.bgm.tv/v0/subjects/{subject_id}?responseGroup=medium"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "AnimeID-i18n-Enricher/1.0",
                "Accept": "application/json"
            },
            method="GET"
        )
        
        with urllib.request.urlopen(req, timeout=8) as resp:
            detail = json.loads(resp.read().decode("utf-8"))
            
            i18n = {}
            
            # 名前フィールド
            name = detail.get("name", "")
            name_cn = detail.get("name_cn", "")
            
            if name_cn and "zh-CN" not in i18n:
                i18n["zh-CN"] = name_cn
                # zh-TW は name_cn（簡体字）を直接使用せず、Wikipedia/AniList で補完予定
            
            # 日本語名は alt_name または name 内の可能性があります
            if name and _is_japanese(name):
                i18n["ja"] = name
            
            # 英語名は alt_name 内の英語部分
            alt_name = detail.get("alt_name", "")
            if alt_name and _is_english(alt_name):
                i18n["en"] = alt_name
            
            return i18n if i18n else None
            
    except Exception as e:
        logger.debug(f"[i18n補完] Bangumi アニメ詳細取得失敗 (subject#{subject_id}): {e}")
        return None


def _match_character_name(name: str, name_cn: str, target: str) -> bool:
    """
    キャラクター名を一致（複数の言語をサポート）
    
    Returns:
        bool: 一致するかどうか
    """
    if not target:
        return False
    
    target_lower = target.lower()
    
    # 正確一致
    if name == target or name_cn == target:
        return True
    
    # 大文字小文字を無視して一致
    if name.lower() == target_lower or (name_cn and name_cn.lower() == target_lower):
        return True
    
    # 部分一致（目標名がキャラクター名に含まれている）
    if target in name or target in name_cn:
        return True
    
    return False


def search_character_i18n_wikipedia(character_name: str) -> Optional[Dict[str, str]]:
    """
    Wikipedia API を使用してキャラクターの台湾訳名（zh-TW）を検索
    
    戦略：
    1. キャラクター名で Wikipedia ページを検索
    2. ?action=render&variant=zh-tw を使用して繁体字中国語ページを取得
    3. ページタイトルまたは最初の行から台湾訳名を抽出
    
    API：
    - 検索：GET https://zh.wikipedia.org/w/api.php?action=query&list=search&srsearch=...
    - ページ内容：GET https://zh.wikipedia.org/w/api.php?action=parse&page=...&prop=wikitext&format=json
    - 台湾訳名：GET https://zh.wikipedia.org/w/api.php?action=parse&page=...&prop=displaytitle&variant=zh-tw
    
    Returns:
        {"zh-TW": "台湾訳名"} または None
    """
    import urllib.request
    import urllib.parse
    import re
    
    if not character_name or not character_name.strip():
        return None
    
    # 可能性のある余分な説明を削除（例：「佐天淚子（某科学的超電磁砲）」）
    clean_name = character_name.strip()
    
    try:
        # Step 1: Wikipedia を検索
        time.sleep(0.5)
        
        search_keyword = urllib.parse.quote(clean_name)
        search_url = (
            f"https://zh.wikipedia.org/w/api.php"
            f"?action=query&list=search&srsearch={search_keyword}"
            f"&srlimit=3&format=json&srwhat=text"
        )
        
        req = urllib.request.Request(
            search_url,
            headers={"User-Agent": "AnimeID-i18n-Enricher/1.0"}
        )
        
        with urllib.request.urlopen(req, timeout=8) as resp:
            search_result = json.loads(resp.read().decode("utf-8"))
            search_results = search_result.get("query", {}).get("search", [])
            
            if not search_results:
                logger.debug(f"[i18n補完] Wikipedia でキャラクターが見つかりません: '{clean_name}'")
                return None
            
            # 最初の検索結果のページタイトルを取得
            page_title = search_results[0].get("title", "")
            if not page_title:
                return None
            
            logger.debug(f"[i18n補完] Wikipedia でページが見つかりました: '{clean_name}' → '{page_title}'")
        
        # Step 2: 台湾訳名を取得（variant=zh-tw）
        time.sleep(0.5)
        
        title_encoded = urllib.parse.quote(page_title)
        parse_url = (
            f"https://zh.wikipedia.org/w/api.php"
            f"?action=parse&page={title_encoded}"
            f"&prop=displaytitle&variant=zh-tw&format=json"
        )
        
        req2 = urllib.request.Request(
            parse_url,
            headers={"User-Agent": "AnimeID-i18n-Enricher/1.0"}
        )
        
        with urllib.request.urlopen(req2, timeout=8) as resp2:
            parse_result = json.loads(resp2.read().decode("utf-8"))
            display_title = parse_result.get("parse", {}).get("displaytitle", "")
            
            # HTML タグをクリーンアップ（例：<span lang="zh-Hant-TW">...</span>）
            if display_title:
                # すべての HTML タグを削除
                display_title = re.sub(r'<[^>]+>', '', display_title).strip()
            
            if display_title and _is_chinese(display_title):
                # 繁体字であることを確認（繁体字特徴がある）
                i18n = {"zh-TW": display_title}
                logger.info(f"[i18n補完] Wikipedia で台湾訳名が見つかりました: '{clean_name}' → zh-TW='{display_title}'")
                return i18n
        
        # Step 3: フォールバック——ページ内容から直接中国語名を検索
        time.sleep(0.5)
        
        parse_url2 = (
            f"https://zh.wikipedia.org/w/api.php"
            f"?action=parse&page={title_encoded}"
            f"&prop=wikitext&format=json&section=0"
        )
        
        req3 = urllib.request.Request(
            parse_url2,
            headers={"User-Agent": "AnimeID-i18n-Enricher/1.0"}
        )
        
        with urllib.request.urlopen(req3, timeout=8) as resp3:
            parse_result2 = json.loads(resp3.read().decode("utf-8"))
            wikitext = parse_result2.get("parse", {}).get("wikitext", {}).get("*", "")
            
            if wikitext:
                # Wikitext 最初の行から中国語名を抽出（通常は {{Infobox}} の | 中文名 = または | 名前 = ）
                name_match = re.search(r'\|(中文名|名前|キャラクター名|本名)\s*=\s*([^\|\n]+)', wikitext)
                if name_match:
                    candidate = name_match.group(2).strip()
                    if _is_chinese(candidate) and len(candidate) < 20:
                        i18n = {"zh-TW": candidate}
                        logger.info(f"[i18n補完] Wikipedia で Wikitext から訳名を抽出: '{clean_name}' → '{candidate}'")
                        return i18n
        
        logger.debug(f"[i18n補完] Wikipedia で台湾訳名を取得できません: '{clean_name}'")
        return None
        
    except Exception as e:
        logger.debug(f"[i18n補完] Wikipedia 検索失敗 '{clean_name}': {e}")
        return None


def _is_chinese(text: str) -> bool:
    """テキストに中国語文字が含まれているかどうかを判定"""
    if not text:
        return False
    return any('\u4e00' <= c <= '\u9fff' for c in text)


def _is_japanese(text: str) -> bool:
    """テキストに日本語文字が含まれているかどうかを判定"""
    if not text:
        return False
    # ひらがな + カタカナ + 漢字
    return any(
        ('\u3040' <= c <= '\u309f') or  # ひらがな
        ('\u30a0' <= c <= '\u30ff') or  # カタカナ
        ('\u4e00' <= c <= '\u9fff')     # 漢字（中国語にも使用可能）
        for c in text
    )


def _is_english(text: str) -> bool:
    """テキストが英語かどうかを判定"""
    if not text:
        return False
    # ASCII 文字、数字、スペース、句読点のみ含む
    return all(ord(c) < 128 for c in text if c.isalnum() or c in ' -_.,&()\'"')
