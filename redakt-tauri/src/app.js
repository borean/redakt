// ═══════════════════════════════════════════════════════════
// REDAKT — Desktop App Logic
// Tauri IPC integration + i18n + state management
// ═══════════════════════════════════════════════════════════

const { invoke } = window.__TAURI__.core;
const { open, save } = window.__TAURI__.dialog;
const { listen } = window.__TAURI__.event;

// ── State ──
const state = {
    language: 'en',
    currentFile: null,
    originalText: '',
    entities: [],
    scanning: false,
    scanned: false,
    downloading: false,
    downloadPercent: 0,
};

// ── i18n ──
const translations = {
    tr: {
        subtitle: 'YEREL KİMLİK GİZLEME',
        no_file: 'DOSYA YOK',
        open: 'AÇ',
        scan: 'TARA',
        export: 'DIŞA AKTAR',
        clear: 'TEMİZLE',
        age_mode: 'YAŞ',
        select_all: 'HEPSİ',
        select_none: 'HİÇBİRİ',
        doc_text: 'BELGE METNİ',
        redacted_preview: 'KARARTILMIŞ ÖNİZLEME',
        detected_pii: 'TESPİT EDİLEN KV',
        col_original: 'Orijinal',
        col_type: 'Tür',
        col_replacement: 'Değişim',
        col_confidence: 'Güven',
        drop_hint: 'Bir dosya sürükleyin veya AÇ\'a tıklayın',
        scan_hint: 'Karartılmış önizleme için "Tara"ya basın.',
        local_badge: '%100 YEREL · İNTERNET YOK',
        settings: 'AYARLAR',
        theme_label: 'Tema',
        model_label: 'Model (GGUF)',
        server_label: 'LLM Sunucu',
        start: 'BAŞLAT',
        stop: 'DURDUR',
        scanning_text: 'TARANIYOR...',
        processing: 'YEREL OLARAK İŞLENİYOR...',
        ready: 'HAZIR',
        chip_name: 'AD',
        chip_date: 'TARİH',
        chip_id: 'KİMLİK',
        chip_address: 'ADRES',
        chip_phone: 'TELEFON',
        chip_email: 'E-POSTA',
        chip_institution: 'KURUM',
        chip_age: 'YAŞ',
        download_wait: 'Model indiriliyor. Bu tek seferlik bir indirmedir — tamamlandığında uygulama hazır olacak.',
        download_onetime: 'Tek seferlik indirme · tamamlandığında otomatik başlar',
        about_desc: 'Yerel tıbbi belge kimlik gizleme. Klinik belgelerden kişisel verileri yerel bir LLM kullanarak tespit eder ve karartır. Hiçbir veri cihazınızdan çıkmaz.',
        about_developer: 'Geliştirici: Dr. Hasan Bora Ulukapı',
        about_engine: 'Motor: Qwen 3.5 · llama.cpp',
        about_license: 'MIT Lisansı',
    },
    en: {
        subtitle: 'LOCAL DE-IDENTIFICATION',
        no_file: 'NO FILE LOADED',
        open: 'OPEN',
        scan: 'SCAN',
        export: 'EXPORT',
        clear: 'CLEAR',
        age_mode: 'AGE',
        select_all: 'ALL',
        select_none: 'NONE',
        doc_text: 'DOCUMENT TEXT',
        redacted_preview: 'REDACTED PREVIEW',
        detected_pii: 'DETECTED PII',
        col_original: 'Original',
        col_type: 'Type',
        col_replacement: 'Replacement',
        col_confidence: 'Conf.',
        drop_hint: 'Drop a file here or click OPEN',
        scan_hint: 'Click "Scan" to preview redacted output.',
        local_badge: '100% LOCAL · NO INTERNET',
        settings: 'SETTINGS',
        theme_label: 'Theme',
        model_label: 'Model (GGUF)',
        server_label: 'LLM Server',
        start: 'START',
        stop: 'STOP',
        scanning_text: 'SCANNING...',
        processing: 'PROCESSING LOCALLY...',
        ready: 'READY',
        chip_name: 'NAME',
        chip_date: 'DATE',
        chip_id: 'ID',
        chip_address: 'ADDR',
        chip_phone: 'PHONE',
        chip_email: 'EMAIL',
        chip_institution: 'INST',
        chip_age: 'AGE',
        download_wait: 'Model is still downloading. This is a one-time download — the app will be ready once it completes.',
        download_onetime: 'One-time download · auto-starts when complete',
        about_desc: 'Local medical document de-identification. Detects and redacts personal identifiable information from clinical documents using a local LLM. No data ever leaves your machine.',
        about_developer: 'Developer: Dr. Hasan Bora Ulukapı',
        about_engine: 'Engine: Qwen 3.5 via llama.cpp',
        about_license: 'MIT License',
    },
};

