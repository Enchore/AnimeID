"""
module2_model/qwen_recognizer.py - Qwen-VL 开放识别器
通过阿里百炼 DashScope API (OpenAI 兼容模式) 进行动漫角色开放识别

作为系统的主力识别器：自由识别任意动漫角色（不受已知角色库限制），
本地模型仅作为已知角色的验证和兜底。
"""
import os
import sys
import json
import re
import base64
import logging
from pathlib import Path
from openai import OpenAI
import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ANIME_CHARACTERS

logger = logging.getLogger(__name__)

# ===== API 配置 =====
# 金鑰從環境變數讀取，禁止寫入程式碼（本倉庫為公開倉庫）。
# 設置方式：export DASHSCOPE_API_KEY=sk-xxxx
QWEN_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
QWEN_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
QWEN_MODEL = "qwen-vl-max"

# ===== 中文名 → character_key 映射（僅用於已入庫角色的匹配，不限制識別範圍）=====
_NAME_TO_KEY = {
    "漩涡鸣人": "naruto_uzumaki",
    "宇智波佐助": "sasuke_uchiha",
    "春野樱": "sakura_haruno",
    "旗木卡卡西": "kakashi_hatake",
    "蒙奇·D·路飞": "monkey_d_luffy",
    "蒙奇.D.路飞": "monkey_d_luffy",
    "罗罗诺亚·索隆": "roronoa_zoro",
    "娜美": "nami",
    "山治": "sanji",
    "艾伦·耶格尔": "eren_yeager",
    "三笠·阿克曼": "mikasa_ackerman",
    "竈门祢豆子": "nezuko_kamado",
    "灶门祢豆子": "nezuko_kamado",
    "绿谷出久": "izuku_midoriya",
    "爆豪胜己": "katsuki_bakugo",
    "孙悟空": "goku",
    "贝吉塔": "vegeta",
    "黑崎一护": "ichigo_kurosaki",
    "朽木露琪亚": "rukia_kuchiki",
    "泉此方": "konata_izumi",
    "雷姆": "rem",
}


def _resolve_character_key(name: str) -> str:
    """
    将 Qwen 返回的中文角色名解析为 character_key。
    
    - 优先查 _NAME_TO_KEY（精确映射）
    - 其次查 ANIME_CHARACTERS（反向搜索）
    - 最后自动生成 slug（用于未入库的新角色）
    """
    if not name:
        return "unknown"
    
    # 1. 精确映射
    key = _NAME_TO_KEY.get(name)
    if key:
        return key
    
    # 2. 反向搜索已知角色库
    for ck, info in ANIME_CHARACTERS.items():
        if info["name"] == name:
            return ck
    
    # 3. 自动生成 slug（新角色）
    slug = name.lower().strip()
    slug = re.sub(r'[·•・]', '_', slug)
    slug = re.sub(r'[^\w\u4e00-\u9fff]', '_', slug)
    slug = re.sub(r'_+', '_', slug).strip('_')
    return slug if slug else "unknown"


