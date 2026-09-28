/**
 * i18n.js - AnimeID 多語言引擎
 *
 * 功能：
 * - 從 /static/i18n/<lang>.json 載入翻譯
 * - 通過 data-i18n 屬性自動翻譯頁面
 * - 語言偏好保存在 cookie (animeid_lang)
 * - 支援 ?lang=xx 切換語言
 * - 支援 data-i18n-params JSON 屬性傳遞參數給 t()
 *
 * 用法：
 * 1. 在 <html> 標籤添加：<html lang="zh-TW">
 * 2. 在需要翻譯的元素添加：data-i18n="nav.character_wall"
 * 3. 需要參數時：data-i18n="history.subtitle" data-i18n-params='{"total": 42}'
 * 4. 在 base.html 引入：<script src="{{ url_for('static', filename='js/i18n.js') }}"></script>
 */

// ===== 當前語言 =====
let _currentLang = null;
let _translations = null;
let _fallbackTranslations = null; // English fallback
let _loading = false;

// 支援的語言
const SUPPORTED_LANGS = [
    { code: 'zh-TW', label: '繁體中文', flag: '🇹🇼' },
    { code: 'zh-CN', label: '简体中文', flag: '🇨🇳' },
    { code: 'en',      label: 'English',  flag: '🇺🇸' },
    { code: 'ja',      label: '日本語',   flag: '🇯🇵' },
    { code: 'ko',      label: '한국어',   flag: '🇰🇷' },
    { code: 'fr',      label: 'Français', flag: '🇫🇷' },
    { code: 'es',      label: 'Español',  flag: '🇪🇸' },
    { code: 'vi',      label: 'Tiếng Việt', flag: '🇻🇳' },
    { code: 'th',      label: 'ไทย',      flag: '🇹🇭' },
];

// ===== Cookie 工具 =====
function getCookie(name) {
    const m = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return m ? decodeURIComponent(m[2]) : null;
}

function setCookie(name, value, days = 365) {
    const d = new Date();
    d.setTime(d.getTime() + days * 24 * 60 * 60 * 1000);
    document.cookie = `${name}=${encodeURIComponent(value)};expires=${d.toUTCString()};path=/`;
}

// ===== 獲取當前語言 =====
function detectLang() {
    // 1. ?lang=xx 參數最高優先權
    const params = new URLSearchParams(window.location.search);
    if (params.has('lang')) {
        const l = params.get('lang');
        if (SUPPORTED_LANGS.find(x => x.code === l)) {
            setCookie('animeid_lang', l);
            return l;
        }
    }
    // 2. Cookie
    const cookieLang = getCookie('animeid_lang');
    if (cookieLang && SUPPORTED_LANGS.find(x => x.code === cookieLang)) {
        return cookieLang;
    }
    // 3. HTML lang 屬性
    const htmlLang = document.documentElement.lang;
    if (htmlLang && SUPPORTED_LANGS.find(x => x.code === htmlLang)) {
        return htmlLang;
    }
    // 4. 瀏覽器語言（取前兩位）
    const navLang = (navigator.language || navigator.userLanguage || '').split('-')[0];
    const matched = SUPPORTED_LANGS.find(x => x.code.startsWith(navLang));
    if (matched) return matched.code;
    // 5. 預設
    return 'zh-TW';
}