function t(key) {
    return translations[state.language]?.[key] || translations.en[key] || key;
}

function applyTranslations() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        el.textContent = t(key);
    });
}

// ── Language toggle ──
function setLanguage(lang) {
    state.language = lang;
    document.documentElement.lang = lang;
    document.getElementById('lang-tr').classList.toggle('active', lang === 'tr');
    document.getElementById('lang-en').classList.toggle('active', lang === 'en');
    applyTranslations();
    updateChipLabels();

    // Restore status text
    if (!state.scanning && !state.scanned) {
        document.getElementById('status-text').textContent = t('ready');
    }
}

document.getElementById('lang-tr').addEventListener('click', () => setLanguage('tr'));
document.getElementById('lang-en').addEventListener('click', () => setLanguage('en'));

// ── File open ──
document.getElementById('btn-open').addEventListener('click', async () => {
    try {
        const path = await open({
            multiple: false,
            filters: [{
                name: 'Documents',
                extensions: ['pdf', 'docx', 'txt', 'md', 'png', 'jpg', 'jpeg']
            }]
        });

        if (path) {
            await loadFile(path);
        }
    } catch (err) {
        setStatus('error', err.toString());
    }
});

async function loadFile(path) {
    try {
        setStatus('processing', t('processing'));
        const text = await invoke('open_file', { path });
        state.currentFile = path;
        state.originalText = text;
        state.entities = [];
        state.scanned = false;

        // Update file label
        const filename = path.split('/').pop().split('\\').pop();
        document.getElementById('file-label').textContent = filename;

        // Switch to split-pane mode
        document.getElementById('panes').classList.remove('single-pane');

        // Show text in left pane
        const docEl = document.getElementById('document-text');
        docEl.innerHTML = '';
        docEl.textContent = text;
        docEl.style.whiteSpace = 'pre-wrap';

        // Reset right pane
        document.getElementById('redacted-preview').innerHTML =
            `<span class="placeholder-text">${t('scan_hint')}</span>`;

        // Reset entity panel
        document.getElementById('entity-panel').style.display = 'none';
        document.getElementById('chips').innerHTML = '';

        // Update left label
        document.getElementById('left-label').textContent = t('doc_text');
        document.getElementById('right-label').textContent = t('redacted_preview');

        setStatus('ready', t('ready'));
    } catch (err) {
        setStatus('error', err.toString());
    }
}

// ── Drag and drop (Tauri v2 webview API) ──
let dropOverlay = null;

function showDropOverlay() {
    if (!dropOverlay) {
        dropOverlay = document.createElement('div');
        dropOverlay.className = 'drop-overlay';
        dropOverlay.innerHTML = `<span>${t('drop_hint')}</span>`;
        document.body.appendChild(dropOverlay);
    }
}

function hideDropOverlay() {
    if (dropOverlay) {
        dropOverlay.remove();
        dropOverlay = null;
    }
}

