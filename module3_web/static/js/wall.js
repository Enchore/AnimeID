/**
 * wall.js - 角色牆交互邏輯
 * 點讚、糾錯 Modal 管理
 */

let _currentCorrectRecordId = null;
let _currentCorrectOriginalName = null;  // 多人糾錯時的原始角色名
let _correctModal = null;

document.addEventListener('DOMContentLoaded', function () {
    _correctModal = new bootstrap.Modal(document.getElementById('correctModal'));
});

/**
 * 點讚介面呼叫（支援 toggle + 角色維度）
 * 核心原則：用 data-char-key 屬性定位同角色按鈕，不依賴 DOM 父子關係
 * @param {number}   recordId - 記錄 ID
 * @param {string}   type     - 點讚類型: "accuracy" 識別正確 / "character" 喜歡角色
 * @param {HTMLElement} btn      - 被點擊的按鈕元素
 * @param {string}  [charKey] - 角色標識（多人識別時傳入，單人/全局模式不傳）
 */
async function likeRecord(recordId, type, btn, charKey) {
    try {
        const body = { type: type || 'accuracy' };
        if (charKey) body.char_key = charKey;

        const res = await fetch(`/api/like/${recordId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await res.json();

        if (!data.success) {
            showToast(data.error || '操作失敗', 'warning');
            return;
        }

        console.log('[likeRecord] raw data:', JSON.stringify(data));
        console.log('[likeRecord] charKey=', charKey, '| data.char=', data.char, '| data.global=', data.global);

        // ── 決定計數來源 ──
        let accCount, charCount;
        if (charKey && data.char) {
            // 角色模式：從 data.char 取該角色獨立計數
            console.log('[likeRecord] 走角色模式，data.char=', JSON.stringify(data.char));
            accCount  = data.char.like_accuracy  || 0;
            charCount = data.char.like_character || 0;
        } else {
            console.warn('[likeRecord] ⚠️ 未走角色模式！charKey=' + charKey + ' data.char=' + JSON.stringify(data.char));
            // 降級：用 global 或頂層欄位
            if (data.global) {
                accCount  = data.global.like_accuracy  || 0;
                charCount = data.global.like_character || 0;
            } else {
                accCount  = data.like_accuracy  || 0;
                charCount = data.like_character || 0;
            }
        }

        if (charKey) {
            // ── 角色模式：用 data-char-key 屬性找到同卡片中該角色的所有按鈕 ──
            const container = btn.closest('.card-back') || btn.closest('.card-back-actions') || btn.closest('.character-card');
            const allTagged = (container || document).querySelectorAll('[data-char-key]');
            const buttons = [];
            for (let i = 0; i < allTagged.length; i++) {
                // 只取 button，排除 .back-char-row 等 div 容器（它們也有 data-char-key）
                if (allTagged[i].tagName === 'BUTTON' && allTagged[i].getAttribute('data-char-key') === charKey) {
                    buttons.push(allTagged[i]);
                }
            }
            console.log('[likeRecord] found buttons for charKey=' + charKey, buttons.length);

            // 用 data-like-type 屬性判斷類型（不再解析 onclick）
            buttons.forEach(function (b) {
                const btnType = (b.getAttribute('data-like-type') || '').toLowerCase();
                const isAccBtn = btnType === 'accuracy';
                _updateLikeBtn(b, isAccBtn, isAccBtn ? accCount : charCount);
            });
        } else if (btn) {
            // ── 全局模式（單人識別）：用 data-like-type 判斷類型 ──
            const clickedType = (btn.getAttribute('data-like-type') || '').toLowerCase();
            const clickedIsAcc = clickedType === 'accuracy';
            _updateLikeBtn(btn, clickedIsAcc, clickedIsAcc ? accCount : charCount);

            // 找同卡片內的另一個按鈕一起更新
            const parent = btn.closest('.card-back-actions') || btn.closest('.card-back-single-actions') || btn.parentElement;
            if (parent) {
                const siblings = parent.querySelectorAll('.action-chip');
                siblings.forEach(function (sib) {
                    if (sib === btn) return;
                    const sibType = (sib.getAttribute('data-like-type') || '').toLowerCase();
                    const sibIsAcc = sibType === 'accuracy';
                    if (sibIsAcc !== clickedIsAcc) {
                        _updateLikeBtn(sib, sibIsAcc, sibIsAcc ? accCount : charCount);
                    }
                });
            }
        }

        // Toast 提示
        const isLiked = data.liked === true;
        if (type === 'accuracy') {
            showToast(isLiked ? '感謝認可識別結果！✓' : '已取消認可', 'success');
        } else {
            showToast(isLiked ? '已標記喜歡該角色！❤️' : '已取消喜歡', 'success');
        }
    } catch (e) {
        console.error('[likeRecord] error', e);
        showToast('網路錯誤，請重試', 'error');
    }
}

/**
 * 更新單個點讚按鈕的圖標和計數
 * @param {HTMLElement} button     - 要更新的按鈕元素
 * @param {boolean}    isAccuracy - true=識別正確 / false=喜歡角色
 * @param {number}     count      - 當前計數
 */
function _updateLikeBtn(button, isAccuracy, count) {
    if (!button) return;
    const icon    = button.querySelector('i');
    const countEl = button.querySelector('.action-count') || button.querySelector('.like-count');

    if (isAccuracy) {
        if (icon) {
            icon.classList.remove('bi-check-circle', 'bi-check-circle-fill');
            icon.classList.add(count > 0 ? 'bi-check-circle-fill' : 'bi-check-circle');
        }
        button.classList.toggle('active-green', count > 0);
        button.classList.remove('active-red');
    } else {
        if (icon) {
            icon.classList.remove('bi-heart', 'bi-heart-fill');
            icon.classList.add(count > 0 ? 'bi-heart-fill' : 'bi-heart');
        }
        button.classList.toggle('active-red', count > 0);
        button.classList.remove('active-green');
    }
    if (countEl) countEl.textContent = count;
}

/**
 * 打開糾錯 Modal（主角色）
 * @param {number} recordId   - 記錄 ID
 * @param {string} currentName - 當前識別名稱
 */
function showCorrectModal(recordId, currentName) {
    _currentCorrectRecordId = recordId;
    _currentCorrectOriginalName = null;  // 主角色糾錯不設 original_name
    const nameEl = document.getElementById('currentCharName');
    if (nameEl) nameEl.textContent = currentName || '未知角色';

    const input = document.getElementById('correctNameInput');
    if (input) input.value = '';

    const animeInput = document.getElementById('correctAnimeInput');
    if (animeInput) animeInput.value = '';

    if (_correctModal) _correctModal.show();
}

/**
 * 打開糾錯 Modal（多人角色中的特定角色）
 * @param {number} recordId  - 記錄 ID
 * @param {string} charName  - 要被糾正的角色名
 * @param {string} charAnime - 當前角色所屬作品（預填）
 */
function showCorrectModalForChar(recordId, charName, charAnime, displayName) {
    _currentCorrectRecordId = recordId;
    _currentCorrectOriginalName = charName;

    const nameEl = document.getElementById('currentCharName');
    if (nameEl) nameEl.textContent = displayName || charName || '未知角色';

    const input = document.getElementById('correctNameInput');
    if (input) input.value = charName;  // 預填原名稱方便微調

    const animeInput = document.getElementById('correctAnimeInput');
    if (animeInput) animeInput.value = charAnime || '';

    if (_correctModal) _correctModal.show();
}

/**
 * 提交糾錯
 */
async function submitCorrection() {
    const correctName = document.getElementById('correctNameInput').value.trim();
    const correctAnime = document.getElementById('correctAnimeInput').value.trim();
    if (!correctName) {
        showToast('請輸入正確的角色名稱', 'warning');
        return;
    }

    try {
        const body = { correct_name: correctName, correct_anime: correctAnime };
        if (_currentCorrectOriginalName) {
            body.original_name = _currentCorrectOriginalName;
        }
        const res = await fetch(`/api/correct/${_currentCorrectRecordId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await res.json();

        if (data.success) {
            _correctModal.hide();
            const extra = data.training_saved ? ' 🎯 已加入訓練集！' : '';
            showToast((data.message || '糾錯已提交！感謝反饋') + extra, 'success');
            setTimeout(() => window.location.reload(), 1200);
        } else {
            showToast(data.error || '提交失敗', 'error');
        }
    } catch (e) {
        showToast('網路錯誤，請重試', 'error');
    }
}

/**
 * 輕量級 Toast 通知（Uiverse 動畫風格）
 * 水平置中、垂直 1/3 處顯示，2s 後自動消失
 * @param {string} message - 消息內容
 * @param {string} type    - 類型: success / error / warning
 */
function showToast(message, type) {
    type = type || 'success';

    // ── 顏色對照表 ──
    var colorMap = {
        success: { line: 'rgba(0,214,143,0.7)',  shadow: 'rgba(0,214,143,0.15)' },
        error:   { line: 'rgba(255,101,132,0.7)', shadow: 'rgba(255,101,132,0.15)' },
        warning: { line: 'rgba(255,183,0,0.7)',   shadow: 'rgba(255,183,0,0.15)' },
    };
    var c = colorMap[type] || colorMap.success;

    // ── 容器：水平置中，垂直 1/3 ──
    var wrapper = document.createElement('div');
    wrapper.style.cssText =
        'position:fixed;' +
        'top:33%;' +
        'left:50%;' +
        'transform:translate(-50%,-50%);' +
        'z-index:9999;' +
        'pointer-events:none;' +
        'opacity:0;' +
        'transition:opacity 0.35s ease;';

    // ── 文字 ──
    var text = document.createElement('span');
    text.textContent = message;
    text.style.cssText =
        'font-size:1.15rem;' +
        'font-weight:600;' +
        'font-style:italic;' +
        'white-space:nowrap;' +
        'display:inline-block;' +
        'position:relative;' +
        'z-index:2;';

    // ── 掃描線（真實 DOM）──
    var line = document.createElement('div');
    line.style.cssText =
        'position:absolute;' +
        'left:0;' +
        'top:0;' +
        'width:100%;' +
        'height:2px;' +
        'background:' + c.line + ';' +
        'z-index:1;' +
        'border-radius:1px;' +
        'filter:none;' +
        'box-shadow:0 0 6px ' + c.shadow + ';' +
        'opacity:1;';

    wrapper.appendChild(line);
    wrapper.appendChild(text);
    document.body.appendChild(wrapper);

    // ── 入場：淡入 ──
    requestAnimationFrame(function () {
        wrapper.style.opacity = '1';
    });

    // ── 掃描線動畫：用 rAF 手動控制（像素值）──
    var startTime = null;
    var duration = 800; // 0.8s 輕快掃描

    function animateScan(timestamp) {
        if (!startTime) startTime = timestamp;
        var elapsed = timestamp - startTime;
        var progress = Math.min(elapsed / duration, 1);

        // ease-in-out 曲線
        var eased = progress < 0.5
            ? 2 * progress * progress
            : 1 - Math.pow(-2 * progress + 2, 2) / 2;

        // 用像素值：wrapper 高度 - 線高度(2px)
        var maxTop = wrapper.offsetHeight - 2;
        line.style.top = Math.round(eased * maxTop) + 'px';

        if (progress < 1) {
            requestAnimationFrame(animateScan);
        } else {
            // 到達底部後淡出掃描線
            line.style.transition = 'opacity 0.3s ease';
            line.style.opacity = '0';
        }
    }
    // 等 DOM 渲染完再開始動畫
    requestAnimationFrame(function () {
        requestAnimationFrame(animateScan);
    });

    // ── 動畫結束後整體淡出 ──
    setTimeout(function () {
        wrapper.style.transition = 'opacity 0.2s ease';
        wrapper.style.opacity = '0';
        setTimeout(function () {
            if (wrapper.parentNode) wrapper.parentNode.removeChild(wrapper);
        }, 200);
    }, duration + 100);
}