class QwenRecognizer:
    """Qwen-VL 动漫角色识别器"""

    def __init__(self):
        try:
            self.client = OpenAI(
                api_key=QWEN_API_KEY,
                base_url=QWEN_API_BASE,
                timeout=httpx.Timeout(30.0, connect=10.0),
            )
            self.model = QWEN_MODEL
            self._available = True
            logger.info(f"Qwen-VL 识别器已就绪，模型: {self.model}")
        except Exception as e:
            logger.warning(f"Qwen-VL 初始化失败: {e}")
            self._available = False

    def is_available(self):
        return self._available

    def _encode_image(self, image_path: str) -> str:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def recognize(self, image_path: str, top_k: int = 5) -> list:
        """
        使用 qwen-vl 开放识别动漫角色（不限已知角色库）

        返回格式：
        [
            {
                "rank": 1,
                "character_key": "naruto_uzumaki" | "auto_generated_slug",
                "name": "漩涡鸣人",
                "anime": "火影忍者",
                "confidence": 95.0,
                "source": "qwen-vl",
                "known_to_db": true | false,   # 是否在本地已知角色库中
                "features": {...},             # Qwen 描述的视觉特征
            },
            ...
        ]
        """
        if not self._available:
            return []

        try:
            image_b64 = self._encode_image(image_path)

            system_prompt = """你是一个专业的动漫角色识别专家。请严格按照以下步骤操作：

**第一步：逐角色视觉特征描述**
仔细观察图中所有角色，对每个角色独立描述：
- 发色+发型（颜色、长短、造型、是否有特殊刘海或遮挡、双马尾/单马尾/短发等）
- 瞳色（颜色、是否有特殊眼型）
- 服装风格+颜色（款式、色调、校服/战斗服/休闲装、是否有标志性设计）
- 标志性配饰（护额、帽子、武器、首饰、发饰、纹身、皮卡丘尾巴等）
- 性别、年龄段、画风（少年漫/少女漫/轻小说风/写实风等）
- 角色在画面中的位置（左/中/右/上/下）或编号（从左到右：角色1、角色2...）

⚠️ 多人图片：必须为每个角色单独列出特征！不准把多个角色的特征混在一起！

**第二步：逐角色识别**
对每个已描述特征的角色，分别判断身份：
- 给出角色名（中文优先）、所属作品名
- 评估置信度（0-100）：
  - 90+ ：极度确定（标志性特征完全匹配，如鸣人的猫须纹+橙色衣服）
  - 70-89 ：比较有把握（多数特征吻合）
  - 50-69 ：推测（部分特征吻合，但不确定）
  - <50 ：不确定
- 说明识别依据：哪些具体视觉特征让你做出这个判断
- ⚠️ 如果某个角色的视觉特征不足以做出明确判断，name 填 "unknown" 并将 confidence 设低

**第三步：输出JSON**
只输出纯JSON，不要加任何解释文字。"""

            user_prompt = f"""请识别这张图片中的动漫角色。

操作要求：
1. 先从左到右、从上到下逐一描述每个角色的视觉特征（发色、瞳色、服装、配饰、画风、位置）
2. 再分别判断每个角色的身份
3. 最多返回 {top_k} 个候选（按置信度从高到低），把握不足就少填
4. ⚠️ 如果图片中有多个角色（双人/多人），必须逐一识别，不要遗漏
5. 如果不是动漫（真人照片、风景、物品、文字截图等），返回 is_anime:false

输出JSON格式：
```json
{{
  "is_anime": true,
  "character_count": 1,
  "art_style": "少年漫/少女漫/轻小说风/写实风",
  "characters": [
    {{
      "position": "左/中/右/上/下 或 编号",
      "features": {{"hair":"","eyes":"","clothing":"","accessories":"","gender":"","estimated_age":""}},
      "name": "角色名（中文优先）",
      "anime": "作品名（中文优先）",
      "confidence": 90,
      "reason": "识别依据：具体特征如何对应到角色"
    }}
  ]
}}
```

关键：
- 每个角色都有独立的 features 描述，不要共用！
- ⚠️ 不要返回 name_i18n 或 anime_i18n 字段（系统会另行从 API 查询真实译名）
- 台湾译名使用繁体中文，大陆译名使用简体中文

非动漫 → {{"is_anime": false, "reason": "非动漫原因", "characters": []}}

⚠️ 防误判规则（严格遵守，违反将导致严重错误）：

【最高优先级：不要被图片中的文字欺骗】
- 🚫 图片中出现的文字、标题、Logo、水印（如印着「地獄少女」「鬼滅の刃」「进击的巨人」等）绝对不能用来推断角色的所属作品！
- ✅ 作品名必须且只能根据角色的【视觉特征】（发色、服装、标志性配饰等）来判断
- ❌ 反面例子：图片上印有「地獄少女」大字 → 不能把画面中的角色的 anime 都写成「地獄少女」
- ✅ 正面例子：角色有黑色长直发+红色瞳孔+黑色水手服+地狱少女的标志性发带 → 这才是判断来自《地獄少女》的依据
- 如果图片中有文字标题，但画面角色的视觉特征与该作品不符，必须按视觉特征给出真实所属作品，而不是照搬图片上的文字

【其他防误判规则】
- 除非看到极具标志性的视觉特征（如鸣人的猫须纹、路飞的草帽、祢豆子的竹筒），不要给高置信度
- 同一个作品中可能有多个外观相似的角色（如《某科学的超电磁炮》中初春饰利、佐天泪子、食蜂操祈），务必仔细区分发色、服装、瞳色
- 白井黑子的标志性特征：棕色双马尾（两条翘起的辫子）+ 常盘台中学校服（米色/浅棕色西装外套）+ 手臂上的风纪委员袖章
- 一方通行的特征：白色短发 + 红色瞳孔 + 黑色条纹T恤或白色简约上衣 + 男性/中性
- 初春饰利的特征：深色短发（有时带发夹）+ 花环头饰（花冠）+ 栅川中学校服（水手服风格）
- 黑崎一护的特征：橙色刺猬头 + 死霸装（黑色和服风）+ 斩魄刀
- 朽木露琪亚的特征：黑色短发（波波头）+ 死霸装 + 白色袖套
- 阎魔爱（地狱少女主角）的特征：黑色长直发 + 红色瞳孔 + 黑色水手服/和服 + 地狱少女标志性红色发带/发饰 + 整体气质阴冷 + 女性
- 巴卫（元气少女缘结缘/Inu x Boku SS）的特征：短发（深色）+ 犬耳（狗耳）＋ 传统日式和服/袴（深蓝色系）＋ 男性 + 严肃气质 + 有紫色/深色眼瞳
- 如果图中角色是短发男性＋犬耳，绝对不是阎魔爱（女性长直发）
- 如果你真的不确定一个角色是谁，用 name:"unknown" 而不是乱猜一个知名角色
- ⚠️ 重要：如果角色不在你的确定范围内，name 必须填 "unknown"，confidence 填 0。自信地乱猜比诚实说不知道更糟糕！
- 只输出纯JSON，不要输出任何其他文字

【相似角色区分指南】（极易混淆，务必仔细对比视觉特征）
- 艾米莉亞（Re:从零开始的异世界生活）vs 芙莉蓮（葬送的芙莉蓮）：
  · 艾米莉亞：银白色长发（双马尾或长直发）＋ 浅蓝色/紫色瞳孔 ＋ 白色/浅色礼服（有时有蓝色装饰）＋ 尖耳朵（精灵耳）＋ 女性
  · 芙莉蓮：银白色短发（耳朵两侧的头发较长，但不是双马尾）＋ 绿色瞳孔 ＋ 深绿色短袍/旅行装（简朴风格）＋ 尖耳朵（精灵耳）＋ 女性 ＋ 气质冷静/无口
  · 关键区别：发型（双马尾/长发 vs 短发）、服装颜色（白色礼服 vs 绿色短袍）、眼神气质（活泼 vs 冷静）
- 白井黑子（某科学的超电磁炮）vs 佐仓杏子（魔法少女小圆）：
  · 白井黑子：棕色双马尾（两条翘起的辫子）＋ 常盘台中学校服（米色/浅棕色西装外套）＋ 手臂上的风纪委员袖章 ＋ 女性
  · 佐仓杏子：橙色短发（有时戴帽子）＋ 现代休闲装/校服 ＋ 魔法少女战斗服（红色系）＋ 女性
  · 关键区别：发色（棕色 vs 橙色）、服装（校服 vs 现代装）、配饰（袖章 vs 无）
"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                            {"type": "text", "text": user_prompt},
                        ]
                    }
                ],
                max_tokens=1000,
                temperature=0.2,
            )

            result_text = response.choices[0].message.content.strip()

            # 清理可能的 markdown 代码块（更健壮的实现）
            if result_text.startswith("```"):
                lines = result_text.split("\n")
                # 去掉第一行（```json 或 ```）
                if lines[0].strip().startswith("```"):
                    lines = lines[1:]
                # 去掉最后一行（```）
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                result_text = "\n".join(lines).strip()

            # 尝试找 JSON 对象（处理模型在 JSON 前后加了额外文字的情况）
            result_text_stripped = result_text.strip()
            brace_start = result_text_stripped.find("{")
            brace_end = result_text_stripped.rfind("}")
            if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
                result_text = result_text_stripped[brace_start:brace_end + 1]

            data = json.loads(result_text)
            is_anime = data.get("is_anime", True)
            characters = data.get("characters", [])

            # 記錄 Qwen 返回的數據（用於調試）
            if characters:
                logger.info(f"Qwen-VL 返回 {len(characters)} 個角色，首角色: {characters[0].get('name', 'N/A')}")
                # 檢查是否有 name_i18n 欄位（僅除錯用，系統不使用 Qwen 的 i18n）
                if characters[0].get("name_i18n"):
                    logger.debug(f"Qwen-VL 返回了 name_i18n（將被忽略）: {characters[0]['name_i18n']}")
                if characters[0].get("anime_i18n"):
                    logger.debug(f"Qwen-VL 返回了 anime_i18n（將被忽略）: {characters[0]['anime_i18n']}")

            # 非动漫图片：返回特殊标记
            if not is_anime:
                reason = data.get("reason", "非动漫图片")
                logger.info(f"Qwen-VL 判定非动漫: {reason}")
                return [{
                    "rank": 0,
                    "character_key": "_not_anime_",
                    "name": "非动漫图片",
                    "anime": reason,
                    "confidence": 0.0,
                    "source": "qwen-vl",
                    "is_anime": False,
                }]

            # 转换为标准格式（开放识别：不限已知角色库）
            character_count = data.get("character_count", len(characters))
            results = []
            for i, char in enumerate(characters[:top_k]):
                name = char.get("name", "").strip()
                anime = char.get("anime", "未知").strip()
                conf = float(char.get("confidence", 85.0))
                reason = char.get("reason", "")
                # 每角色独立特征描述（新 JSON 格式），兜底兼容旧格式
                char_features = char.get("features", data.get("features", {}))
                # 多语言译名——【重要】不使用 Qwen 返回的值（Qwen 会幻觉/瞎编翻译）
                # 系统会在后续步骤中通过 Bangumi/AniList API 查询真实的官方译名
                name_i18n = {}   # 强制忽略 Qwen 的 name_i18n
                anime_i18n = {}  # 强制忽略 Qwen 的 anime_i18n

                # 尝试映射到已知角色库（用於 DB 關聯，不影響識別結果）
                char_key = _resolve_character_key(name)
                known_to_db = char_key in ANIME_CHARACTERS

                results.append({
                    "rank": i + 1,
                    "character_key": char_key,
                    "name": name,
                    "anime": anime,
                    "name_i18n": name_i18n,
                    "anime_i18n": anime_i18n,
                    "confidence": conf,
                    "source": "qwen-vl",
                    "known_to_db": known_to_db,
                    "features": char_features,   # 每个角色独立特征（新版）或全局特征（旧版兜底）
                    "reason": reason,             # Qwen 的识别依据
                    "_character_count": character_count,  # 多人检测标记
                })

            logger.info(
                f"Qwen-VL 开放识别完成: {len(results)} 个角色(图中{character_count}人), "
                f"Top1={results[0]['name'] if results else '无'} "
                f"({'已知' if results and results[0].get('known_to_db') else '新角色'})"
            )
            return results

        except json.JSONDecodeError as e:
            logger.warning(f"Qwen-VL 返回解析失败: {e}, 原文: {result_text[:200]}")
            return []
        except Exception as e:
            logger.warning(f"Qwen-VL 识别失败: {e}")
            return []

    def verify_correction(self, image_path: str, corrected_name: str, corrected_anime: str = "") -> dict:
        """
        使用 Qwen-VL 验证用户提交的纠错是否正确

        参数：
            image_path: 图片路径
            corrected_name: 用户提供的纠正后的角色名
            corrected_anime: 用户提供的作品名（可选）

        返回：
            {
                "verified": True/False,       # 是否验证通过
                "confidence": 85.0,           # Qwen-VL 的置信度
                "qwen_name": "角色名",         # Qwen-VL 自己识别出的名称
                "reason": "验证依据",          # Qwen-VL 的判断理由
            }
        """
        if not self._available:
            logger.warning("Qwen-VL 不可用，跳过纠错验证")
            return {"verified": None, "confidence": 0, "reason": "Qwen-VL不可用"}

        try:
            image_b64 = self._encode_image(image_path)

            prompt = f"""请仔细查看这张图片中的动漫角色，判断以下用户提供的角色信息是否正确。

