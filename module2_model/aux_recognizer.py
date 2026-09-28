"""
module2_model/aux_recognizer.py - 辅助识别器
基于 danbooru-pretrained ResNet50（RF5/danbooru-pretrained）

功能：
  - 作为自训练模型的补充，当主模型置信度低时提供更广泛的角色识别能力
  - danbooru-pretrained 支持 6000+ 标签（含大量动漫角色名），以角色名标签作为识别结果
  - 支持离线回退：若模型无法加载，透明降级（不影响主流程）

使用方式：
  from module2_model.aux_recognizer import AuxRecognizer
  aux = AuxRecognizer()
  results = aux.predict(image_path, top_k=5)
"""

import os
import sys
import logging
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


# ===== 已知角色标签映射 =====
# danbooru 标签格式为 "character_(series)" 或直接 "character"
# 将 danbooru 标签映射到可读的中文名称与作品名
DANBOORU_TAG_MAP = {
    # 火影忍者
    "uzumaki_naruto": {"name": "漩涡鸣人", "anime": "火影忍者"},
    "naruto": {"name": "漩涡鸣人", "anime": "火影忍者"},
    "uchiha_sasuke": {"name": "宇智波佐助", "anime": "火影忍者"},
    # 海贼王
    "monkey_d_luffy": {"name": "蒙奇·D·路飞", "anime": "海贼王"},
    # 进击的巨人
    "mikasa_ackerman": {"name": "三笠·阿克曼", "anime": "进击的巨人"},
    # 龙珠
    "son_gokuu": {"name": "孙悟空", "anime": "龙珠"},
    # 幸运星
    "izumi_konata": {"name": "泉此方", "anime": "幸运星"},
    # Re:从零开始
    "rem_(re:zero)": {"name": "雷姆", "anime": "Re:从零开始"},
    # 鬼灭之刃 (部分标签可能不在6000列表中)
    "kamado_nezuko": {"name": "竈门祢豆子", "anime": "鬼灭之刃"},
    "kamado_tanjirou": {"name": "竈门炭治郎", "anime": "鬼灭之刃"},
    # 我的英雄学院
    "midoriya_izuku": {"name": "绿谷出久", "anime": "我的英雄学院"},
    "bakugou_katsuki": {"name": "爆豪胜己", "anime": "我的英雄学院"},
    # 死神
    "kurosaki_ichigo": {"name": "黑崎一护", "anime": "死神"},
    # 海贼王
    "roronoa_zoro": {"name": "罗罗诺亚·索隆", "anime": "海贼王"},
    "nami_(one_piece)": {"name": "娜美", "anime": "海贼王"},
    "sanji_(one_piece)": {"name": "山治", "anime": "海贼王"},
    # 火影忍者
    "hatake_kakashi": {"name": "旗木卡卡西", "anime": "火影忍者"},
    "haruno_sakura": {"name": "春野樱", "anime": "火影忍者"},
    # 进击的巨人
    "eren_yeager": {"name": "艾伦·耶格尔", "anime": "进击的巨人"},
    # 龙珠
    "vegeta_(dragon_ball)": {"name": "贝吉塔", "anime": "龙珠"},
    # 刀剑神域
    "kirigaya_kazuto": {"name": "桐谷和人", "anime": "刀剑神域"},
    "yuuki_asuna": {"name": "结城明日奈", "anime": "刀剑神域"},
    # Fate系列
    "saber_(fate)": {"name": "Saber", "anime": "Fate系列"},
    "tohsaka_rin": {"name": "远坂凛", "anime": "Fate系列"},
    # EVA
    "ayanami_rei": {"name": "绫波丽", "anime": "新世纪福音战士"},
    "souryuu_asuka_langley": {"name": "明日香·兰格蕾", "anime": "新世纪福音战士"},
    # 通用兜底
    "luffy": {"name": "蒙奇·D·路飞", "anime": "海贼王"},
    "naruto_(series)": {"name": "火影忍者", "anime": "火影忍者"},
    "naruto_shippuuden": {"name": "火影忍者疾风传", "anime": "火影忍者"},
    "remilia_scarlet": {"name": "蕾米莉亚·斯卡雷特", "anime": "东方Project"},
}

# danbooru 角色关键词（用于过滤标签）
# 每个关键词必须以「下划线」或「行首/行尾」为边界完整匹配，防止子串误报
# 例如 "rem" 不应匹配 "trembling", "rin" 不应匹配 "earrings"
_CHARACTER_KEYWORDS = [
    "uzumaki", "uchiha", "naruto", "monkey_d", "luffy",
    "mikasa", "ackerman", "izumi", "konata", "son_goku",
    "rem_", "kamado", "nezuko", "tanjirou",
    "midoriya", "bakugou", "todoroki", "kurosaki",
    "roronoa", "zoro", "nami_", "sanji_",
    "hatake", "kakashi", "haruno", "sakura",
    "eren_ye", "vegeta", "ayanami", "asuka_",
    "saber_", "tohsaka", "kirigaya", "asuna_",
    "sakura_kyouko", "matou",
]


