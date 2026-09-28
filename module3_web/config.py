"""
config.py - 全局配置文件
基于深度学习的动漫角色图像识别系统
"""
import os

# ===== 路径配置 =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
AUGMENTED_DIR = os.path.join(DATA_DIR, "augmented")
MODELS_DIR = os.path.join(BASE_DIR, "models")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

# ===== 图像配置 =====
IMAGE_SIZE = 224          # 标准化尺寸
IMAGE_CHANNELS = 3
MEAN = [0.485, 0.456, 0.406]   # ImageNet均值（用于迁移学习）
STD = [0.229, 0.224, 0.225]    # ImageNet标准差

# 支持识别的动漫角色列表（实际用于训练的19个，排除无数据的tanjiro_kamado）
# 注意：此列表顺序与 trainer.py 的 active_classes（按字母序）不同
# evaluator.py 和 app.py 应从 checkpoint 的 active_classes 读取，而非此处
#
# 多语系结构（v2）：每个角色/番剧名称支援 9 种语言
# 使用各市場標準譯名 — 繁體中文使用台灣當地譯名
# 語言代碼：zh-CN, zh-TW, ja, en, ko, fr, es, vi, th
ANIME_CHARACTERS = {
    # ===== 火影忍者 / NARUTO =====
    "naruto_uzumaki": {
        "name": {
            "zh-CN": "漩涡鸣人", "zh-TW": "漩渦鳴人",
            "ja": "うずまきナルト", "en": "Naruto Uzumaki",
            "ko": "나루토 우즈마키",
            "fr": "Naruto Uzumaki", "es": "Naruto Uzumaki",
            "vi": "Naruto Uzumaki", "th": "นารูโตะ อุซึมากิ",
        },
        "anime": {
            "zh-CN": "火影忍者", "zh-TW": "火影忍者",
            "ja": "NARUTO -ナルト-", "en": "Naruto",
            "ko": "나루토",
            "fr": "Naruto", "es": "Naruto",
            "vi": "Naruto", "th": "นารูโตะ",
        }
    },
    "sasuke_uchiha": {
        "name": {
            "zh-CN": "宇智波佐助", "zh-TW": "宇智波佐助",
            "ja": "うちはサスケ", "en": "Sasuke Uchiha",
            "ko": "우치하 사스케",
            "fr": "Sasuke Uchiha", "es": "Sasuke Uchiha",
            "vi": "Sasuke Uchiha", "th": "ซาสึเกะ อุจิวะ",
        },
        "anime": {
            "zh-CN": "火影忍者", "zh-TW": "火影忍者",
            "ja": "NARUTO -ナルト-", "en": "Naruto",
            "ko": "나루토",
            "fr": "Naruto", "es": "Naruto",
            "vi": "Naruto", "th": "นารูโตะ",
        }
    },
    "sakura_haruno": {
        "name": {
            "zh-CN": "春野樱", "zh-TW": "春野櫻",
            "ja": "春野サクラ", "en": "Sakura Haruno",
            "ko": "하루노 사쿠라",
            "fr": "Sakura Haruno", "es": "Sakura Haruno",
            "vi": "Sakura Haruno", "th": "ซากุระ ฮารุโนะ",
        },
        "anime": {
            "zh-CN": "火影忍者", "zh-TW": "火影忍者",
            "ja": "NARUTO -ナルト-", "en": "Naruto",
            "ko": "나루토",
            "fr": "Naruto", "es": "Naruto",
            "vi": "Naruto", "th": "นารูโตะ",
        }
    },
    "kakashi_hatake": {
        "name": {
            "zh-CN": "旗木卡卡西", "zh-TW": "旗木卡卡西",
            "ja": "はたけカカシ", "en": "Kakashi Hatake",
            "ko": "하타케 카카시",
            "fr": "Kakashi Hatake", "es": "Kakashi Hatake",
            "vi": "Kakashi Hatake", "th": "คาคาชิ ฮาตาเกะ",
        },
        "anime": {
            "zh-CN": "火影忍者", "zh-TW": "火影忍者",
            "ja": "NARUTO -ナルト-", "en": "Naruto",
            "ko": "나루토",
            "fr": "Naruto", "es": "Naruto",
            "vi": "Naruto", "th": "นารูโตะ",
        }
    },
    # ===== 航海王 / ONE PIECE（台灣官方譯名：航海王）=====
    "monkey_d_luffy": {
        "name": {
            "zh-CN": "蒙奇·D·路飞", "zh-TW": "蒙其·D·魯夫",
            "ja": "モンキー・D・ルフィ", "en": "Monkey D. Luffy",
            "ko": "몽키 D. 루피",
            "fr": "Monkey D. Luffy", "es": "Monkey D. Luffy",
            "vi": "Monkey D. Luffy", "th": "มังกี้ ดี. ลูฟี่",
        },
        "anime": {
            "zh-CN": "海贼王", "zh-TW": "航海王",
            "ja": "ONE PIECE", "en": "One Piece",
            "ko": "원피스",
            "fr": "One Piece", "es": "One Piece",
            "vi": "One Piece", "th": "วันพีซ",
        }
    },
    "roronoa_zoro": {
        "name": {
            "zh-CN": "罗罗诺亚·索隆", "zh-TW": "羅羅亞·索隆",
            "ja": "ロロノア・ゾロ", "en": "Roronoa Zoro",
            "ko": "롤로노아 조로",
            "fr": "Roronoa Zoro", "es": "Roronoa Zoro",
            "vi": "Roronoa Zoro", "th": "โรโรโนอา โซโล",
        },
        "anime": {
            "zh-CN": "海贼王", "zh-TW": "航海王",
            "ja": "ONE PIECE", "en": "One Piece",
            "ko": "원피스",
            "fr": "One Piece", "es": "One Piece",
            "vi": "One Piece", "th": "วันพีซ",
        }
    },
    "nami": {
        "name": {
            "zh-CN": "娜美", "zh-TW": "娜美",
            "ja": "ナミ", "en": "Nami",
            "ko": "나미",
            "fr": "Nami", "es": "Nami",
            "vi": "Nami", "th": "นามิ",
        },
        "anime": {
            "zh-CN": "海贼王", "zh-TW": "航海王",
            "ja": "ONE PIECE", "en": "One Piece",
            "ko": "원피스",
            "fr": "One Piece", "es": "One Piece",
            "vi": "One Piece", "th": "วันพีซ",
        }
    },
    "sanji": {
        "name": {
            "zh-CN": "山治", "zh-TW": "香吉士",
            "ja": "サンジ", "en": "Sanji",
            "ko": "상디",
            "fr": "Sanji", "es": "Sanji",
            "vi": "Sanji", "th": "ซันจิ",
        },
        "anime": {
            "zh-CN": "海贼王", "zh-TW": "航海王",
            "ja": "ONE PIECE", "en": "One Piece",
            "ko": "원피스",
            "fr": "One Piece", "es": "One Piece",
            "vi": "One Piece", "th": "วันพีซ",
        }
    },
    # ===== 進擊的巨人 / Attack on Titan =====
    "eren_yeager": {
        "name": {
            "zh-CN": "艾伦·耶格尔", "zh-TW": "艾連·葉卡",
            "ja": "エレン・イェーガー", "en": "Eren Yeager",
            "ko": "에렌 예거",
            "fr": "Eren Jäger", "es": "Eren Jaeger",
            "vi": "Eren Yeager", "th": "เอเรน เยเกอร์",
        },
        "anime": {
            "zh-CN": "进击的巨人", "zh-TW": "進擊的巨人",
            "ja": "進撃の巨人", "en": "Attack on Titan",
            "ko": "진격의 거인",
            "fr": "L'Attaque des Titans", "es": "Ataque a los Titanes",
            "vi": "Đại Chiến Titan", "th": "ผ่าพิภพไททัน",
        }
    },
    "mikasa_ackerman": {
        "name": {
            "zh-CN": "三笠·阿克曼", "zh-TW": "米卡莎·阿卡曼",
            "ja": "ミカサ・アッカーマン", "en": "Mikasa Ackerman",
            "ko": "미카사 아커만",
            "fr": "Mikasa Ackerman", "es": "Mikasa Ackerman",
            "vi": "Mikasa Ackerman", "th": "มิคาสะ แอคเคอร์แมน",
        },
        "anime": {
            "zh-CN": "进击的巨人", "zh-TW": "進擊的巨人",
            "ja": "進撃の巨人", "en": "Attack on Titan",
            "ko": "진격의 거인",
            "fr": "L'Attaque des Titans", "es": "Ataque a los Titanes",
            "vi": "Đại Chiến Titan", "th": "ผ่าพิภพไททัน",
        }
    },
    # ===== 鬼滅之刃 / Demon Slayer =====
    "nezuko_kamado": {
        "name": {
            "zh-CN": "灶门祢豆子", "zh-TW": "竈門禰豆子",
            "ja": "竈門 禰豆子", "en": "Nezuko Kamado",
            "ko": "카마도 네즈코",
            "fr": "Nezuko Kamado", "es": "Nezuko Kamado",
            "vi": "Nezuko Kamado", "th": "เนซึโกะ คามาโดะ",
        },
        "anime": {
            "zh-CN": "鬼灭之刃", "zh-TW": "鬼滅之刃",
            "ja": "鬼滅の刃", "en": "Demon Slayer: Kimetsu no Yaiba",
            "ko": "귀멸의 칼날",
            "fr": "Demon Slayer", "es": "Demon Slayer",
            "vi": "Thanh Gươm Diệt Quỷ", "th": "ดาบพิฆาตอสูร",
        }
    },
    # ===== 我的英雄學院 / My Hero Academia =====
    "izuku_midoriya": {
        "name": {
            "zh-CN": "绿谷出久", "zh-TW": "綠谷出久",
            "ja": "緑谷出久", "en": "Izuku Midoriya",
            "ko": "미도리야 이즈쿠",
            "fr": "Izuku Midoriya", "es": "Izuku Midoriya",
            "vi": "Izuku Midoriya", "th": "อิซึคุ มิโดริยะ",
        },
        "anime": {
            "zh-CN": "我的英雄学院", "zh-TW": "我的英雄學院",
            "ja": "僕のヒーローアカデミア", "en": "My Hero Academia",
            "ko": "나의 히어로 아카데미아",
            "fr": "My Hero Academia", "es": "My Hero Academia",
            "vi": "My Hero Academia", "th": "มายฮีโร่ อคาเดเมีย",
        }
    },
    "katsuki_bakugo": {
        "name": {
            "zh-CN": "爆豪胜己", "zh-TW": "爆豪勝己",
            "ja": "爆豪勝己", "en": "Katsuki Bakugo",
            "ko": "바쿠고 카츠키",
            "fr": "Katsuki Bakugo", "es": "Katsuki Bakugo",
            "vi": "Katsuki Bakugo", "th": "คัตสึกิ บาคุโก",
        },
        "anime": {
            "zh-CN": "我的英雄学院", "zh-TW": "我的英雄學院",
            "ja": "僕のヒーローアカデミア", "en": "My Hero Academia",
            "ko": "나의 히어로 아카데미아",
            "fr": "My Hero Academia", "es": "My Hero Academia",
            "vi": "My Hero Academia", "th": "มายฮีโร่ อคาเดเมีย",
        }
    },
    # ===== 七龍珠 / Dragon Ball（台灣譯名：七龍珠）=====
    "goku": {
        "name": {
            "zh-CN": "孙悟空", "zh-TW": "孫悟空",
            "ja": "孫悟空", "en": "Goku",
            "ko": "손오공",
            "fr": "Sangoku", "es": "Goku",
            "vi": "Goku", "th": "โกคู",
        },
        "anime": {
            "zh-CN": "龙珠", "zh-TW": "七龍珠",
            "ja": "ドラゴンボール", "en": "Dragon Ball",
            "ko": "드래곤볼",
            "fr": "Dragon Ball", "es": "Dragon Ball",
            "vi": "Dragon Ball", "th": "ดราก้อนบอล",
        }
    },
    "vegeta": {
        "name": {
            "zh-CN": "贝吉塔", "zh-TW": "達爾",
            "ja": "ベジータ", "en": "Vegeta",
            "ko": "베지터",
            "fr": "Vegeta", "es": "Vegeta",
            "vi": "Vegeta", "th": "เบจิต้า",
        },
        "anime": {
            "zh-CN": "龙珠", "zh-TW": "七龍珠",
            "ja": "ドラゴンボール", "en": "Dragon Ball",
            "ko": "드래곤볼",
            "fr": "Dragon Ball", "es": "Dragon Ball",
            "vi": "Dragon Ball", "th": "ดราก้อนบอล",
        }
    },
    # ===== 死神 / BLEACH =====
    "ichigo_kurosaki": {
        "name": {
            "zh-CN": "黑崎一护", "zh-TW": "黑崎一護",
            "ja": "黒崎一護", "en": "Ichigo Kurosaki",
            "ko": "쿠로사키 이치고",
            "fr": "Ichigo Kurosaki", "es": "Ichigo Kurosaki",
            "vi": "Ichigo Kurosaki", "th": "อิจิโกะ คุโรซากิ",
        },
        "anime": {
            "zh-CN": "死神", "zh-TW": "死神",
            "ja": "BLEACH", "en": "Bleach",
            "ko": "블리치",
            "fr": "Bleach", "es": "Bleach",
            "vi": "Bleach", "th": "เทพมรณะ",
        }
    },
    "rukia_kuchiki": {
        "name": {
            "zh-CN": "朽木露琪亚", "zh-TW": "朽木露琪亞",
            "ja": "朽木ルキア", "en": "Rukia Kuchiki",
            "ko": "쿠치키 루키아",
            "fr": "Rukia Kuchiki", "es": "Rukia Kuchiki",
            "vi": "Rukia Kuchiki", "th": "ลูเคีย คุจิกิ",
        },
        "anime": {
            "zh-CN": "死神", "zh-TW": "死神",
            "ja": "BLEACH", "en": "Bleach",
            "ko": "블리치",
            "fr": "Bleach", "es": "Bleach",
            "vi": "Bleach", "th": "เทพมรณะ",
        }
    },
    # ===== 幸運☆星 / Lucky Star =====
    "konata_izumi": {
        "name": {
            "zh-CN": "泉此方", "zh-TW": "泉此方",
            "ja": "泉こなた", "en": "Konata Izumi",
            "ko": "이즈미 코나타",
            "fr": "Konata Izumi", "es": "Konata Izumi",
            "vi": "Konata Izumi", "th": "โคนาตะ อิซึมิ",
        },
        "anime": {
            "zh-CN": "幸运星", "zh-TW": "幸運☆星",
            "ja": "らき☆すた", "en": "Lucky Star",
            "ko": "러키☆스타",
            "fr": "Lucky Star", "es": "Lucky Star",
            "vi": "Lucky Star", "th": "ลัคกี้☆สตาร์",
        }
    },
    # ===== Re:從零開始的異世界生活 / Re:Zero =====
    "rem": {
        "name": {
            "zh-CN": "雷姆", "zh-TW": "雷姆",
            "ja": "レム", "en": "Rem",
            "ko": "렘",
            "fr": "Rem", "es": "Rem",
            "vi": "Rem", "th": "เรม",
        },
        "anime": {
            "zh-CN": "Re:从零开始的异世界生活", "zh-TW": "Re:從零開始的異世界生活",
            "ja": "Re:ゼロから始める異世界生活", "en": "Re:Zero − Starting Life in Another World",
            "ko": "Re:제로부터 시작하는 이세계 생활",
            "fr": "Re:Zero", "es": "Re:Zero",
            "vi": "Re:Zero − Bắt Đầu Lại Ở Thế Giới Khác", "th": "Re:Zero",
        }
    },

    # ===== Qwen 開放識別常見角色（2026-06-21 擴展）=====
    "tanjiro_kamado": {
        "name": {
            "zh-CN": "灶门炭治郎", "zh-TW": "竈門炭治郎",
            "ja": "竈門 炭治郎", "en": "Tanjiro Kamado",
            "ko": "탄지로 카마도",
            "fr": "Tanjiro Kamado", "es": "Tanjiro Kamado",
            "vi": "Kamado Tanjirō", "th": "คามาโดะ ทันจิโร่",
        },
        "anime": {
            "zh-CN": "鬼灭之刃", "zh-TW": "鬼滅之刃",
            "ja": "鬼滅の刃", "en": "Demon Slayer: Kimetsu no Yaiba",
            "ko": "귀멸의 칼날",
            "fr": "Demon Slayer", "es": "Demon Slayer",
            "vi": "Thanh Gươm Diệt Quỷ", "th": "ดีมอน สลเยอร์",
        },
    },
    "nezuko_kamado_ext": {
        "name": {
            "zh-CN": "灶门祢豆子", "zh-TW": "竈門禰豆子",
            "ja": "竈門 禰豆子", "en": "Nezuko Kamado",
            "ko": "네즈코 카마도",
            "fr": "Nezuko Kamado", "es": "Nezuko Kamado",
            "vi": "Kamado Nezuko", "th": "คามาโดะ เนซุโกะ",
        },
        "anime": {
            "zh-CN": "鬼灭之刃", "zh-TW": "鬼滅之刃",
            "ja": "鬼滅の刃", "en": "Demon Slayer: Kimetsu no Yaiba",
            "ko": "귀멸의 칼날",
            "fr": "Demon Slayer", "es": "Demon Slayer",
            "vi": "Thanh Gươm Diệt Quỷ", "th": "ดีมอน สลเยอร์",
        },
    },
    "enma_ai": {
        "name": {
            "zh-CN": "阎魔爱", "zh-TW": "閻魔愛",
            "ja": "閻魔 あい", "en": "Enma Ai",
            "ko": "엔마 아이",
            "fr": "Enma Ai", "es": "Enma Ai",
            "vi": "Enma Ai", "th": "เอ็นมะ ไอ",
        },
        "anime": {
            "zh-CN": "地狱少女", "zh-TW": "地獄少女",
            "ja": "地獄少女", "en": "Hell Girl (Jigoku Shoujo)",
            "ko": "지옥 소녀",
            "fr": "Jigoku Shoujo", "es": "Jigoku Shoujo",
            "vi": "Cô Nữ Địa Ngục", "th": "Jigoku Shoujo",
        },
    },
    "hone_onna": {
        "name": {
            "zh-CN": "骨女", "zh-TW": "骨女",
            "ja": "骨女", "en": "Hone Onna",
            "ko": "뼈여자",
            "fr": "Hone Onna", "es": "Hone Onna",
            "vi": "Hone Onna", "th": "โฮเนะ ออนนะ",
        },
        "anime": {
            "zh-CN": "地狱少女", "zh-TW": "地獄少女",
            "ja": "地獄少女", "en": "Hell Girl (Jigoku Shoujo)",
            "ko": "지옥 소녀",
            "fr": "Jigoku Shoujo", "es": "Jigoku Shoujo",
            "vi": "Cô Nữ Địa Ngục", "th": "Jigoku Shoujo",
        },
    },
    "inuyasha": {
        "name": {
            "zh-CN": "犬夜叉", "zh-TW": "犬夜叉",
            "ja": "犬夜叉", "en": "Inuyasha",
            "ko": "이누야샤",
            "fr": "Inuyasha", "es": "Inuyasha",
            "vi": "Inuyasha", "th": "ินุยาชะ",
        },
        "anime": {
            "zh-CN": "犬夜叉", "zh-TW": "犬夜叉",
            "ja": "犬夜叉", "en": "Inuyasha",
            "ko": "이누야샤",
            "fr": "Inuyasha", "es": "Inuyasha",
            "vi": "Inuyasha", "th": "ินุยาชะ",
        },
    },
    "sakura_kinomoto": {
        "name": {
            "zh-CN": "木之本樱", "zh-TW": "木之本櫻",
            "ja": "木之本 桜", "en": "Sakura Kinomoto",
            "ko": "목본 사쿠라",
            "fr": "Sakura Kinomoto", "es": "Sakura Kinomoto",
            "vi": "Kinomoto Sakura", "th": "คิโนโมโตะ ซากุระ",
        },
        "anime": {
            "zh-CN": "魔卡少女樱", "zh-TW": "魔卡少女櫻",
            "ja": "カードキャプターさくら", "en": "Cardcaptor Sakura",
            "ko": "카드캡터 체리",
            "fr": "Cardcaptor Sakura", "es": "Sakura Card Captor",
            "vi": "Sakura Bắt Thẻ", "th": "การ์ดแคปเตอร์ ซากุระ",
        },
    },
    "misaka_mikoto": {
        "name": {
            "zh-CN": "御坂美琴", "zh-TW": "御坂美琴",
            "ja": "御坂 美琴", "en": "Mikoto Misaka",
            "ko": "미사카 미코토",
            "fr": "Mikoto Misaka", "es": "Mikoto Misaka",
            "vi": "Misaka Mikoto", "th": "มิซากะ มิโคโตะ",
        },
        "anime": {
            "zh-CN": "某科学的超电磁炮", "zh-TW": "某科學的超電磁砲",
            "ja": "とある科学の超電磁砲", "en": "A Certain Scientific Railgun",
            "ko": "어떤 과학의 초전자포",
            "fr": "A Certain Scientific Railgun", "es": "A Certain Scientific Railgun",
            "vi": "A Certain Scientific Railgun", "th": "A Certain Scientific Railgun",
        },
    },
    "uiharu_kazari": {
        "name": {
            "zh-CN": "佐天泪子", "zh-TW": "佐天泪子",
            "ja": "佐天 淚子", "en": "Uiharu Kazari",
            "ko": "사텐 루이코",
            "fr": "Uiharu Kazari", "es": "Uiharu Kazari",
            "vi": "Uiharu Kazari", "th": "อุิฮารุ คาซาริ",
        },
        "anime": {
            "zh-CN": "某科学的超电磁炮", "zh-TW": "某科學的超電磁砲",
            "ja": "とある科学の超電磁砲", "en": "A Certain Scientific Railgun",
            "ko": "어떤 과학의 초전자포",
            "fr": "A Certain Scientific Railgun", "es": "A Certain Scientific Railgun",
            "vi": "A Certain Scientific Railgun", "th": "A Certain Scientific Railgun",
        },
    },
    "anya_forger": {
        "name": {
            "zh-CN": "阿尼亚", "zh-TW": "阿尼亞",
            "ja": "アニア・フォージャー", "en": "Anya Forger",
            "ko": "아니아 포저",
            "fr": "Anya Forger", "es": "Anya Forger",
            "vi": "Anya Forger", "th": "อันย่า ฟอร์จเจอร์",
        },
        "anime": {
            "zh-CN": "间谍过家家", "zh-TW": "間諜過家家",
            "ja": "スパイファミリー", "en": "Spy x Family",
            "ko": "스파이 패밀리",
            "fr": "Spy x Family", "es": "Spy x Family",
            "vi": "Gia Đình Điệp Viên", "th": "สปาย x แฟมิลี่",
        },
    },
    "subaru_natsuki": {
        "name": {
            "zh-CN": "菜月昴", "zh-TW": "菜月昴",
            "ja": "菜月 昴", "en": "Subaru Natsuki",
            "ko": "나츠키 스바루",
            "fr": "Subaru Natsuki", "es": "Subaru Natsuki",
            "vi": "Natsuki Subaru", "th": "นัทสึกิ สบารุ",
        },
        "anime": {
            "zh-CN": "Re:从零开始的异世界生活", "zh-TW": "Re:從零開始的異世界生活",
            "ja": "Re:ゼロから始める異世界生活", "en": "Re:Zero − Starting Life in Another World",
            "ko": "Re:제로부터 시작하는 이세계 생활",
            "fr": "Re:Zero", "es": "Re:Zero",
            "vi": "Re:Zero − Bắt Đầu Lại Ở Thế Giới Khác", "th": "Re:Zero",
        },
    },
    "umaru_doma": {
        "name": {
            "zh-CN": "土间埋", "zh-TW": "土間埋",
            "ja": "土間 埋", "en": "Umaru Doma",
            "ko": "도마 우마루",
            "fr": "Umaru Doma", "es": "Umaru Doma",
            "vi": "Doma Umaru", "th": "โดมะ อุมารุ",
        },
        "anime": {
            "zh-CN": "干物妹小埋", "zh-TW": "幹物妹小埋",
            "ja": "干物妹!うまるちゃん", "en": "Himouto! Umaru-chan",
            "ko": "힘쎄 여자 우마루-chan",
            "fr": "Himouto! Umaru-chan", "es": "Himouto! Umaru-chan",
            "vi": "Himouto! Umaru-chan", "th": "Himouto! Umaru-chan",
        },
    },
    "saten_ruiko_ext": {
        "name": {
            "zh-CN": "初春饰利", "zh-TW": "初春飾利",
            "ja": "初春 飾利", "en": "Saten Ruiko",
            "ko": "사텐 루이코",
            "fr": "Saten Ruiko", "es": "Saten Ruiko",
            "vi": "Saten Ruiko", "th": "ซาเต็น รุยิโกะ",
        },
        "anime": {
            "zh-CN": "某科学的超电磁炮", "zh-TW": "某科學的超電磁砲",
            "ja": "とある科学の超電磁砲", "en": "A Certain Scientific Railgun",
            "ko": "어떤 과학의 초전자포",
            "fr": "A Certain Scientific Railgun", "es": "A Certain Scientific Railgun",
            "vi": "A Certain Scientific Railgun", "th": "A Certain Scientific Railgun",
        },
    },
    "shirai_kuroko": {
        "name": {
            "zh-CN": "白井黑子", "zh-TW": "白井黑子",
            "ja": "白井 黒子", "en": "Shirai Kuroko",
            "ko": "시라이 쿠로코",
            "fr": "Shirai Kuroko", "es": "Shirai Kuroko",
            "vi": "Shirai Kuroko", "th": "ชิราอิ คุโระโกะ",
        },
        "anime": {
            "zh-CN": "某科学的超电磁炮", "zh-TW": "某科學的超電磁砲",
            "ja": "とある科学の超電磁砲", "en": "A Certain Scientific Railgun",
            "ko": "어떤 과학의 초전자포",
            "fr": "A Certain Scientific Railgun", "es": "A Certain Scientific Railgun",
            "vi": "A Certain Scientific Railgun", "th": "A Certain Scientific Railgun",
        },
    },
}