用户声称：
- 角色名：{corrected_name}
- 作品：{corrected_anime or "未提供"}

请严格按照以下步骤操作：

**第一步：仔细观察图片**
描述角色的视觉特征（发色、瞳色、服装、标志性特征等）。

**第二步：独立判断**
基于你的视觉判断，这个角色是谁？来自哪部作品？

**第三步：比對驗證**
将你的独立判断与用户提供的信息进行比對：
- 如果用户提供的角色名是正确的 → verified: true, confidence 为你的确信度
- 如果用户提供的角色名错误 → verified: false, confidence 为你的确信度
- 如果角色在该图中确实存在但你有疑虑 → verified: true/false, 给出你的判断

**第四步：输出JSON**
只输出纯JSON，不要加任何解释文字：
```json
{{
  "verified": true,
  "confidence": 90,
  "qwen_name": "你识别出的角色名",
  "qwen_anime": "作品名",
  "reason": "验证依据（你为何认为正确或错误）",
  "features": {{"hair":"","eyes":"","clothing":""}}
}}
```

重要规则：
- verified 必须是布尔值 true 或 false
- confidence 0-100，表示你对判断的确信度
- 不要受用户信息影响，必须基于视觉独立判断再对比
- 如果这根本不是动漫角色，verified: false, confidence: 0
"""
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个动漫角色识别验证专家。必须基于视觉特征独立判断，再对比用户提供的信息。"
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                            {"type": "text", "text": prompt},
                        ]
                    }
                ],
                max_tokens=500,
                temperature=0.1,  # 低温度，确保一致性
            )

            result_text = response.choices[0].message.content.strip()

            # 清理 markdown 代码块
            if result_text.startswith("```"):
                lines = result_text.split("\n")
                if lines[0].strip().startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                result_text = "\n".join(lines).strip()

            # 提取 JSON
            brace_start = result_text.find("{")
            brace_end = result_text.rfind("}")
            if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
                result_text = result_text[brace_start:brace_end + 1]

            data = json.loads(result_text)
            verified = data.get("verified", False)
            confidence = float(data.get("confidence", 50))

            logger.info(
                f"Qwen-VL 纠错验证: 用户声称={corrected_name}, "
                f"Qwen判断={verified}, 置信度={confidence}, "
                f"Qwen识别={data.get('qwen_name', 'N/A')}"
            )

            return {
                "verified": verified,
                "confidence": confidence,
                "qwen_name": data.get("qwen_name", ""),
                "qwen_anime": data.get("qwen_anime", ""),
                "reason": data.get("reason", ""),
                "features": data.get("features", {}),
            }

        except json.JSONDecodeError as e:
            logger.warning(f"Qwen-VL 验证返回解析失败: {e}")
            return {"verified": False, "confidence": 0, "reason": f"解析失败: {e}"}
        except Exception as e:
            logger.warning(f"Qwen-VL 验证失败: {e}")
            return {"verified": False, "confidence": 0, "reason": str(e)}

    def confirm_after_admin_approval(self, image_path: str, confirmed_name: str, confirmed_anime: str = "") -> dict:
        """
        管理員核准後的 Qwen 二次驗證 — 確認角色身份以便加入訓練集

        與 verify_correction 不同：此方法的語境是「管理員已人工確認」，Qwen 做最終核實。

        參數：
            image_path: 圖片路徑
            confirmed_name: 管理員核准的最終角色名
            confirmed_anime: 管理員核准的最終作品名

        返回：
            {
                "verified": True/False,
                "confidence": 95.0,
                "reason": "管理員已進行確認，使用者提交糾錯核實...",
                "features": {...},
            }
        """
        if not self._available:
            logger.warning("Qwen-VL 不可用，跳過核准後二次驗證")
            return {"verified": None, "confidence": 0, "reason": "Qwen-VL不可用"}

        try:
            image_b64 = self._encode_image(image_path)

            prompt = f"""你是動漫角色識別系統的最終核實模組。

