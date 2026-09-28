/**
 * upload.js - 上传识别页面逻辑（重设计版）
 * 支持：文件拖拽、点击选择、URL输入、预览、识别请求、结果跳转
 * 新增：步骤指示器联动
 */

const uploadZone = document.getElementById('uploadZone');
const imageInput = document.getElementById('imageInput');
const previewSection = document.getElementById('previewSection');
const previewImage = document.getElementById('previewImage');
const loadingSection = document.getElementById('loadingSection');
const errorContainer = document.getElementById('errorContainer');

let _selectedFile = null;
let _abortController = null;
let _cancelTimer = null;

// ===== 步骤指示器 =====
function setStep(n) {
    document.querySelectorAll('.step').forEach(s => s.classList.remove('active'));
    const el = document.getElementById('step' + n);
    if (el) el.classList.add('active');
}

// ===== 拖拽事件 =====
uploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadZone.classList.add('drag-over');
});

uploadZone.addEventListener('dragleave', (e) => {
    // 只有当鼠标真正离开区域时才移除样式
    if (!uploadZone.contains(e.relatedTarget)) {
        uploadZone.classList.remove('drag-over');
    }
});

uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('drag-over');
    const files = e.dataTransfer.files;
    if (files.length > 0) handleFileSelect(files[0]);
});

// 点击上传区域触发文件选择
uploadZone.addEventListener('click', (e) => {
    if (e.target.tagName !== 'BUTTON' && !e.target.closest('button')) {
        imageInput.click();
    }
});

// 文件选择变化
imageInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) handleFileSelect(e.target.files[0]);
});

/**
 * 处理文件选择
 */
function handleFileSelect(file) {
    // 验证文件类型
    const validTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
    if (!validTypes.includes(file.type)) {
        showUploadError('仅支持 JPG / PNG / WebP / GIF 格式');
        return;
    }

    // 验证文件大小（16MB）
    if (file.size > 16 * 1024 * 1024) {
        showUploadError('文件过大，最大支持 16MB');
        return;
    }

    _selectedFile = file;

    // 显示预览
    const reader = new FileReader();
    reader.onload = (e) => {
        previewImage.src = e.target.result;
        uploadZone.classList.add('d-none');
        previewSection.classList.remove('d-none');
        setStep(2);
    };
    reader.readAsDataURL(file);
}

/**
 * 清除预览
 */
function clearPreview() {
    _selectedFile = null;
    previewImage.src = '';
    imageInput.value = '';
    previewSection.classList.add('d-none');
    uploadZone.classList.remove('d-none');
    setStep(1);
}

// ===== 请求工具 =====
/**
 * 带超时的 fetch 封装
 */
function fetchWithTimeout(url, options, timeoutMs = 30000) {
    _abortController = new AbortController();
    const timer = setTimeout(() => _abortController.abort(), timeoutMs);
    return fetch(url, { ...options, signal: _abortController.signal })
        .finally(() => {
            clearTimeout(timer);
            _abortController = null;
        });
}

/**
 * 手动取消识别
 */
function cancelRecognition() {
    if (_abortController) {
        _abortController.abort();
        _abortController = null;
    }
    showLoading(false);
    setStep(1);
    showUploadError('识别已取消');
}

async function startRecognition() {
    if (!_selectedFile) {
        showUploadError('请先选择图片文件');
        return;
    }

    const recogBtn = document.getElementById('recognizeBtn');
    if (recogBtn) {
        recogBtn.disabled = true;
        recogBtn.innerHTML = '<i class="bi bi-hourglass-split me-2"></i>识别中...';
    }

    setStep(3);
    showLoading(true);

    try {
        const formData = new FormData();
        formData.append('image', _selectedFile);

        const res = await fetchWithTimeout('/api/recognize', {
            method: 'POST',
            body: formData,
        }, 60000);
        const data = await res.json();

        if (data.success) {
            window.location.href = data.redirect || `/record/${data.record_id}`;
        } else {
            setStep(2);
            showLoading(false);
            showUploadError(data.error || '识别失败，请重试');
        }
    } catch (e) {
        setStep(2);
        showLoading(false);
        if (e.name === 'AbortError') {
            showUploadError('识别超时（60秒），请尝试较小的图片或稍后重试');
        } else {
            showUploadError('网络错误，请检查连接后重试');
        }
    } finally {
        if (recogBtn) {
            recogBtn.disabled = false;
            recogBtn.innerHTML = '<i class="bi bi-cpu-fill me-2"></i>开始识别';
        }
    }
}

