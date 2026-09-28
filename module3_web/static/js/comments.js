/**
 * comments.js - 評論互動邏輯（支援多語言）
 * 支援：評論列表、發表評論、回覆、點讚
 */

/**
 * 載入評論列表
 */
async function loadComments(recordId) {
    try {
        const res = await fetch(`/api/comments/${recordId}`);
        const data = await res.json();
        if (!data.success) return;

        document.getElementById('commentCount').textContent = data.count;
        const list = document.getElementById('commentList');
        const empty = document.getElementById('commentEmpty');

        if (data.comments.length === 0) {
            list.innerHTML = '';
            empty.classList.remove('d-none');
            return;
        }

        empty.classList.add('d-none');
        list.innerHTML = data.comments.map(c => renderComment(c)).join('');
    } catch (e) {
        console.error(i18n.t('detail.network_error'), e);
    }
}

/**
 * 渲染單條評論（遞迴包含回覆）
 */
function renderComment(c, isReply = false) {
    const rawName = c.username || i18n.t('detail.anonymous_name');
    const name = escapeHtml(rawName);
    const time = formatTime(c.created_at);
    const avatar = (rawName).charAt(0);

    let html = `
    <div class="comment-item ${isReply ? 'comment-child' : ''}" id="comment-${c.id}">
        <div class="comment-header">
            <div class="comment-avatar">${escapeHtml(avatar)}</div>
            <strong style="color:var(--text-primary);font-size:0.88rem;">${name}</strong>
            <span class="comment-meta">· ${time}</span>
        </div>
        <div class="comment-content">${escapeHtml(c.content)}</div>
        <div class="comment-actions">
            <button class="comment-action-btn" onclick="likeComment(${c.id}, this)">
                <i class="bi bi-hand-thumbs-up"></i> <span class="like-cnt">${c.likes || 0}</span>
            </button>
            <button class="comment-action-btn" onclick="showReplyForm(${c.id}, this)">
                <i class="bi bi-reply"></i> ${i18n.t('detail.reply')}
            </button>
        </div>
        <div class="comment-reply-form" id="replyForm-${c.id}">
            <textarea class="comment-input" rows="2" placeholder="${i18n.t('detail.reply_placeholder', { name: rawName })}"></textarea>
            <button class="btn btn-primary btn-sm rounded-pill px-3" onclick="submitReply(${c.id}, this)">
                <i class="bi bi-send"></i>
            </button>
        </div>
    `;

    // 渲染子回覆
    if (c.replies && c.replies.length > 0) {
        html += c.replies.map(r => renderComment(r, true)).join('');
    }

    html += '</div>';
    return html;
}

/**
 * 發表評論
 */
async function submitComment() {
    const input = document.getElementById('commentInput');
    const content = input.value.trim();
    if (!content) return;

    const username = document.getElementById('commentUsername').value.trim() || i18n.t('detail.anonymous_name');

    try {
        const res = await fetch('/api/comments', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                record_id: RECORD_ID,
                content: content,
                username: username,
            }),
        });
        const data = await res.json();

        if (data.success) {
            input.value = '';
            loadComments(RECORD_ID);
        } else {
            alert(data.error || i18n.t('detail.comment_error'));
        }
    } catch (e) {
        alert(i18n.t('detail.network_error'));
    }
}

/**
 * 展開回覆表單
 */
function showReplyForm(commentId, btn) {
    const form = document.getElementById('replyForm-' + commentId);
    if (form) {
        form.classList.toggle('show');
        if (form.classList.contains('show')) {
            form.querySelector('textarea').focus();
        }
    }
}

/**
 * 提交回覆
 */
async function submitReply(parentId, btn) {
    const form = btn.closest('.comment-reply-form');
    const textarea = form.querySelector('textarea');
    const content = textarea.value.trim();
    if (!content) return;

    try {
        const res = await fetch('/api/comments', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                record_id: RECORD_ID,
                parent_id: parentId,
                content: content,
            }),
        });
        const data = await res.json();

        if (data.success) {
            textarea.value = '';
            loadComments(RECORD_ID);
        } else {
            alert(data.error || i18n.t('detail.reply_error'));
        }
    } catch (e) {
        alert(i18n.t('detail.network_error'));
    }
}

/**
 * 點讚評論
 */
async function likeComment(commentId, btn) {
    try {
        const res = await fetch(`/api/comments/${commentId}/like`, { method: 'POST' });
        const data = await res.json();

        if (data.success) {
            const cnt = btn.querySelector('.like-cnt');
            cnt.textContent = data.likes;
            btn.classList.add('liked');
        }
    } catch (e) {
        console.error(i18n.t('detail.network_error'), e);
    }
}

/**
 * 格式化時間（支援多語言）
 */
function formatTime(isoString) {
    if (!isoString) return '';
    const d = new Date(isoString);
    const now = new Date();
    const diff = now - d;
    if (diff < 60000) return i18n.t('detail.time_just_now');
    if (diff < 3600000) return i18n.t('detail.time_minutes_ago', { n: Math.floor(diff / 60000) });
    if (diff < 86400000) return i18n.t('detail.time_hours_ago', { n: Math.floor(diff / 3600000) });
    if (diff < 604800000) return i18n.t('detail.time_days_ago', { n: Math.floor(diff / 86400000) });
    return d.toLocaleDateString(i18n.getCurrentLang());
}

/**
 * HTML 轉義
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