**背景資訊**：
- 一張動漫角色圖片經過初始識別後，使用者提交了糾錯
- 該糾錯已由系統管理員人工審查並**正式核准**
- 現在需要你做最終視覺核實，以確認這條數據可以安全地加入模型訓練集

**管理員核准的角色資訊**：
- 角色名：{confirmed_name}
- 作品：{confirmed_anime or "未提供"}

**請嚴格按照以下步驟操作**：

**第一步：仔細觀察圖片**
詳細描述該角色的視覺特徵（髮色、髮型、瞳色、服裝、配件、標誌性特徵等）。

**第二步：獨立識別**
基於純視覺判斷，這個角色是誰？來自哪部作品？給出你的答案和確信度。

**第三步：比對管理員核准值**
將你的獨立判斷與管理員核准的資訊（{confirmed_name} / {confirmed_anime or "未提供"}）進行比對。
- 如果一致 → 該數據可信度高
- 如果不一致但有合理解釋（如不同翻譯名稱）→ 仍可接受
- 如果完全矛盾 → 標記為存疑

**第四步：輸出 JSON**
只輸出純 JSON，不要加任何解釋文字：
```json
{{
  "verified": true,
  "confidence": 95,
  "reason": "管理員已進行確認，使用者提交糾錯核實，該角色為{confirmed_name}（{confirmed_anime or '作品待補充'}）。[補充你的視覺觀察作為佐證]",
  "features": {{"hair":"","eyes":"","clothing":""}}
}}
```