// Tauri v2: use getCurrentWebview().onDragDropEvent() for OS file drops
(async function setupDragDrop() {
    try {
        // Try webview API first (Tauri v2 preferred)
        if (window.__TAURI__?.webview?.getCurrentWebview) {
            const webview = window.__TAURI__.webview.getCurrentWebview();
            await webview.onDragDropEvent((event) => {
                const type = event.payload.type;
                if (type === 'enter' || type === 'over') {
                    showDropOverlay();
                } else if (type === 'leave' || type === 'cancel') {
                    hideDropOverlay();
                } else if (type === 'drop') {
                    hideDropOverlay();
                    const paths = event.payload.paths;
                    if (paths && paths.length > 0) {
                        loadFile(paths[0]);
                    }
                }
            });
            console.log('Drag-drop: using webview.onDragDropEvent');
        }
        // Fallback: try window API
        else if (window.__TAURI__?.window?.getCurrentWindow) {
            const appWindow = window.__TAURI__.window.getCurrentWindow();
            await appWindow.onDragDropEvent((event) => {
                const type = event.payload.type;
                if (type === 'enter' || type === 'over') {
                    showDropOverlay();
                } else if (type === 'leave' || type === 'cancel') {
                    hideDropOverlay();
                } else if (type === 'drop') {
                    hideDropOverlay();
                    const paths = event.payload.paths;
                    if (paths && paths.length > 0) {
                        loadFile(paths[0]);
                    }
                }
            });
            console.log('Drag-drop: using window.onDragDropEvent');
        }
        // Last resort: global listen
        else {
            await listen('tauri://drag-drop', async (event) => {
                hideDropOverlay();
                const paths = event.payload?.paths;
                if (paths && paths.length > 0) {
                    await loadFile(paths[0]);
                }
            });
            await listen('tauri://drag-over', () => showDropOverlay());
            await listen('tauri://drag-leave', () => hideDropOverlay());
            console.log('Drag-drop: using global listen fallback');
        }
    } catch (err) {
        console.error('Drag-drop setup failed:', err);
        // Ultimate fallback: global listen
        listen('tauri://drag-drop', async (event) => {
            hideDropOverlay();
            const paths = event.payload?.paths;
            if (paths && paths.length > 0) {
                await loadFile(paths[0]);
            }
        });
    }
})();

// Prevent browser default drag behavior
document.addEventListener('dragover', (e) => e.preventDefault());
document.addEventListener('drop', (e) => e.preventDefault());

// ── Scan ──
document.getElementById('btn-scan').addEventListener('click', async () => {
    if (state.scanning || !state.originalText) return;

    // Block scan while model is downloading
    if (state.downloading) {
        showToast(t('download_wait'), 5000);
        return;
    }

    state.scanning = true;
    const scanBtn = document.getElementById('btn-scan');
    scanBtn.classList.add('scanning');
    scanBtn.textContent = t('scanning_text');

    setStatus('processing', t('processing'));
    document.getElementById('progress-bar').classList.add('active');

    try {
        const result = await invoke('scan_document', {
            text: state.originalText,
            language: state.language,
        });

        state.entities = result.entities;
        state.scanned = true;

        // Render highlighted text
        document.getElementById('document-text').innerHTML = result.highlighted_html;

        // Render redacted preview
        document.getElementById('redacted-preview').innerHTML = result.redacted_html;

        // Update labels with counts
        const count = state.entities.length;
        const lang = state.language;
        document.getElementById('left-label').textContent =
            `${t('doc_text')} (${count} ${lang === 'tr' ? 'KV' : 'PII'})`;
        document.getElementById('right-label').textContent =
            `${t('redacted_preview')} (${count}/${count})`;

        // Build chips
        buildChips();

        // Build entity table
        buildEntityTable();

        // Enable export
        document.getElementById('btn-export').classList.add('ready');
        document.getElementById('age-toggle').style.display = 'flex';
        document.getElementById('btn-select-all').style.display = '';
        document.getElementById('btn-select-none').style.display = '';

        setStatus('success', result.summary);
    } catch (err) {
        setStatus('error', err.toString());
    } finally {
        state.scanning = false;
        scanBtn.classList.remove('scanning');
        scanBtn.textContent = t('scan');
        document.getElementById('progress-bar').classList.remove('active');
    }
});

