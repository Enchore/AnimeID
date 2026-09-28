"""为所有语言文件添加主页和角色墙的新 i18n 键"""
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))

# 各语言翻译（按 key 组织）
translations = {
    "home.subtitle": {
        "zh-TW": "上傳任意動漫截圖，AI 即刻告訴你角色名稱與出處作品<br>支援數千動漫角色，準確率領先",
        "zh-CN": "上传任意动漫截图，AI 即刻告诉你角色名称与出处作品<br>支持数千动漫角色，准确率领先",
        "en": "Upload any anime screenshot, AI instantly identifies character name and series<br>Supports thousands of anime characters with leading accuracy",
        "ja": "任意のアニメスクリーンショットをアップロードすると、AIがキャラクター名と作品を即座に識別<br>数千のアニメキャラクターに対応、最高水準の精度",
        "ko": "애니메이션 스크린샷을 업로드하면 AI가 캐릭터 이름과 작품을 즉시 식별<br>수천 개의 애니메이션 캐릭터 지원, 업계 최고 정확도",
        "fr": "Téléchargez n'importe quelle capture d'écran d'anime, l'IA identifie instantanément le personnage et la série<br>Prend en charge des milliers de personnages avec une précision de pointe",
        "es": "Sube cualquier captura de anime, la IA identifica al instante el personaje y la serie<br>Soporta miles de personajes de anime con precisión líder",
        "vi": "Tải lên bất kỳ ảnh chụp màn hình anime nào, AI nhận diện ngay tên nhân vật và tác phẩm<br>Hỗ trợ hàng nghìn nhân vật anime với độ chính xác hàng đầu",
        "th": "อัปโหลดภาพหน้าจออนิเมะ AI ระบุชื่อตัวละครและเรื่องได้ทันที<br>รองรับตัวละครอนิเมะนับพันด้วยความแม่นยำชั้นนำ",
    },
    "home.scan_btn": {
        "zh-TW": "📷 立即識別",
        "zh-CN": "📷 立即识别",
        "en": "📷 Identify Now",
        "ja": "📷 今すぐ識別",
        "ko": "📷 지금 식별하기",
        "fr": "📷 Identifier maintenant",
        "es": "📷 Identificar ahora",
        "vi": "📷 Nhận diện ngay",
        "th": "📷 ระบุทันที",
    },
    "home.scan_hint": {
        "zh-TW": "支援拖拽、粘貼或粘貼鏈接",
        "zh-CN": "支持拖拽、粘贴或粘贴链接",
        "en": "Supports drag & drop, paste, or URL link",
        "ja": "ドラッグ＆ドロップ、貼り付け、URLリンクに対応",
        "ko": "드래그 앤 드롭, 붙여넣기, URL 링크 지원",
        "fr": "Glisser-déposer, coller ou lien URL pris en charge",
        "es": "Soporta arrastrar y soltar, pegar o enlace URL",
        "vi": "Hỗ trợ kéo thả, dán hoặc liên kết URL",
        "th": "รองรับการลากและวาง วาง หรือลิงก์ URL",
    },
    "home.feat1_title": {
        "zh-TW": "🔍 AI 精準識別",
        "zh-CN": "🔍 AI 精准识别",
        "en": "🔍 AI-Powered Recognition",
        "ja": "🔍 AI高精度認識",
        "ko": "🔍 AI 정밀 인식",
        "fr": "🔍 Reconnaissance IA de précision",
        "es": "🔍 Reconocimiento preciso con IA",
        "vi": "🔍 Nhận diện chính xác bằng AI",
        "th": "🔍 การรู้จำด้วย AI แม่นยำ",
    },
    "home.feat1_desc": {
        "zh-TW": "基於深度學習的 ResNet-50 + ArcFace 架構，配合 Qwen-VL 大模型，精準識別動漫角色與出處",
        "zh-CN": "基于深度学习的 ResNet-50 + ArcFace 架构，配合 Qwen-VL 大模型，精准识别动漫角色与出处",
        "en": "Deep learning powered ResNet-50 + ArcFace architecture with Qwen-VL large model for accurate anime character and series recognition",
        "ja": "深層学習ベースの ResNet-50 + ArcFace アーキテクチャに Qwen-VL 大規模モデルを組み合わせ、アニメキャラクターと作品を高精度に識別",
        "ko": "딥러닝 기반 ResNet-50 + ArcFace 아키텍처와 Qwen-VL 대형 모델을 결합하여 애니메이션 캐릭터와 작품을 정밀하게 식별",
        "fr": "Architecture ResNet-50 + ArcFace basée sur le deep learning avec le grand modèle Qwen-VL pour une reconnaissance précise des personnages et séries d'anime",
        "es": "Arquitectura ResNet-50 + ArcFace basada en deep learning con el modelo grande Qwen-VL para un reconocimiento preciso de personajes y series de anime",
        "vi": "Kiến trúc ResNet-50 + ArcFace dựa trên học sâu kết hợp với mô hình lớn Qwen-VL để nhận diện chính xác nhân vật và tác phẩm anime",
        "th": "สถาปัตยกรรม ResNet-50 + ArcFace ที่ใช้การเรียนรู้เชิงลึก ผสานกับโมเดลขนาดใหญ่ Qwen-VL เพื่อการรู้จำตัวละครและเรื่องอนิเมะอย่างแม่นยำ",
    },
    "home.feat2_title": {
        "zh-TW": "⚡ 秒速響應",
        "zh-CN": "⚡ 秒速响应",
        "en": "⚡ Instant Response",
        "ja": "⚡ 瞬時レスポンス",
        "ko": "⚡ 즉시 응답",
        "fr": "⚡ Réponse instantanée",
        "es": "⚡ Respuesta instantánea",
        "vi": "⚡ Phản hồi tức thì",
        "th": "⚡ ตอบสนองทันที",
    },
    "home.feat2_desc": {
        "zh-TW": "上傳截圖即可獲得結果，無需複雜操作，讓你專注於欣賞動漫的樂趣",
        "zh-CN": "上传截图即可获得结果，无需复杂操作，让你专注于欣赏动漫的乐趣",
        "en": "Get results instantly after uploading a screenshot — no complex steps needed, just enjoy anime",
        "ja": "スクリーンショットをアップロードするだけで結果が得られ、複雑な操作は不要。アニメを楽しむことに集中できます",
        "ko": "스크린샷을 업로드하면 바로 결과를 얻을 수 있으며, 복잡한 조작 없이 애니메이션 감상에 집중할 수 있습니다",
        "fr": "Obtenez des résultats instantanément après avoir téléchargé une capture d'écran — aucune étape complexe, profitez simplement de l'anime",
        "es": "Obtén resultados al instante tras subir una captura — sin pasos complejos, solo disfruta del anime",
        "vi": "Nhận kết quả ngay sau khi tải lên ảnh chụp màn hình — không cần thao tác phức tạp, chỉ cần tận hưởng anime",
        "th": "รับผลลัพธ์ทันทีหลังจากอัปโหลดภาพหน้าจอ — ไม่มีขั้นตอนซับซ้อน เพียงแค่เพลิดเพลินกับอนิเมะ",
    },
    "home.feat3_title": {
        "zh-TW": "🌐 開放識別",
        "zh-CN": "🌐 开放识别",
        "en": "🌐 Open Recognition",
        "ja": "🌐 オープン認識",
        "ko": "🌐 개방형 인식",
        "fr": "🌐 Reconnaissance ouverte",
        "es": "🌐 Reconocimiento abierto",
        "vi": "🌐 Nhận diện mở",
        "th": "🌐 การรู้จำแบบเปิด",
    },
    "home.feat3_desc": {
        "zh-TW": "不僅限於已知角色庫，AI 可識別海量動漫作品中的任意角色，持續學習進化",
        "zh-CN": "不仅限于已知角色库，AI 可识别海量动漫作品中的任意角色，持续学习进化",
        "en": "Not limited to known character database — AI can recognize any character from countless anime series, continuously learning and evolving",
        "ja": "既知のキャラクターデータベースに限定されず、AIは無数のアニメ作品からあらゆるキャラクターを認識し、継続的に学習・進化します",
        "ko": "알려진 캐릭터 데이터베이스에 국한되지 않고, AI는 수많은 애니메이션 작품의 모든 캐릭터를 인식하며 지속적으로 학습하고 진화합니다",
        "fr": "Non limité à la base de données de personnages connus — l'IA peut reconnaître n'importe quel personnage de nombreuses séries d'anime, en apprenant et évoluant continuellement",
        "es": "No limitado a la base de datos de personajes conocidos — la IA puede reconocer cualquier personaje de innumerables series de anime, aprendiendo y evolucionando continuamente",
        "vi": "Không giới hạn ở cơ sở dữ liệu nhân vật đã biết — AI có thể nhận diện bất kỳ nhân vật nào từ vô số tác phẩm anime, liên tục học hỏi và phát triển",
        "th": "ไม่จำกัดเฉพาะฐานข้อมูลตัวละครที่รู้จัก — AI สามารถรู้จำตัวละครใดๆ จากผลงานอนิเมะนับไม่ถ้วน เรียนรู้และพัฒนาอย่างต่อเนื่อง",
    },
    "home.panel_back": {
        "zh-TW": "返回主頁",
        "zh-CN": "返回主页",
        "en": "Back to Home",
        "ja": "ホームに戻る",
        "ko": "홈으로 돌아가기",
        "fr": "Retour à l'accueil",
        "es": "Volver al inicio",
        "vi": "Quay lại trang chủ",
        "th": "กลับสู่หน้าหลัก",
    },
    "home.panel_title": {
        "zh-TW": "識別動漫角色",
        "zh-CN": "识别动漫角色",
        "en": "Identify Anime Character",
        "ja": "アニメキャラクターを識別",
        "ko": "애니메이션 캐릭터 식별",
        "fr": "Identifier un personnage d'anime",
        "es": "Identificar personaje de anime",
        "vi": "Nhận diện nhân vật anime",
        "th": "ระบุตัวละครอนิเมะ",
    },
    "wall.empty_title": {
        "zh-TW": "角色牆空空如也",
        "zh-CN": "角色墙空空如也",
        "en": "Character Wall is Empty",
        "ja": "キャラクターウォールは空です",
        "ko": "캐릭터 월이 비어 있습니다",
        "fr": "Le mur des personnages est vide",
        "es": "El muro de personajes está vacío",
        "vi": "Tường nhân vật trống trơn",
        "th": "กำแพงตัวละครว่างเปล่า",
    },
    "wall.empty_desc": {
        "zh-TW": "快去上傳第一張動漫角色圖片吧！",
        "zh-CN": "快去上传第一张动漫角色图片吧！",
        "en": "Go upload your first anime character image!",
        "ja": "最初のアニメキャラクター画像をアップロードしましょう！",
        "ko": "첫 번째 애니메이션 캐릭터 이미지를 업로드하세요!",
        "fr": "Téléchargez votre première image de personnage d'anime !",
        "es": "¡Sube tu primera imagen de personaje de anime!",
        "vi": "Hãy tải lên hình ảnh nhân vật anime đầu tiên của bạn!",
        "th": "ไปอัปโหลดภาพตัวละครอนิเมะภาพแรกของคุณกันเถอะ!",
    },
    "wall.sidebar_title": {
        "zh-TW": "識別記錄",
        "zh-CN": "识别记录",
        "en": "Recognition History",
        "ja": "認識履歴",
        "ko": "인식 기록",
        "fr": "Historique de reconnaissance",
        "es": "Historial de reconocimiento",
        "vi": "Lịch sử nhận diện",
        "th": "ประวัติการรู้จำ",
    },
    "wall.view_all": {
        "zh-TW": "全部 →",
        "zh-CN": "全部 →",
        "en": "View All →",
        "ja": "すべて →",
        "ko": "전체 보기 →",
        "fr": "Voir tout →",
        "es": "Ver todo →",
        "vi": "Xem tất cả →",
        "th": "ดูทั้งหมด →",
    },
    "wall.no_records": {
        "zh-TW": "暫無識別記錄",
        "zh-CN": "暂无识别记录",
        "en": "No recognition records yet",
        "ja": "認識記録はまだありません",
        "ko": "아직 인식 기록이 없습니다",
        "fr": "Aucun enregistrement de reconnaissance",
        "es": "Aún no hay registros de reconocimiento",
        "vi": "Chưa có bản ghi nhận diện nào",
        "th": "ยังไม่มีบันทึกการรู้จำ",
    },
}

def add_keys_to_file(filepath):
    lang_code = os.path.basename(filepath).replace('.json', '')
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    added = 0
    for key, trans in translations.items():
        if key not in data:
            data[key] = trans.get(lang_code, trans.get('en', key))
            added += 1
    
    # 排序：_meta 始终第一，其余按字母排序
    ordered = {}
    if '_meta' in data:
        ordered['_meta'] = data.pop('_meta')
    
    for k in sorted(data.keys()):
        ordered[k] = data[k]
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(ordered, f, ensure_ascii=False, indent=2)
        f.write('\n')
    
    return added

if __name__ == '__main__':
    for fname in sorted(os.listdir(BASE)):
        if fname.endswith('.json'):
            fpath = os.path.join(BASE, fname)
            added = add_keys_to_file(fpath)
            print(f"  {fname}: +{added} keys, total={len(json.load(open(fpath, encoding='utf-8')))}")

    print("\n✓ Done!")