**重要規則**：
- verified 必須是布林值 true 或 false
- confidence 0-100
- reason 必須以「管理員已進行確認」開頭
- 這條數據將直接用於模型訓練，請謹慎核實
"""
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是動漫角色識別系統的最終核實專家。管理員已人工確認過此糾錯，你負責做最後的視覺核實。"
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                            {"type": "text", "text": prompt},
                        ]
                    }
                ],
                max_tokens=500,
                temperature=0.1,
            )

            result_text = response.choices[0].message.content.strip()

            # 清理 markdown 代碼塊
            if result_text.startswith("```"):
                lines = result_text.split("\n")
                if lines[0].strip().startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                result_text = "\n".join(lines).strip()

            # 提取 JSON
            brace_start = result_text.find("{")
            brace_end = result_text.rfind("}")
            if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
                result_text = result_text[brace_start:brace_end + 1]

            data = json.loads(result_text)
            verified = data.get("verified", False)
            confidence = float(data.get("confidence", 50))
            reason = data.get("reason", "")

            logger.info(
                f"Qwen-VL 核准後二次驗證: 管理員核准={confirmed_name}, "
                f"Qwen確認={verified}, 置信度={confidence}"
            )

            return {
                "verified": verified,
                "confidence": confidence,
                "reason": reason,
                "features": data.get("features", {}),
            }

        except json.JSONDecodeError as e:
            logger.warning(f"Qwen-VL 核准後驗證返回解析失敗: {e}")
            return {"verified": False, "confidence": 0, "reason": f"解析失敗: {e}"}
        except Exception as e:
            logger.warning(f"Qwen-VL 核准後驗證失敗: {e}")
            return {"verified": False, "confidence": 0, "reason": str(e)}


# ===== 全局单例 =====
_qwen_instance = None


def get_qwen_recognizer() -> QwenRecognizer:
    """获取 Qwen-VL 识别器单例"""
    global _qwen_instance
    if _qwen_instance is None:
        _qwen_instance = QwenRecognizer()
    return _qwen_instance