// ── Chips ──
function buildChips() {
    const chipsEl = document.getElementById('chips');
    chipsEl.innerHTML = '';

    // Count entities per category
    const cats = {};
    state.entities.forEach(e => {
        cats[e.category] = (cats[e.category] || 0) + 1;
    });

    for (const [cat, count] of Object.entries(cats)) {
        const chip = document.createElement('span');
        chip.className = `chip ${cat} active`;
        chip.textContent = t(`chip_${cat}`) || cat.toUpperCase();
        chip.dataset.category = cat;
        chip.title = `${count} ${cat}`;

        chip.addEventListener('click', () => {
            chip.classList.toggle('active');
            const enabled = chip.classList.contains('active');
            toggleCategory(cat, enabled);
        });

        chipsEl.appendChild(chip);
    }
}

function updateChipLabels() {
    document.querySelectorAll('.chip').forEach(chip => {
        const cat = chip.dataset.category;
        if (cat) {
            chip.textContent = t(`chip_${cat}`) || cat.toUpperCase();
        }
    });
}

function toggleCategory(category, enabled) {
    state.entities.forEach(e => {
        if (e.category === category) {
            e.enabled = enabled;
        }
    });
    refreshViews();
}

// ── Entity table ──
function buildEntityTable() {
    const panel = document.getElementById('entity-panel');
    const tbody = document.getElementById('entity-tbody');
    tbody.innerHTML = '';

    if (state.entities.length === 0) {
        panel.style.display = 'none';
        return;
    }

    panel.style.display = '';

    state.entities.forEach((entity, idx) => {
        const tr = document.createElement('tr');

        // Category color
        const colors = {
            name: '#d46b6b', date: '#d4884e', id: '#d4a04e', address: '#6bbd6b',
            phone: '#5ba8b5', email: '#7aabdb', institution: '#9b8ec4', age: '#c47a8e',
        };
        const color = colors[entity.category] || '#808080';

        tr.innerHTML = `
            <td><input type="checkbox" ${entity.enabled ? 'checked' : ''} data-idx="${idx}"></td>
            <td style="color:${color};font-weight:700">${idx + 1}</td>
            <td>${escapeHtml(entity.original)}</td>
            <td><span class="entity-type" style="background:${color}22;color:${color};border:1px solid ${color}66">${entity.category.toUpperCase()}</span></td>
            <td style="color:var(--text-dim)">${entity.placeholder}</td>
            <td>${Math.round(entity.confidence * 100)}%</td>
        `;

        // Toggle handler
        tr.querySelector('input').addEventListener('change', (e) => {
            state.entities[idx].enabled = e.target.checked;
            refreshViews();
        });

        tbody.appendChild(tr);
    });
}

// ── Select all / none ──
document.getElementById('btn-select-all').addEventListener('click', () => {
    state.entities.forEach(e => e.enabled = true);
    document.querySelectorAll('.chip').forEach(c => c.classList.add('active'));
    refreshViews();
    buildEntityTable();
});

document.getElementById('btn-select-none').addEventListener('click', () => {
    state.entities.forEach(e => e.enabled = false);
    document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
    refreshViews();
    buildEntityTable();
});

// ── Refresh both panes after toggle changes ──
async function refreshViews() {
    if (!state.scanned) return;

    try {
        // Re-render on the Rust side for consistent output
        const result = await invoke('toggle_entity', {
            text: state.originalText,
            entities: state.entities,
            index: 0,
            enabled: state.entities[0]?.enabled ?? true,
        });

        document.getElementById('document-text').innerHTML = result.highlighted_html;
        document.getElementById('redacted-preview').innerHTML = result.redacted_html;

        const enabled = state.entities.filter(e => e.enabled).length;
        const total = state.entities.length;
        document.getElementById('right-label').textContent =
            `${t('redacted_preview')} (${enabled}/${total})`;
    } catch (err) {
        console.error('Refresh failed:', err);
    }
}