# ===== Flask 配置 =====
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 5000
FLASK_DEBUG = True

# ===== 应用配置 =====
# 以下兩項一律從環境變數讀取，不可寫入程式碼（本倉庫為公開倉庫）。
#
# SECRET_KEY 用於簽署 Flask session cookie。一旦洩漏，攻擊者可自行偽造
# session、繞過登入直接取得管理員身分，因此絕不能有已知預設值。
# 未設置時改為每次啟動隨機生成（重啟後既有 session 失效，這是刻意的行為）。
import secrets

SECRET_KEY = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

# ===== 上传配置 =====
MAX_UPLOAD_SIZE = 16 * 1024 * 1024  # 16MB
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "bmp", "webp"}

# ===== 数据库配置 =====
DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "anime_system.db")

# ===== 模型配置 =====
NUM_CLASSES = 19  # 已知角色数量

# ===== 训练超参数（供 train_worker.py 使用）=====
BASE_LR = 1e-4              # 基础学习率
BACKBONE_LR = 1e-5          # 骨干网络学习率（解冻后使用）
WEIGHT_DECAY = 1e-4         # 权重衰减
LABEL_SMOOTHING = 0.1       # 标签平滑
BATCH_SIZE = 32              # 批次大小
NUM_EPOCHS = 15              # 训练轮数
MODEL_BACKBONE = "mobilenet_v2"  # 骨干网络
LOSS_TYPE = "cross_entropy"    # 损失函数类型
EMBEDDING_SIZE = 128         # 嵌入维度（用于对比学习等）
DROPOUT_RATE = 0.5          # Dropout 比率

