# ==============================
# 管理員記錄管理（識別記錄 CRUD）
# ==============================

@app.route("/admin/records")
@admin_required
def admin_records():
    """管理員記錄管理頁面"""
    return render_template("admin_records.html")


@app.route("/api/admin/records", methods=["GET"])
@admin_required
def api_admin_list_records():
    """列出所有識別記錄（支援搜尋/分頁）"""
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    search = request.args.get("search", "").strip()
    source = request.args.get("source", "").strip()

    query = RecognitionRecord.query

    if search:
        like_pattern = f"%{search}%"
        query = query.filter(
            db.or_(
                RecognitionRecord.top1_character_name.like(like_pattern),
                RecognitionRecord.top1_anime.like(like_pattern),
                RecognitionRecord.uuid.like(like_pattern),
            )
        )

    if source:
        query = query.filter(RecognitionRecord.recognition_source == source)

    query = query.order_by(RecognitionRecord.id.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    records = []
    for r in pagination.items:
        records.append({
            "id": r.id,
            "uuid": r.uuid,
            "image_filename": r.image_filename,
            "image_url": r.image_url or f"/uploads/{r.image_filename}",
            "top1_character_name": r.top1_character_name,
            "top1_anime": r.top1_anime,
            "top1_confidence": r.top1_confidence,
            "recognition_source": r.recognition_source,
            "like_accuracy": r.like_accuracy,
            "like_character": r.like_character,
            "corrections": r.corrections,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return jsonify({
        "success": True,
        "records": records,
        "total": pagination.total,
        "page": page,
        "per_page": per_page,
        "pages": pagination.pages,
    })


@app.route("/api/admin/records/<int:record_id>", methods=["DELETE"])
@admin_required
def api_admin_delete_record(record_id: int):
    """刪除識別記錄（同時刪除圖片檔案）"""
    record = RecognitionRecord.query.get_or_404(record_id)

    # 刪除圖片檔案
    try:
        image_path = os.path.join(app.config["UPLOAD_FOLDER"], record.image_filename)
        if os.path.exists(image_path):
            os.remove(image_path)
            logger.info(f"已刪除圖片檔案: {image_path}")
    except Exception as e:
        logger.warning(f"刪除圖片檔案失敗: {e}")

    # 同時刪除相關的 PendingReview
    try:
        reviews = PendingReview.query.filter_by(record_id=record_id).all()
        for rv in reviews:
            db.session.delete(rv)
    except Exception:
        pass

    db.session.delete(record)
    db.session.commit()

    log_action("admin_delete_record", record_id=record_id)
    logger.info(f"管理員刪除記錄: record_id={record_id}, {record.top1_character_name}")

    return jsonify({"success": True, "message": f"已刪除記錄 #{record_id}"})


@app.route("/api/admin/records/<int:record_id>", methods=["PUT"])
@admin_required
def api_admin_update_record(record_id: int):
    """編輯識別記錄的角色資訊（前台顯示的名稱/作品）"""
    record = RecognitionRecord.query.get_or_404(record_id)
    data = request.get_json(silent=True) or {}

    changed = []
    new_name = data.get("top1_character_name", "").strip()
    new_anime = data.get("top1_anime", "").strip()

    if new_name and new_name != record.top1_character_name:
        old_name = record.top1_character_name
        record.top1_character_name = new_name
        try:
            from module2_model.qwen_recognizer import _resolve_character_key
            record.top1_character_key = _resolve_character_key(new_name)
        except Exception:
            pass
        changed.append(f"name: {old_name} → {new_name}")

    if "top1_anime" in data:
        old_anime = record.top1_anime
        record.top1_anime = new_anime or None
        changed.append(f"anime: {old_anime} → {new_anime}")

    if changed:
        db.session.commit()
        log_action("admin_update_record", record_id=record_id, detail={"changes": changed})
        logger.info(f"管理員更新記錄: record_id={record_id}, {', '.join(changed)}")
        return jsonify({"success": True, "message": "已更新", "changes": changed})

    return jsonify({"success": False, "error": "未偵測到變更"}), 400