// ── Export ──
document.getElementById('btn-export').addEventListener('click', async () => {
    if (!state.scanned || state.entities.length === 0) return;

    const format = document.getElementById('export-format').value;
    const ext = format === 'md' ? 'md' : format;

    try {
        const path = await save({
            defaultPath: `redacted.${ext}`,
            filters: [{ name: format.toUpperCase(), extensions: [ext] }],
        });

        if (path) {
            setStatus('processing', t('processing'));
            await invoke('export_document', {
                text: state.originalText,
                entities: state.entities,
                format,
                outputPath: path,
            });
            setStatus('success', `Exported to ${path.split('/').pop()}`);
        }
    } catch (err) {
        setStatus('error', err.toString());
    }
});

// ── Clear ──
document.getElementById('btn-clear').addEventListener('click', () => {
    state.currentFile = null;
    state.originalText = '';
    state.entities = [];
    state.scanning = false;
    state.scanned = false;

    document.getElementById('file-label').textContent = t('no_file');
    document.getElementById('panes').classList.add('single-pane');
    document.getElementById('document-text').innerHTML = `
        <div class="empty-state" id="empty-state">
            <div class="empty-icon">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity="0.3">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14,2 14,8 20,8"/>
                </svg>
            </div>
            <p class="empty-text">${t('drop_hint')}</p>
            <p class="empty-formats">PDF, DOCX, TXT, PNG, JPG</p>
        </div>
    `;
    document.getElementById('redacted-preview').innerHTML =
        `<span class="placeholder-text">${t('scan_hint')}</span>`;
    document.getElementById('entity-panel').style.display = 'none';
    document.getElementById('chips').innerHTML = '';
    document.getElementById('left-label').textContent = t('doc_text');
    document.getElementById('right-label').textContent = t('redacted_preview');
    document.getElementById('btn-export').classList.remove('ready');
    document.getElementById('age-toggle').style.display = 'none';
    document.getElementById('btn-select-all').style.display = 'none';
    document.getElementById('btn-select-none').style.display = 'none';

    setStatus('ready', t('ready'));
});

// ── Settings dialog ──
document.getElementById('btn-config').addEventListener('click', async () => {
    document.getElementById('settings-overlay').style.display = 'flex';
    await populateModels();
    await checkServerBinary();
});

async function populateModels() {
    const nameEl = document.getElementById('model-name');
    const detailsEl = document.getElementById('model-details');
    const dlProgress = document.getElementById('model-dl-progress');
    const select = document.getElementById('setting-model');

    try {
        const models = await invoke('list_models');
        select.innerHTML = '';

        if (state.downloading) {
            // Show download in progress
            nameEl.textContent = 'Qwen3.5-35B-A3B';
            detailsEl.textContent = 'Q4_K_M · ~21 GB · GGUF';
            dlProgress.style.display = '';
            updateSettingsDownloadProgress();
            select.style.display = 'none';
        } else if (models.length === 0) {
            nameEl.textContent = state.language === 'tr' ? 'Model bulunamadi' : 'No model found';
            detailsEl.textContent = state.language === 'tr'
                ? 'Qwen 3.5 otomatik indirilecek'
                : 'Qwen 3.5 will auto-download';
            dlProgress.style.display = 'none';

            const opt = document.createElement('option');
            opt.value = '__download__';
            opt.textContent = state.language === 'tr'
                ? 'Qwen 3.5 indir (~21 GB)'
                : 'Download Qwen 3.5 (~21 GB)';
            select.appendChild(opt);
            select.style.display = 'none';
        } else {
            const model = models[0]; // Best model (Qwen sorted first)
            nameEl.textContent = model.name;
            detailsEl.textContent = `${model.size_gb} GB`;
            dlProgress.style.display = 'none';

            models.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m.path;
                opt.textContent = `${m.name} (${m.size_gb} GB, ${m.quantization})`;
                select.appendChild(opt);
            });
            // Only show select if multiple models available
            select.style.display = models.length > 1 ? '' : 'none';
        }
    } catch (err) {
        console.error('Failed to list models:', err);
        nameEl.textContent = '--';
        detailsEl.textContent = '';
        dlProgress.style.display = 'none';
    }
}