/**
 * 从URL识别
 */
async function recognizeFromUrl() {
    const urlInput = document.getElementById('imageUrlInput');
    const urlBtn = document.getElementById('urlRecognizeBtn');
    const url = urlInput.value.trim();

    if (!url) {
        showUploadError('请输入图片链接');
        return;
    }

    // 基础URL验证
    try {
        new URL(url);
    } catch {
        showUploadError('请输入有效的图片链接');
        return;
    }

    // 禁用按钮防止重复点击
    if (urlBtn) {
        urlBtn.disabled = true;
        urlBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> 识别中...';
    }

    setStep(3);
    showLoading(true);

    try {
        const res = await fetchWithTimeout('/api/recognize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image_url: url }),
        }, 30000);
        const data = await res.json();

        if (data.success) {
            window.location.href = data.redirect || `/record/${data.record_id}`;
        } else {
            setStep(1);
            showLoading(false);
            showUploadError(data.error || '识别失败，请检查图片链接');
        }
    } catch (e) {
        setStep(1);
        showLoading(false);
        if (e.name === 'AbortError') {
            showUploadError('识别超时（30秒），请检查图片链接是否有效或稍后重试');
        } else {
            showUploadError('网络错误，无法连接到服务器，请确认服务正在运行');
        }
    } finally {
        // 恢复按钮
        if (urlBtn) {
            urlBtn.disabled = false;
            urlBtn.innerHTML = '<i class="bi bi-search"></i> 识别';
        }
    }
}

/**
 * 控制加载状态
 */
function showLoading(isLoading) {
    previewSection.classList.toggle('d-none', isLoading);
    loadingSection.classList.toggle('d-none', !isLoading);

    // 取消按钮逻辑
    const cancelBtn = document.getElementById('cancelLoadingBtn');
    if (cancelBtn) {
        if (isLoading) {
            // 5秒后显示取消按钮
            _cancelTimer = setTimeout(() => {
                cancelBtn.style.display = '';
            }, 5000);
        } else {
            clearTimeout(_cancelTimer);
            cancelBtn.style.display = 'none';
        }
    }
}

/**
 * 显示错误提示
 */
function showUploadError(message) {
    // 移除已有的错误提示
    const existing = errorContainer.querySelector('.alert');
    if (existing) existing.remove();

    const alert = document.createElement('div');
    alert.className = 'alert alert-danger d-flex align-items-center gap-2 fade show mt-3';
    alert.innerHTML = `
        <i class="bi bi-exclamation-circle-fill text-danger"></i>
        <span>${message}</span>
        <button type="button" class="btn-close ms-auto" onclick="this.parentElement.remove()"></button>
    `;
    errorContainer.appendChild(alert);

    // 自动消失（5秒）
    setTimeout(() => {
        if (alert.parentElement) alert.remove();
    }, 5000);
}

// Enter键触发URL识别
document.getElementById('imageUrlInput')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        recognizeFromUrl();
    }
});

// ===== 剪贴板粘贴识别 =====
// 当识别面板打开时，Ctrl+V / Cmd+V 直接粘贴剪贴簿图片进行识别
document.addEventListener('paste', (e) => {
    // 判断识别面板是否打开（主页弹窗 or 独立上传页）
    const overlay = document.getElementById('recognizeOverlay');
    const panelOpen = (overlay && overlay.classList.contains('active')) || !overlay;

    if (!panelOpen) return;
    // 如果正在加载中，不处理
    if (loadingSection && !loadingSection.classList.contains('d-none')) return;

    const items = e.clipboardData?.items;
    if (!items) return;

    for (const item of items) {
        if (item.type.startsWith('image/')) {
            e.preventDefault();
            const file = item.getAsFile();
            if (file) {
                // 给剪贴簿的文件加个合理的文件名
                if (!file.name || file.name === 'image.png') {
                    const ext = file.type.split('/')[1] || 'png';
                    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
                    const renamed = new File([file], `clipboard-${ts}.${ext}`, { type: file.type });
                    handleFileSelect(renamed);
                } else {
                    handleFileSelect(file);
                }
            }
            return;
        }
    }
});
