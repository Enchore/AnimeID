#!/usr/bin/env python3
"""
一次性为 9 个语言 JSON 文件添加所有缺失的翻译键。
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))

NEW_KEYS = {
    # ---- history.html ----
    "history.title":              {"zh-CN":"识别记录","zh-TW":"識別記錄","en":"History","ja":"識別履歴","ko":"인식 기록","fr":"Historique","es":"Historial","vi":"Lịch sử","th":"ประวัติ"},
    "history.subtitle":           {"zh-CN":"共 {n} 条","zh-TW":"共 {n} 筆","en":"{n} records","ja":"{n} 件","ko":"{n}개","fr":"{n} entrées","es":"{n} registros","vi":"{n} bản ghi","th":"{n} รายการ"},
    "history.not_anime":          {"zh-CN":"非动漫","zh-TW":"非動漫","en":"Non-anime","ja":"非アニメ","ko":"비애니","fr":"Non-anime","es":"No anime","vi":"Không anime","th":"ไม่ใช่อนิเมะ"},
    "history.source_qwen":        {"zh-CN":"Qwen AI","zh-TW":"Qwen AI","en":"Qwen AI","ja":"Qwen AI","ko":"Qwen AI","fr":"Qwen AI","es":"Qwen AI","vi":"Qwen AI","th":"Qwen AI"},
    "history.source_local":       {"zh-CN":"本地模型","zh-TW":"本地模型","en":"Local Model","ja":"ローカル","ko":"로컬 모델","fr":"Modèle local","es":"Modelo local","vi":"Mô hình cục bộ","th":"โมเดลท้องถิ่น"},
    "history.empty_title":        {"zh-CN":"暂无识别记录","zh-TW":"尚無識別記錄","en":"No records yet","ja":"記録なし","ko":"기록 없음","fr":"Aucun enregistrement","es":"Sin registros","vi":"Chưa có bản ghi","th":"ยังไม่มีประวัติ"},
    "history.empty_desc":         {"zh-CN":"快去上传第一张图片开始识别吧！","zh-TW":"快去上傳第一張圖片開始識別吧！","en":"Upload your first image to get started!","ja":"最初の画像をアップロードしよう！","ko":"첫 번째 이미지를 업로드해 보세요!","fr":"Téléchargez votre première image !","es":"¡Sube tu primera imagen!","vi":"Hãy tải lên ảnh đầu tiên!","th":"อัปโหลดภาพแรกของคุณ!"},
    "history.upload_btn":         {"zh-CN":"上传图片","zh-TW":"上傳圖片","en":"Upload Image","ja":"画像をアップロード","ko":"이미지 업로드","fr":"Télécharger une image","es":"Subir imagen","vi":"Tải ảnh lên","th":"อัปโหลดภาพ"},
    "history.people":             {"zh-CN":"{n}人","zh-TW":"{n}人","en":"{n} chars","ja":"{n}人","ko":"{n}명","fr":"{n} perso.","es":"{n} pers.","vi":"{n} nhân vật","th":"{n} ตัวละคร"},
    # ---- community.html ----
    "community.title":            {"zh-CN":"社群","zh-TW":"社群","en":"Community","ja":"コミュニティ","ko":"커뮤니티","fr":"Communauté","es":"Comunidad","vi":"Cộng đồng","th":"ชุมชน"},
    "community.subtitle":         {"zh-CN":"发现热门识别、参与讨论、查看排行榜","zh-TW":"發現熱門識別、參與討論、查看排行榜","en":"Discover top identifications, join discussions, view leaderboards","ja":"人気の識別を発見し、ランキングを確認","ko":"인기 인식을 발견하고 토론에 참여하세요","fr":"Découvrez les identifications populaires et les classements","es":"Descubre identificaciones populares y clasificaciones","vi":"Khám phá nhận dạng phổ biến và bảng xếp hạng","th":"ค้นพบการรู้จำยอดนิยมและกระดานผู้นำ"},
    "community.hot_discussion":   {"zh-CN":"热门讨论","zh-TW":"熱門討論","en":"Hot Discussions","ja":"人気の議論","ko":"인기 토론","fr":"Discussions populaires","es":"Discusiones populares","vi":"Thảo luận nổi bật","th":"การสนทนายอดนิยม"},
    "community.leaderboard":      {"zh-CN":"角色人气榜","zh-TW":"角色人氣榜","en":"Character Popularity","ja":"キャラクター人気ランキング","ko":"캐릭터 인기 순위","fr":"Popularité des personnages","es":"Popularidad de personajes","vi":"Bảng xếp hạng nhân vật","th":"ความนิยมของตัวละคร"},
    "community.latest_uploads":   {"zh-CN":"最新上传","zh-TW":"最新上傳","en":"Latest Uploads","ja":"最新のアップロード","ko":"최근 업로드","fr":"Derniers téléchargements","es":"Últimas subidas","vi":"Tải lên mới nhất","th":"อัปโหลดล่าสุด"},
    "community.no_discussion":    {"zh-CN":"暂无讨论，快去识别页添加评论吧","zh-TW":"暫無討論，快去識別頁新增評論吧","en":"No discussions yet. Add a comment on the detail page!","ja":"まだ議論なし","ko":"아직 토론 없음","fr":"Aucune discussion","es":"Sin discusiones aún","vi":"Chưa có thảo luận","th":"ยังไม่มีการสนทนา"},
    "community.no_data":          {"zh-CN":"暂无数据","zh-TW":"暫無資料","en":"No data yet","ja":"データなし","ko":"데이터 없음","fr":"Aucune donnée","es":"Sin datos","vi":"Chưa có dữ liệu","th":"ยังไม่มีข้อมูล"},
    "community.no_uploads":       {"zh-CN":"暂无上传记录","zh-TW":"暫無上傳記錄","en":"No uploads yet","ja":"アップロードなし","ko":"업로드 없음","fr":"Aucun téléchargement","es":"Sin subidas","vi":"Chưa có tải lên","th":"ยังไม่มีการอัปโหลด"},
    "community.browse_wall":      {"zh-CN":"浏览全部角色墙","zh-TW":"瀏覽全部角色牆","en":"Browse Character Wall","ja":"キャラクターウォールを見る","ko":"캐릭터 월 보기","fr":"Voir le mur de personnages","es":"Ver muro de personajes","vi":"Xem bức tường nhân vật","th":"ดูกำแพงตัวละคร"},
    # ---- upload.html ----
    "upload.drag_hint_sub":       {"zh-CN":"或点击选择图片文件","zh-TW":"或點擊選擇圖片檔案","en":"or click to select a file","ja":"またはファイルを選択","ko":"또는 파일 선택","fr":"ou cliquez pour sélectionner","es":"o haz clic para seleccionar","vi":"hoặc nhấp để chọn","th":"หรือคลิกเพื่อเลือก"},
    "upload.formats":             {"zh-CN":"支持 JPG / PNG / WebP / GIF，最大 16MB","zh-TW":"支援 JPG / PNG / WebP / GIF，最大 16MB","en":"JPG / PNG / WebP / GIF, max 16MB","ja":"JPG/PNG/WebP/GIF、最大16MB","ko":"JPG/PNG/WebP/GIF, 최대 16MB","fr":"JPG/PNG/WebP/GIF, max 16 Mo","es":"JPG/PNG/WebP/GIF, máx 16 MB","vi":"JPG/PNG/WebP/GIF, tối đa 16MB","th":"JPG/PNG/WebP/GIF สูงสุด 16MB"},
    "upload.url_label":           {"zh-CN":"图片链接（URL）","zh-TW":"圖片連結（URL）","en":"Image URL","ja":"画像URL","ko":"이미지 URL","fr":"URL de l'image","es":"URL de imagen","vi":"URL ảnh","th":"URL รูปภาพ"},
    "upload.select_file":         {"zh-CN":"选择文件","zh-TW":"選擇檔案","en":"Select File","ja":"ファイル選択","ko":"파일 선택","fr":"Sélectionner","es":"Seleccionar","vi":"Chọn tệp","th":"เลือกไฟล์"},
    "upload.preview_label":       {"zh-CN":"图片预览","zh-TW":"圖片預覽","en":"Preview","ja":"プレビュー","ko":"미리보기","fr":"Aperçu","es":"Vista previa","vi":"Xem trước","th":"ตัวอย่าง"},
    "upload.step1":               {"zh-CN":"上传图片","zh-TW":"上傳圖片","en":"Upload","ja":"アップロード","ko":"업로드","fr":"Télécharger","es":"Subir","vi":"Tải lên","th":"อัปโหลด"},
    "upload.step2":               {"zh-CN":"预览确认","zh-TW":"預覽確認","en":"Preview","ja":"確認","ko":"확인","fr":"Aperçu","es":"Vista previa","vi":"Xem trước","th":"ตัวอย่าง"},
    "upload.step3":               {"zh-CN":"开始识别","zh-TW":"開始識別","en":"Recognize","ja":"識別開始","ko":"인식 시작","fr":"Reconnaître","es":"Reconocer","vi":"Nhận dạng","th":"เริ่มรู้จำ"},
    "upload.analyzing":           {"zh-CN":"AI 正在分析中，请稍候...","zh-TW":"AI 正在分析中，請稍候...","en":"AI is analyzing, please wait...","ja":"AI が分析中...","ko":"AI 분석 중...","fr":"L'IA analyse, veuillez patienter...","es":"La IA está analizando...","vi":"AI đang phân tích...","th":"AI กำลังวิเคราะห์..."},
    "upload.cancel":              {"zh-CN":"取消识别","zh-TW":"取消識別","en":"Cancel","ja":"キャンセル","ko":"취소","fr":"Annuler","es":"Cancelar","vi":"Hủy","th":"ยกเลิก"},
    "upload.or":                  {"zh-CN":"或者","zh-TW":"或者","en":"or","ja":"または","ko":"또는","fr":"ou","es":"o","vi":"hoặc","th":"หรือ"},
    # ---- detail.html ----
    "detail.back":                {"zh-CN":"返回角色墙","zh-TW":"返回角色牆","en":"Back to Wall","ja":"ウォールに戻る","ko":"캐릭터 월로 돌아가기","fr":"Retour au mur","es":"Volver al muro","vi":"Về tường nhân vật","th":"กลับไปยังกำแพง"},
    "detail.continue_upload":     {"zh-CN":"继续上传","zh-TW":"繼續上傳","en":"Upload More","ja":"続けてアップ","ko":"계속 업로드","fr":"Continuer","es":"Seguir subiendo","vi":"Tải thêm","th":"อัปโหลดต่อ"},
    "detail.home":                {"zh-CN":"首页","zh-TW":"首頁","en":"Home","ja":"ホーム","ko":"홈","fr":"Accueil","es":"Inicio","vi":"Trang chủ","th":"หน้าหลัก"},
    "detail.not_anime_title":     {"zh-CN":"非动漫图片","zh-TW":"非動漫圖片","en":"Non-Anime Image","ja":"非アニメ画像","ko":"비애니 이미지","fr":"Image non-anime","es":"Imagen no anime","vi":"Ảnh không phải anime","th":"ไม่ใช่ภาพอนิเมะ"},
    "detail.not_anime_body":      {"zh-CN":"这不是一张动漫图片","zh-TW":"這不是一張動漫圖片","en":"This is not an anime image","ja":"これはアニメ画像ではありません","ko":"이것은 애니메이션 이미지가 아닙니다","fr":"Ce n'est pas une image anime","es":"Esta no es una imagen anime","vi":"Đây không phải ảnh anime","th":"ภาพนี้ไม่ใช่อนิเมะ"},
    "detail.upload_real":         {"zh-CN":"上传真正的动漫角色","zh-TW":"上傳真正的動漫角色","en":"Upload a real anime character","ja":"本物のアニメキャラをアップ","ko":"실제 애니메이션 캐릭터 업로드","fr":"Télécharger un vrai personnage","es":"Sube un personaje real","vi":"Tải ảnh anime thật","th":"อัปโหลดตัวละครอนิเมะจริง"},
    "detail.candidates":          {"zh-CN":"候选结果 Top-5","zh-TW":"候選結果 Top-5","en":"Top-5 Candidates","ja":"上位5候補","ko":"상위 5개 후보","fr":"Top 5 candidats","es":"Top 5 candidatos","vi":"5 ứng viên hàng đầu","th":"5 ตัวเลือกอันดับต้น"},
    "detail.corrected_badge":     {"zh-CN":"已纠错","zh-TW":"已糾錯","en":"Corrected","ja":"修正済","ko":"수정됨","fr":"Corrigé","es":"Corregido","vi":"Đã sửa","th":"แก้ไขแล้ว"},
    "detail.correction_alert":    {"zh-CN":"用户纠错：正确名称可能是","zh-TW":"用戶糾錯：正確名稱可能是","en":"User correction: correct name may be","ja":"ユーザー修正：正しい名前は","ko":"사용자 수정: 올바른 이름은","fr":"Correction : le nom correct serait","es":"Corrección: el nombre correcto podría ser","vi":"Sửa lỗi: tên đúng có thể là","th":"การแก้ไข: ชื่อที่ถูกต้องอาจเป็น"},
    "detail.rec_time":            {"zh-CN":"识别时间","zh-TW":"識別時間","en":"Recognized at","ja":"識別日時","ko":"인식 시각","fr":"Reconnu le","es":"Reconocido el","vi":"Thời gian nhận dạng","th":"เวลาที่รู้จำ"},
    "detail.rec_id":              {"zh-CN":"记录编号","zh-TW":"記錄編號","en":"Record ID","ja":"記録番号","ko":"기록 ID","fr":"ID d'enregistrement","es":"ID de registro","vi":"Mã bản ghi","th":"รหัสบันทึก"},
    "detail.like_accuracy":       {"zh-CN":"识别正确","zh-TW":"識別正確","en":"Correct","ja":"正解","ko":"정확","fr":"Correct","es":"Correcto","vi":"Đúng","th":"ถูกต้อง"},
    "detail.like_character":      {"zh-CN":"喜欢角色","zh-TW":"喜歡角色","en":"Love this char","ja":"このキャラが好き","ko":"이 캐릭터 좋아","fr":"J'aime ce perso","es":"Me gusta este personaje","vi":"Thích nhân vật này","th":"ชอบตัวละครนี้"},
    "detail.correct_btn":         {"zh-CN":"纠错","zh-TW":"糾錯","en":"Correct","ja":"修正","ko":"수정","fr":"Corriger","es":"Corregir","vi":"Sửa lỗi","th":"แก้ไข"},
    "detail.share_btn":           {"zh-CN":"分享","zh-TW":"分享","en":"Share","ja":"シェア","ko":"공유","fr":"Partager","es":"Compartir","vi":"Chia sẻ","th":"แชร์"},
    "detail.correct_title":       {"zh-CN":"识别纠错","zh-TW":"識別糾錯","en":"Correction","ja":"修正","ko":"수정","fr":"Correction","es":"Corrección","vi":"Sửa lỗi","th":"แก้ไขข้อผิดพลาด"},
    "detail.correct_name_label":  {"zh-CN":"正确的角色名称","zh-TW":"正確的角色名稱","en":"Correct character name","ja":"正しいキャラクター名","ko":"올바른 캐릭터 이름","fr":"Nom correct du personnage","es":"Nombre correcto del personaje","vi":"Tên nhân vật đúng","th":"ชื่อตัวละครที่ถูกต้อง"},
    "detail.correct_anime_label": {"zh-CN":"所属作品（可选）","zh-TW":"所屬作品（可選）","en":"Anime title (optional)","ja":"作品名（任意）","ko":"애니 제목 (선택)","fr":"Titre de l'anime (optionnel)","es":"Título del anime (opcional)","vi":"Tên anime (tùy chọn)","th":"ชื่ออนิเมะ (ไม่บังคับ)"},
    "detail.comment_placeholder": {"zh-CN":"写下你的评论...","zh-TW":"寫下你的評論...","en":"Write a comment...","ja":"コメントを入力...","ko":"댓글을 입력하세요...","fr":"Écrire un commentaire...","es":"Escribe un comentario...","vi":"Viết bình luận...","th":"เขียนความคิดเห็น..."},
    "detail.nickname_placeholder":{"zh-CN":"昵称（可选）","zh-TW":"暱稱（可選）","en":"Nickname (optional)","ja":"ニックネーム（任意）","ko":"닉네임 (선택)","fr":"Pseudo (optionnel)","es":"Apodo (opcional)","vi":"Biệt danh (tùy chọn)","th":"ชื่อเล่น (ไม่บังคับ)"},
    "detail.send_comment":        {"zh-CN":"发送","zh-TW":"傳送","en":"Send","ja":"送信","ko":"전송","fr":"Envoyer","es":"Enviar","vi":"Gửi","th":"ส่ง"},
    "detail.no_comment":          {"zh-CN":"还没有评论，来说点什么吧","zh-TW":"還沒有評論，來說點什麼吧","en":"No comments yet. Say something!","ja":"まだコメントなし","ko":"아직 댓글 없음","fr":"Pas encore de commentaires","es":"Sin comentarios aún","vi":"Chưa có bình luận","th":"ยังไม่มีความคิดเห็น"},
    "detail.multi_chars":         {"zh-CN":"多人识别 · 共 {n} 个角色","zh-TW":"多人識別 · 共 {n} 個角色","en":"Multi-char · {n} characters","ja":"複数キャラ · {n}人","ko":"멀티 캐릭터 · {n}명","fr":"Personnages multiples · {n}","es":"Múltiples personajes · {n}","vi":"Nhiều nhân vật · {n}","th":"หลายตัวละคร · {n}"},
    "detail.cancel":              {"zh-CN":"取消","zh-TW":"取消","en":"Cancel","ja":"キャンセル","ko":"취소","fr":"Annuler","es":"Cancelar","vi":"Hủy","th":"ยกเลิก"},
    "detail.submit_correction":   {"zh-CN":"提交纠错","zh-TW":"提交糾錯","en":"Submit Correction","ja":"修正を提出","ko":"수정 제출","fr":"Soumettre la correction","es":"Enviar corrección","vi":"Gửi sửa lỗi","th":"ส่งการแก้ไข"},
    # ---- error.html ----
    "error.back_home":            {"zh-CN":"返回首页","zh-TW":"返回首頁","en":"Back to Home","ja":"ホームに戻る","ko":"홈으로","fr":"Retour à l'accueil","es":"Volver al inicio","vi":"Về trang chủ","th":"กลับหน้าหลัก"},
    "error.desc":                 {"zh-CN":"别担心，去首页看看角色墙吧","zh-TW":"別擔心，去首頁看看角色牆吧","en":"Don't worry, go check the character wall!","ja":"キャラクターウォールへどうぞ","ko":"캐릭터 월을 확인해보세요","fr":"Regardez le mur de personnages","es":"Ve a ver el muro de personajes","vi":"Hãy xem bức tường nhân vật","th":"ดูกำแพงตัวละครได้เลย"},
    # ---- admin pages (static text only, no full i18n since they inherit nothing) ----
    "admin.title":                {"zh-CN":"管理员后台","zh-TW":"管理員後臺","en":"Admin Panel","ja":"管理パネル","ko":"관리 패널","fr":"Panneau d'administration","es":"Panel de administración","vi":"Bảng quản trị","th":"แผงผู้ดูแล"},
    "admin.login_title":          {"zh-CN":"AnimeID 管理员后台","zh-TW":"AnimeID 管理員後臺","en":"AnimeID Admin Panel","ja":"AnimeID 管理パネル","ko":"AnimeID 관리 패널","fr":"Panneau Admin AnimeID","es":"Panel Admin AnimeID","vi":"Bảng quản trị AnimeID","th":"แผงผู้ดูแล AnimeID"},
    "admin.password_label":       {"zh-CN":"管理员密码","zh-TW":"管理員密碼","en":"Admin Password","ja":"管理者パスワード","ko":"관리자 비밀번호","fr":"Mot de passe admin","es":"Contraseña de admin","vi":"Mật khẩu quản trị","th":"รหัสผ่านผู้ดูแล"},
    "admin.login_btn":            {"zh-CN":"登录","zh-TW":"登入","en":"Login","ja":"ログイン","ko":"로그인","fr":"Connexion","es":"Iniciar sesión","vi":"Đăng nhập","th":"เข้าสู่ระบบ"},
    "admin.back_wall":            {"zh-CN":"返回角色墙","zh-TW":"返回角色牆","en":"Back to Wall","ja":"ウォールに戻る","ko":"캐릭터 월로","fr":"Retour au mur","es":"Volver al muro","vi":"Về tường nhân vật","th":"กลับไปยังกำแพง"},
}

LANGS = ["zh-CN","zh-TW","en","ja","ko","fr","es","vi","th"]

for lang in LANGS:
    path = os.path.join(HERE, f"{lang}.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    added = 0
    for key, translations in NEW_KEYS.items():
        if key not in data:
            data[key] = translations.get(lang, translations.get("en", key))
            added += 1
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"{lang}: +{added} keys")

print("Done!")