// ===== 載入翻譯 JSON =====
async function loadTranslations(lang) {
    if (_translations && _currentLang === lang) return _translations;
    _loading = true;
    try {
        // 並行載入英文降級翻譯（非英文語言時）
        let fallbackPromise = null;
        if (lang !== 'en' && !_fallbackTranslations) {
            fallbackPromise = fetch(`/static/i18n/en.json`)
                .then(r => r.ok ? r.json() : null)
                .then(data => { _fallbackTranslations = data; })
                .catch(() => {});
        }
        const resp = await fetch(`/static/i18n/${lang}.json`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        _translations = await resp.json();
        _currentLang = lang;
        if (fallbackPromise) await fallbackPromise;
        return _translations;
    } catch (e) {
        console.warn(`[i18n] 載入語言 ${lang} 失敗:`, e);
        if (lang !== 'en') return loadTranslations('en');
        return null;
    } finally {
        _loading = false;
    }
}

// ===== 翻譯函數 =====
function t(key, params = null) {
    if (!_translations && !_fallbackTranslations) return key;
    let text = (_translations && _translations[key])
                || (_fallbackTranslations && _fallbackTranslations[key])
                || key;
    // 支援簡單參數替換：t("hello", {name: "World"}) → "hello".replace("{name}", "World")
    if (params && typeof params === 'object') {
        for (const [k, v] of Object.entries(params)) {
            text = text.replace(new RegExp(`\\{${k}\\}`, 'g'), v);
        }
    }
    return text;
}

// ===== 套用翻譯到頁面 =====
function applyTranslations() {
    if (!_translations && !_fallbackTranslations) return;
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');

        // 檢查是否帶參數
        let text;
        const paramsAttr = el.getAttribute('data-i18n-params');
        if (paramsAttr) {
            try {
                const params = JSON.parse(paramsAttr);
                text = t(key, params);
            } catch (e) {
                console.warn('[i18n] 無效的 data-i18n-params:', paramsAttr);
                text = t(key);
            }
        } else {
            text = t(key);
        }

        // 根據元素類型設定文字
        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
            if (el.placeholder) el.placeholder = text;
        } else if (el.tagName === 'IMG') {
            if (el.alt) el.alt = text;
        } else {
            // 保留子元素（如图標），只替換文字節點
            let found = false;
            for (const node of el.childNodes) {
                if (node.nodeType === Node.TEXT_NODE && node.textContent.trim()) {
                    node.textContent = node.textContent.replace(node.textContent.trim(), text);
                    found = true;
                    break;
                }
            }
            if (!found) el.textContent = text;
        }
    });

    // 處理 data-i18n-placeholder（翻譯 placeholder）
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        el.placeholder = t(key);
    });

    // 更新 html lang 屬性
    document.documentElement.lang = _currentLang;
}

// ===== 切換語言 =====
async function switchLang(lang) {
    if (!SUPPORTED_LANGS.find(x => x.code === lang)) {
        console.warn(`[i18n] 不支援的語言: ${lang}`);
        return;
    }
    setCookie('animeid_lang', lang);
    
    // 先嘗試載入翻譯並套用 UI（讓使用者看到即時反饋）
    await loadTranslations(lang);
    applyTranslations();
    // 更新選擇器（如果存在）
    const switcher = document.getElementById('langSwitcher');
    if (switcher) switcher.value = lang;
    // 更新導航欄語言按鈕
    updateLangButton(lang);
    console.log(`[i18n] 已切換到: ${lang}`);
    
    // 重新整理頁面，讓伺服器端用新語系重新渲染內容（角色名、作品名等）
    window.location.reload();
}

// ===== 更新語言按鈕顯示 =====
function updateLangButton(lang) {
    const info = SUPPORTED_LANGS.find(x => x.code === lang);
    if (!info) return;
    // 頁腳語言按鈕
    const footerFlagEl = document.getElementById('footerLangFlag');
    if (footerFlagEl) footerFlagEl.textContent = info.flag;
    // 高亮當前語言（頁腳選單）
    document.querySelectorAll('#footerLangMenu .footer-lang-option').forEach(el => {
        el.classList.toggle('active', el.getAttribute('data-lang') === lang);
    });
}

// ===== 初始化 =====
async function initI18n() {
    const lang = detectLang();
    await loadTranslations(lang);
    applyTranslations();
    // 更新語言按鈕
    updateLangButton(lang);
    // 填滿語言選擇器
    const switcher = document.getElementById('langSwitcher');
    if (switcher) {
        switcher.value = lang;
        switcher.addEventListener('change', (e) => switchLang(e.target.value));
    }
    // 觸發 i18n:ready 事件，讓需要動態翻譯的頁面可以監聽
    document.dispatchEvent(new CustomEvent('i18n:ready', { detail: { lang } }));
}

// 頁面載入後自動初始化
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initI18n);
} else {
    initI18n();
}

// ===== 匯出全域 API =====
window.i18n = {
    t,
    switchLang,
    getCurrentLang: () => _currentLang,
    getSupportedLangs: () => SUPPORTED_LANGS,
    reload: initI18n,
};