# ===== 优化器配置 =====
OPTIMIZER = "adam"           # 优化器类型
MOMENTUM = 0.9              # SGD momentum（当 OPTIMIZER="sgd" 时使用）
LR_SCHEDULER = "cosine"      # 学习率调度器
T_WARMUP = 5                 # Warmup 轮数

# ===== 损失函数参数 =====
ARCFACE_SCALE = 30.0        # ArcFace 缩放参数
ARCFACE_MARGIN = 0.5        # ArcFace 边界参数
COSFACE_SCALE = 30.0        # CosFace 缩放参数
COSFACE_MARGIN = 0.35       # CosFace 边界参数
SUPPORTED_LOCALES = ["zh-CN", "zh-TW", "en", "ja", "ko", "fr", "es", "vi", "th"]
DEFAULT_LOCALE = "zh-TW"

# ===== 辅助函数 =====
def get_char_name(char_key, locale="zh-CN"):
    """获取角色名的多语言版本"""
    if char_key in ANIME_CHARACTERS:
        return ANIME_CHARACTERS[char_key]["name"].get(locale, char_key)
    return char_key

def get_anime_name(char_key, locale="zh-CN"):
    """获取番剧名的多语言版本"""
    if char_key in ANIME_CHARACTERS:
        anime = ANIME_CHARACTERS[char_key]["anime"]
        if isinstance(anime, dict):
            return anime.get(locale, "")
        return anime
    return ""

CLASS_NAMES = list(ANIME_CHARACTERS.keys())



def get_char_info_flat(char_key, locale="zh-CN"):
    """
    获取角色信息的扁平格式（兼容旧代码）
    
    Returns:
        {
            "name": "角色名",
            "anime": "番剧名",
            "name_i18n": {...},  # 多语言名称
            "anime_i18n": {...}, # 多语言番剧名
        }
    """
    if char_key not in ANIME_CHARACTERS:
        return None
    
    info = ANIME_CHARACTERS[char_key]
    return {
        "name": get_char_name(char_key, locale),
        "anime": get_anime_name(char_key, locale),
        "name_i18n": info["name"],
        "anime_i18n": info["anime"],
    }