class AuxRecognizer:
    """
    辅助识别器 —— 基于 danbooru-pretrained ResNet50
    
    加载策略（按优先级）：
    1. torch.hub 在线加载 RF5/danbooru-pretrained
    2. 若已有本地缓存则直接使用
    3. 若均失败则设 _available=False，不影响主流程
    
    识别策略：
    - 输出 6000+ 标签的 sigmoid 概率
    - 过滤出角色相关标签（含关键词）
    - 映射到中文名称与作品名
    """

    # 辅助模型置信度阈值（动画截图模式下角色标签分数普遍很低，降低阈值以提升召回）
    AUX_CONFIDENCE_THRESHOLD = 0.5

    def __init__(self):
        self._available = False
        self._model = None
        self._labels: List[str] = []
        self._transform = None
        self._try_load()

    # ------------------------------------------------------------------ #
    # 加载
    # ------------------------------------------------------------------ #
    def _try_load(self):
        """尝试加载 danbooru-pretrained 模型（失败则静默降级）
        
        优先使用本地缓存（~/.cache/torch/hub/），避免 GitHub API 限流。
        若本地不存在则尝试 torch.hub 在线加载。
        """
        try:
            import json
            import torch
            from torchvision import transforms

            hub_dir = os.path.expanduser("~/.cache/torch/hub")
            local_repo = os.path.join(hub_dir, "RF5_danbooru-pretrained_main")
            tags_json = os.path.join(local_repo, "config", "class_names_6000.json")
            ckpt_path = os.path.join(
                hub_dir, "checkpoints", "resnet50-13306192.pth"
            )
            
            logger.info("正在加载 danbooru-pretrained 辅助识别模型...")

            # 优先从本地缓存加载（避免 GitHub API rate limit）
            if os.path.isdir(local_repo) and os.path.isfile(
                os.path.join(local_repo, "hubconf.py")
            ):
                logger.info("  使用本地缓存: %s", local_repo)
                # pretrained=False 避免 torchvision 覆蓋權重
                self._model = torch.hub.load(
                    local_repo, "resnet50",
                    source="local", pretrained=False, trust_repo=True,
                    top_n=6000,
                )
                # 手動加載 danbooru 權重
                if os.path.isfile(ckpt_path):
                    state = torch.load(ckpt_path, map_location="cpu")
                    self._model.load_state_dict(state)
                    logger.info("  權重加載: %s", ckpt_path)
                else:
                    raise FileNotFoundError(f"權重文件不存在: {ckpt_path}")
            else:
                logger.info("  本地缓存不存在，尝试在线加载...")
                self._model = torch.hub.load(
                    "RF5/danbooru-pretrained", "resnet50",
                    pretrained=False, top_n=6000,
                )
                # torch.hub 可能會自動下載權重，嘗試 load_state_dict_from_url
                state = torch.hub.load_state_dict_from_url(
                    "https://github.com/RF5/danbooru-pretrained/releases/download/v0.1/resnet50-13306192.pth",
                    progress=False,
                )
                self._model.load_state_dict(state)
            
            self._model.eval()

            # 加载标签列表（从本地 JSON）
            if os.path.isfile(tags_json):
                with open(tags_json, "r", encoding="utf-8") as f:
                    self._labels = json.load(f)
                logger.info("  标签加载自: %s", tags_json)
            else:
                # 回退：尝试 torch.hub
                logger.info("  标签 JSON 不存在，尝试在线获取...")
                self._labels = torch.hub.load(
                    "RF5/danbooru-pretrained", "get_tags",
                )

            # 与 danbooru-pretrained 原始 repo 一致的预处理
            self._transform = transforms.Compose([
                transforms.Resize(360),
                transforms.CenterCrop(360),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.7137, 0.6628, 0.6519],
                    std=[0.2970, 0.3017, 0.2979],
                ),
            ])

            self._available = True
            logger.info(
                f"辅助识别模型加载成功 | 标签数: {len(self._labels)}"
            )

        except Exception as e:
            logger.warning(
                f"辅助识别模型加载失败（将跳过辅助识别）: {e}"
            )
            self._available = False

    # ------------------------------------------------------------------ #
    # 预测
    # ------------------------------------------------------------------ #
    def is_available(self) -> bool:
        return self._available

    def predict(
        self,
        image_input,
        top_k: int = 5,
    ) -> List[Dict]:
        """
        对图像进行辅助识别
        
        参数：
            image_input: 文件路径（str/Path）或 PIL.Image
            top_k: 返回候选数量
        
        返回：
            list of dict，格式与 AnimeEvaluator.predict_single() 一致：
            {
                "rank": 1,
                "character_key": "uzumaki_naruto",
                "name": "漩涡鸣人",
                "anime": "火影忍者",
                "confidence": 72.3,
                "class_id": -1,   # -1 表示辅助模型（无本地 class_id）
                "source": "aux",  # 标记来源
            }
        """
        if not self._available:
            return []

        try:
            import torch
            from PIL import Image

            # 加载图像
            if isinstance(image_input, (str, Path)):
                img = Image.open(str(image_input)).convert("RGB")
            else:
                img = image_input.convert("RGB")

            # 推理
            tensor = self._transform(img).unsqueeze(0)
            with torch.no_grad():
                logits = self._model(tensor)
                probs = torch.sigmoid(logits)[0]  # 多标签，使用 sigmoid

            # 找出置信度最高的角色相关标签
            char_results = self._filter_character_tags(probs, top_k * 3)

            # 只返回置信度高于阈值的结果
            filtered = [
                r for r in char_results
                if r["confidence"] >= self.AUX_CONFIDENCE_THRESHOLD
            ]

            return filtered[:top_k]

        except Exception as e:
            logger.error(f"辅助识别推理失败: {e}")
            return []

    def _filter_character_tags(
        self,
        probs,  # torch.Tensor 1D，长度 = len(self._labels)
        top_n: int,
    ) -> List[Dict]:
        """过滤出角色相关标签，去重后排序"""
        import torch

        results = []
        seen_names = {}  # name → index，用于去重（同名取高置信度）
        scores = probs.cpu().tolist()

        for idx, (tag, score) in enumerate(zip(self._labels, scores)):
            if not self._is_character_tag(tag):
                continue

            confidence = round(score * 100, 2)
            char_info = self._resolve_tag(tag)

            entry = {
                "rank": 0,
                "character_key": tag,
                "name": char_info["name"],
                "anime": char_info["anime"],
                "confidence": confidence,
                "class_id": -1,
                "source": "aux",
            }

            name = entry["name"]
            if name in seen_names:
                # 同名：保留置信度更高的
                if confidence > results[seen_names[name]]["confidence"]:
                    results[seen_names[name]] = entry
            else:
                seen_names[name] = len(results)
                results.append(entry)

        # 按置信度降序，只保留 top_n
        results.sort(key=lambda x: x["confidence"], reverse=True)
        results = results[:top_n]
        for i, r in enumerate(results, start=1):
            r["rank"] = i

        return results

    @staticmethod
    def _is_character_tag(tag: str) -> bool:
        """判断是否为角色相关标签（使用下划线边界匹配，防止子串误报）"""
        tag_lower = tag.lower()
        # 跳过通用标签（画风/质量/NSFW等）
        skip_prefixes = (
            "rating:", "score_", "year:", "source:", "meta:", "general:",
            "1girl", "1boy", "2girls", "2boys", "multiple",
            "highres", "absurdres", "masterpiece", "best_quality",
            "looking_at_viewer", "smile", "open_mouth", "long_hair",
            "short_hair", "blonde_hair", "black_hair", "white_hair",
            "blue_eyes", "red_eyes", "green_eyes",
        )
        for prefix in skip_prefixes:
            if tag_lower.startswith(prefix) or tag_lower == prefix:
                return False

        # 将标签按「_」拆分为片段，在片段边界上精确匹配关键词
        segments = tag_lower.split("_")
        for kw in _CHARACTER_KEYWORDS:
            kw_stripped = kw.rstrip("_")  # 去掉关键词自身的后缀下划线
            # 方式1：关键词是完整片段（如 "naruto" 匹配 "naruto"、"uzumaki_naruto"）
            if kw_stripped in segments:
                return True
            # 方式2：连续两个片段拼接后匹配（如 "izumi"+"konata" → "izumi_konata"）
            for i in range(len(segments) - 1):
                if f"{segments[i]}_{segments[i+1]}" == kw_stripped:
                    return True
                if f"{segments[i]}_{segments[i+1]}" == kw:
                    return True

        # danbooru 角色标签格式：精确匹配已知映射
        if tag_lower in DANBOORU_TAG_MAP:
            return True

        return False

    @staticmethod
    def _resolve_tag(tag: str) -> Dict[str, str]:
        """将 danbooru 标签解析为可读名称"""
        # 精确匹配
        if tag in DANBOORU_TAG_MAP:
            return DANBOORU_TAG_MAP[tag]
        tag_lower = tag.lower()
        if tag_lower in DANBOORU_TAG_MAP:
            return DANBOORU_TAG_MAP[tag_lower]

        # 模糊匹配：标签中含有已知角色名
        for known_key, info in DANBOORU_TAG_MAP.items():
            if known_key in tag_lower or tag_lower in known_key:
                return info

        # 兜底：将 snake_case 转换为可读形式
        readable = tag.replace("_", " ").title()
        # 从 "Character (Series)" 格式中提取
        if "(" in readable and ")" in readable:
            parts = readable.split("(")
            char_name = parts[0].strip()
            series = parts[1].replace(")", "").strip()
            return {"name": char_name, "anime": series}

        return {"name": readable, "anime": "未知作品"}


# ===== 全局单例（懒加载）=====
_aux_instance: Optional[AuxRecognizer] = None


def get_aux_recognizer() -> AuxRecognizer:
    """获取辅助识别器单例"""
    global _aux_instance
    if _aux_instance is None:
        _aux_instance = AuxRecognizer()
    return _aux_instance