function updateSettingsDownloadProgress() {
    const bar = document.getElementById('model-dl-bar');
    const pct = document.getElementById('model-dl-pct');
    const speed = document.getElementById('model-dl-speed');
    const eta = document.getElementById('model-dl-eta');
    if (!bar) return;

    const p = state.downloadPercent || 0;
    bar.style.width = `${p}%`;
    if (pct) pct.textContent = `${p}%`;
}

async function checkServerBinary() {
    // Server is auto-managed, no UI to update
}

document.getElementById('settings-close').addEventListener('click', () => {
    document.getElementById('settings-overlay').style.display = 'none';
});

document.getElementById('settings-overlay').addEventListener('click', (e) => {
    if (e.target === document.getElementById('settings-overlay')) {
        document.getElementById('settings-overlay').style.display = 'none';
    }
});

// Theme toggle (titlebar button)
document.getElementById('btn-theme').addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', next);

    // Force WebKit to repaint scrolled-off content with new theme colors
    document.querySelectorAll('.pane-content').forEach(el => {
        el.style.display = 'none';
        el.offsetHeight; // trigger reflow
        el.style.display = '';
    });
});

// LLM server is auto-managed by autoStartServer() — no manual controls needed

// ── Status bar ──
function setStatus(level, message) {
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');

    dot.className = 'status-dot';
    text.style.color = '';

    switch (level) {
        case 'processing':
            dot.classList.add('processing');
            text.style.color = 'var(--accent)';
            break;
        case 'error':
            dot.classList.add('error');
            text.style.color = 'var(--error)';
            break;
        case 'success':
            text.style.color = 'var(--success)';
            break;
        case 'ready':
        default:
            break;
    }

    text.textContent = message;
}

// ── Toast notifications ──
let toastTimer = null;

function showToast(message, durationMs = 4000) {
    const toast = document.getElementById('toast');
    const pct = state.downloadPercent || 0;

    toast.innerHTML = `
        <div class="toast-message">${message}</div>
        ${state.downloading ? `
        <div class="toast-progress">
            <div class="toast-bar-wrap">
                <div class="toast-bar-fill" id="toast-dl-bar" style="width:${pct}%"></div>
            </div>
            <span class="toast-pct" id="toast-dl-pct">${pct}%</span>
        </div>` : ''}
    `;
    toast.classList.add('visible');

    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
        toast.classList.remove('visible');
        toastTimer = null;
    }, durationMs);
}

// ── Utility ──
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ── Auto-start LLM server ──
async function autoStartServer() {
    try {
        // Check if already running
        const status = await invoke('get_llm_status');
        if (status.running) {
            setStatus('ready', t('ready'));
            updateServerUI(true, status.model_name);
            return;
        }

        // Find available models (Qwen sorted first)
        const models = await invoke('list_models');
        let model = models.find(m => m.name.toLowerCase().includes('qwen'));

        // If no Qwen but other models exist, use best available
        if (!model && models.length > 0) {
            model = models[0];
        }

        // No model found anywhere — auto-download Qwen 3.5
        if (!model) {
            const modelPath = await downloadModelWithProgress();
            if (!modelPath) return; // Download failed
            model = { path: modelPath, name: 'Qwen3.5-35B-A3B-Q4_K_M' };
        }

        // Start server with the selected model
        setStatus('processing', state.language === 'tr'
            ? `Model yükleniyor: ${model.name}...`
            : `Loading model: ${model.name}...`);

        await invoke('start_llm_server', {
            modelPath: model.path,
            serverPath: null,
        });

        setStatus('ready', t('ready'));
        updateServerUI(true, model.name);
    } catch (err) {
        console.error('Auto-start failed:', err);
        setStatus('error', err.toString());
        updateServerUI(false, null);
    }
}

// ── Model download with progress ──
async function downloadModelWithProgress() {
    state.downloading = true;
    showDownloadProgress();

    // Listen for progress events from Rust backend
    const unlisten = await listen('download-progress', (event) => {
        const p = event.payload;
        updateDownloadProgress(p.percent, p.speed_mbps, p.eta_secs, p.downloaded, p.total);
    });

    try {
        setStatus('processing', state.language === 'tr'
            ? 'Qwen 3.5 indiriliyor...'
            : 'Downloading Qwen 3.5...');

        const modelPath = await invoke('download_model');
        hideDownloadProgress();
        return modelPath;
    } catch (err) {
        hideDownloadProgress();
        setStatus('error', state.language === 'tr'
            ? `İndirme başarısız: ${err}`
            : `Download failed: ${err}`);
        return null;
    } finally {
        state.downloading = false;
        unlisten();
    }
}

function showDownloadProgress() {
    const docEl = document.getElementById('document-text');
    docEl.innerHTML = `
        <div class="download-overlay" id="download-overlay">
            <div class="download-icon">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.5">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="7 10 12 15 17 10"/>
                    <line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
            </div>
            <div class="download-title">${state.language === 'tr' ? 'MODEL İNDİRİLİYOR' : 'DOWNLOADING MODEL'}</div>
            <div class="download-model-name">Qwen 3.5-35B-A3B · Q4_K_M · ~21 GB</div>
            <div class="download-percent" id="dl-percent">0%</div>
            <div class="download-bar-wrap">
                <div class="download-bar-fill" id="dl-bar"></div>
            </div>
            <div class="download-stats">
                <span id="dl-size">0 MB / 0 GB</span>
                <span id="dl-speed">-- MB/s</span>
                <span id="dl-eta">-- remaining</span>
            </div>
            <div class="download-note">${t('download_onetime')}</div>
        </div>
    `;

    // Also show determinate progress bar at top
    const progressBar = document.getElementById('progress-bar');
    progressBar.classList.remove('active');
    progressBar.classList.add('determinate');
    progressBar.style.setProperty('--progress', '0%');
}

function updateDownloadProgress(percent, speedMbps, etaSecs, downloaded, total) {
    // Track in state so toast can read it
    state.downloadPercent = Math.round(percent * 10) / 10;

    // Also update toast progress bar if visible
    const toastBar = document.getElementById('toast-dl-bar');
    const toastPct = document.getElementById('toast-dl-pct');
    if (toastBar) toastBar.style.width = `${state.downloadPercent}%`;
    if (toastPct) toastPct.textContent = `${state.downloadPercent}%`;

    // Also update settings dialog download progress if visible
    const modelBar = document.getElementById('model-dl-bar');
    const modelPct = document.getElementById('model-dl-pct');
    const modelSpeed = document.getElementById('model-dl-speed');
    const modelEta = document.getElementById('model-dl-eta');
    if (modelBar) {
        modelBar.style.width = `${state.downloadPercent}%`;
        if (modelPct) modelPct.textContent = `${state.downloadPercent}%`;
        if (modelSpeed) modelSpeed.textContent = speedMbps > 0 ? `${speedMbps.toFixed(1)} MB/s` : '--';
        if (modelEta) {
            if (etaSecs > 3600) {
                const h = Math.floor(etaSecs / 3600);
                const m = Math.floor((etaSecs % 3600) / 60);
                modelEta.textContent = `~${h}h ${m}m`;
            } else if (etaSecs > 60) {
                modelEta.textContent = `~${Math.floor(etaSecs / 60)} min`;
            } else if (etaSecs > 0) {
                modelEta.textContent = '<1 min';
            } else {
                modelEta.textContent = '--';
            }
        }
        // Show the progress section if it was hidden
        const dlProgress = document.getElementById('model-dl-progress');
        if (dlProgress) dlProgress.style.display = '';
    }

    const pctEl = document.getElementById('dl-percent');
    const barEl = document.getElementById('dl-bar');
    const sizeEl = document.getElementById('dl-size');
    const speedEl = document.getElementById('dl-speed');
    const etaEl = document.getElementById('dl-eta');

    if (!pctEl) return; // Download UI not visible

    const pct = Math.round(percent * 10) / 10;
    pctEl.textContent = `${pct}%`;
    barEl.style.width = `${pct}%`;

    // Format sizes
    const dlGB = (downloaded / 1_073_741_824).toFixed(2);
    const totalGB = (total / 1_073_741_824).toFixed(1);
    sizeEl.textContent = `${dlGB} / ${totalGB} GB`;

    // Speed
    speedEl.textContent = speedMbps > 0 ? `${speedMbps.toFixed(1)} MB/s` : '-- MB/s';

    // ETA
    if (etaSecs > 3600) {
        const h = Math.floor(etaSecs / 3600);
        const m = Math.floor((etaSecs % 3600) / 60);
        etaEl.textContent = `~${h}h ${m}m ${state.language === 'tr' ? 'kaldı' : 'remaining'}`;
    } else if (etaSecs > 60) {
        const m = Math.floor(etaSecs / 60);
        etaEl.textContent = `~${m} min ${state.language === 'tr' ? 'kaldı' : 'remaining'}`;
    } else if (etaSecs > 0) {
        etaEl.textContent = `<1 min ${state.language === 'tr' ? 'kaldı' : 'remaining'}`;
    } else {
        etaEl.textContent = '';
    }

    // Update top progress bar
    const progressBar = document.getElementById('progress-bar');
    progressBar.style.setProperty('--progress', `${pct}%`);

    // Update status bar text
    const statusText = state.language === 'tr'
        ? `Qwen 3.5 indiriliyor... ${pct}%`
        : `Downloading Qwen 3.5... ${pct}%`;
    document.getElementById('status-text').textContent = statusText;
}

function hideDownloadProgress() {
    // Reset progress bar
    const progressBar = document.getElementById('progress-bar');
    progressBar.classList.remove('determinate', 'active');
    progressBar.style.removeProperty('--progress');

    // Restore empty state
    const docEl = document.getElementById('document-text');
    docEl.innerHTML = `
        <div class="empty-state" id="empty-state">
            <div class="empty-icon">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity="0.3">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14,2 14,8 20,8"/>
                </svg>
            </div>
            <p class="empty-text">${t('drop_hint')}</p>
            <p class="empty-formats">PDF, DOCX, TXT, PNG, JPG</p>
        </div>
    `;
}

function updateServerUI(running, modelName) {
    // Server UI is automatic — just update model info in settings if open
    const nameEl = document.getElementById('model-name');
    const detailsEl = document.getElementById('model-details');
    if (nameEl && running && modelName) {
        nameEl.textContent = modelName;
    }
}

// ── Init ──
(async function init() {
    // Detect browser language
    const browserLang = (navigator.language || '').toLowerCase();
    setLanguage(browserLang.startsWith('tr') ? 'tr' : 'en');

    // Auto-detect model and start LLM server
    await autoStartServer();

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.metaKey || e.ctrlKey) {
            switch (e.key) {
                case 'o':
                    e.preventDefault();
                    document.getElementById('btn-open').click();
                    break;
                case 's':
                    e.preventDefault();
                    document.getElementById('btn-scan').click();
                    break;
                case 'e':
                    e.preventDefault();
                    document.getElementById('btn-export').click();
                    break;
                case ',':
                    e.preventDefault();
                    document.getElementById('btn-config').click();
                    break;
            }
        }
    });
})();
