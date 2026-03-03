"""Simple TR/EN localization for UI strings."""

from redakt.constants import Language

_STRINGS = {
    # ── Main Window ──
    "title": {"tr": "REDAKT", "en": "REDAKT"},
    "subtitle": {"tr": "YEREL ANONIMLEŞTIRME", "en": "LOCAL DE-IDENTIFICATION"},
    "config": {"tr": "AYARLAR", "en": "CONFIG"},
    "no_file": {"tr": "DOSYA YÜKLENMEDİ", "en": "NO FILE LOADED"},
    "open_file": {"tr": "AÇ", "en": "OPEN"},
    "clear": {"tr": "SİL", "en": "CLEAR"},
    "workflow_hint": {
        "tr": "1. Dosya aç  \u2192  2. KVK tara  \u2192  3. İncele & seç  \u2192  4. Dışa aktar",
        "en": "1. Open file  \u2192  2. Scan for PII  \u2192  3. Review & toggle  \u2192  4. Export",
    },
    "document_text": {"tr": "BELGE METNİ", "en": "DOCUMENT TEXT"},
    "document_hint": {
        "tr": "Orijinal belge metni. Taramadan sonra kişisel veriler vurgulanır.",
        "en": "Original document text. PII entities are highlighted after scanning.",
    },
    "redacted_preview": {"tr": "ANONİMLEŞTİRİLMİŞ ÖNİZLEME", "en": "REDACTED PREVIEW"},
    "redacted_hint": {
        "tr": "Kişisel verilerin siyah çubuklarla değiştirildiği önizleme.",
        "en": "Preview with personal data replaced by black bars.",
    },
    "detected_pii": {"tr": "TESPİT EDİLEN KİŞİSEL VERİLER", "en": "DETECTED PII"},
    "entity_hint": {
        "tr": "Öğeleri tek tek aç/kapat. İşaretlenmemiş öğeler anonimleştirilMEZ.",
        "en": "Toggle individual items on/off. Unchecked items won't be redacted.",
    },
    "select_all": {"tr": "TÜMÜNÜ SEÇ", "en": "SELECT ALL"},
    "select_none": {"tr": "HİÇBİRİNİ SEÇME", "en": "SELECT NONE"},
    "document_ai": {"tr": "BELGE YAPAY ZEKASI", "en": "DOCUMENT AI"},
    "ai_hint": {
        "tr": "Yapay zeka destekli belge analizi. Belge hakkında soru sorun.",
        "en": "AI-powered document analysis. Ask questions about the document.",
    },
    "clear_chat": {"tr": "TEMİZLE", "en": "CLEAR"},
    "send": {"tr": "GÖNDER", "en": "SEND"},
    "ask_placeholder": {"tr": "Belge hakkında soru sor...", "en": "Ask a question about the document..."},
    "scan_for_pii": {"tr": "TARA", "en": "SCAN"},
    "age_based_dates": {"tr": "TARİHLERİ HASTA YAŞI OLARAK YAZ", "en": "AGE-BASED DATES"},
    "age_short": {"tr": "YAŞ", "en": "AGE"},
    "export": {"tr": "DIŞA AKTAR:", "en": "EXPORT:"},
    "export_short": {"tr": "AKTAR", "en": "EXPORT"},
    "export_redacted": {"tr": "ANONİM DOSYA İNDİR", "en": "EXPORT REDACTED"},
    "lang": {"tr": "DİL:", "en": "LANG:"},

    # ── Tooltips ──
    "tip_open": {
        "tr": "Tıbbi belge aç (PDF, DOCX, XLSX veya görüntü)",
        "en": "Open a medical document (PDF, DOCX, XLSX, or image)",
    },
    "tip_clear": {"tr": "Mevcut belgeyi kapat ve sıfırla", "en": "Close the current document and reset"},
    "tip_config": {
        "tr": "Model, motor ve dil ayarlarını yapılandır",
        "en": "Configure model, backend, and language settings",
    },
    "tip_scan": {
        "tr": "Belgedeki tüm kişisel verileri tespit etmek için AI analizi başlat",
        "en": "Run AI analysis to detect all personal data in the document",
    },
    "tip_export": {
        "tr": "Kişisel verileri kaldırılmış anonimleştirilmiş belgeyi dışa aktar",
        "en": "Export the redacted document with PII removed",
    },
    "tip_clear_chat": {"tr": "Sohbet geçmişini temizle", "en": "Clear conversation history"},
    "tip_send": {"tr": "Sorunuzu yapay zekaya gönderin", "en": "Send your question to the AI"},
    "tip_select_all": {
        "tr": "Tüm tespit edilen öğeleri anonimleştirme için etkinleştir",
        "en": "Enable all detected entities for redaction",
    },
    "tip_select_none": {
        "tr": "Tüm öğeleri devre dışı bırak (hiçbir şey anonimleştirilmez)",
        "en": "Disable all entities (nothing will be redacted)",
    },
    "tip_age_mode": {
        "tr": "Doğum tarihi bulunduğunda, diğer tarihleri hasta yaşıyla değiştir "
              "(örn: '3.5 yaş'). Pediatrik belgeler için kullanışlı.",
        "en": "When a birth date is found, replace other dates with patient age "
              "(e.g., 'at age 3.5 yrs'). Useful for pediatric documents.",
    },
    "tip_model_label": {
        "tr": "Model ve motor ayarlarını açmak için tıkla",
        "en": "Click to open model and backend settings",
    },

    # ── Birth date selection dialog ──
    "select_birth_date": {"tr": "Doğum Tarihini Seçin", "en": "Select Birth Date"},
    "birth_date_prompt": {
        "tr": "Doğum tarihini seçin. Diğer tarihler hasta yaşına dönüştürülecektir.",
        "en": "Select the birth date. Other dates will be converted to patient age.",
    },
    "no_dates_found": {
        "tr": "Ayrıştırılabilir tarih bulunamadı. Yaşa göre tarih modu etkinleştirilemiyor.",
        "en": "No parseable dates found. Cannot enable age-based date mode.",
    },
    "birth_date_label": {"tr": "Doğum:", "en": "Birth:"},
    "change_birth_date": {"tr": "Değiştir", "en": "Change"},
    "tip_change_birth_date": {
        "tr": "Doğum tarihini değiştir — yaş hesaplamaları yeniden yapılacak",
        "en": "Change birth date — age calculations will be recalculated",
    },
    "identifying_birth_date": {
        "tr": "Doğum tarihi tespit ediliyor...",
        "en": "Identifying birth date...",
    },

    # ── Status/state messages ──
    "drop_here": {
        "tr": "DOSYA SÜRÜKLE VEYA AÇ'A TIKLA",
        "en": "DROP FILE HERE OR CLICK OPEN",
    },
    "scan_to_preview": {
        "tr": "ÖNİZLEME İÇİN KİŞİSEL VERİ TARA",
        "en": "SCAN FOR PII TO PREVIEW REDACTION",
    },
    "click_scan": {
        "tr": "KİŞİSEL VERİLERİ TESPİT ETMEK İÇİN 'KİŞİSEL VERİ TARA'YA TIKLAYIN",
        "en": "CLICK 'SCAN FOR PII' TO DETECT PERSONAL DATA",
    },
    "file_loaded_chat": {
        "tr": "DOSYA YÜKLENDİ: {name}\nAşağıdan belge hakkında soru sorun.",
        "en": "FILE LOADED: {name}\nAsk a question about the document below.",
    },
    "load_file_chat": {
        "tr": "SOHBET İÇİN DOSYA YÜKLEYİN",
        "en": "LOAD A FILE TO USE CHAT",
    },
    "file_cleared_chat": {
        "tr": "DOSYA: {name}\nAşağıdan belge hakkında soru sorun.",
        "en": "FILE: {name}\nAsk a question about the document below.",
    },
    "scanning": {"tr": "TARANIYOR...", "en": "SCANNING..."},
    "scanning_chunk": {"tr": "PARÇA {i}/{n} TARANIYOR...", "en": "SCANNING CHUNK {i}/{n}..."},
    "scanning_image": {"tr": "GÖRÜNTÜ TARANIYOR...", "en": "SCANNING IMAGE..."},
    "image_file_loaded": {
        "tr": "GÖRÜNTÜ DOSYASI: {name}\n\nKİŞİSEL VERİ TARA ile görüntü modeliyle analiz edin.",
        "en": "IMAGE FILE: {name}\n\nClick SCAN FOR PII to analyze with the vision model.",
    },

    # ── Settings Dialog ──
    "config_title": {"tr": "Redakt Ayarlar", "en": "Redakt Config"},
    "your_system": {"tr": "SİSTEMİNİZ", "en": "YOUR SYSTEM"},
    "sys_helper": {
        "tr": "Bu makinede tespit edilen donanım. Model uyumluluğu mevcut belleğe bağlıdır.",
        "en": "Hardware detected on this machine. Model compatibility depends on available memory.",
    },
    "privacy_notice": {
        "tr": "Tüm işlemler bu makinede yerel olarak çalışır. Hiçbir veri bulut servisine gönderilmez.",
        "en": "All processing runs locally on this machine. No data is sent to any cloud service.",
    },
    "engine": {"tr": "MOTOR", "en": "ENGINE"},
    "engine_helper": {
        "tr": "Makinenizde çalışacak AI motorunu seçin.",
        "en": "Choose which AI backend runs on your machine.",
    },
    "model_quant": {"tr": "MODEL KANTİZASYON", "en": "MODEL QUANTIZATION"},
    "model_helper": {
        "tr": "Kantizasyon seviyesi seçin. Yüksek kalite daha fazla bellek gerektirir.",
        "en": "Select a quantization level. Higher quality requires more memory.",
    },
    "llamacpp_server": {"tr": "LLAMA.CPP SUNUCU", "en": "LLAMA.CPP SERVER"},
    "llamacpp_helper": {
        "tr": "Otomatik yönetilen yerel sunucu. Yapılandırma gerekmez.",
        "en": "Automatically managed local server. No configuration needed.",
    },
    "llamacpp_model_note": {
        "tr": "Llama.cpp GGUF dosyaları kullanır. Model ilk çalıştırmada otomatik indirilir.",
        "en": "Llama.cpp uses GGUF files. The model downloads automatically on first launch.",
    },
    "about": {"tr": "HAKKINDA", "en": "ABOUT"},
    "close": {"tr": "KAPAT", "en": "CLOSE"},
    "recommended": {"tr": "ÖNERİLEN", "en": "RECOMMENDED"},
    "high_quality": {"tr": "YÜKSEK KALİTE", "en": "HIGH QUALITY"},
    "full_precision": {"tr": "TAM HASSASIYET", "en": "FULL PRECISION"},
    "needs_more_memory": {"tr": "DAHA FAZLA BELLEK GEREKLİ", "en": "NEEDS MORE MEMORY"},
    "balanced_desc": {
        "tr": "Dengeli hız ve kalite. Çoğu sistem için önerilir.",
        "en": "Balanced speed and quality. Recommended for most systems.",
    },
    "high_quality_desc": {
        "tr": "Daha yüksek kalite çıktı, daha fazla bellek gerektirir.",
        "en": "Higher quality output, needs more memory.",
    },
    "full_precision_desc": {
        "tr": "Tam hassasiyet. Maksimum kalite, üst düzey donanım gerektirir.",
        "en": "Full precision. Maximum quality, requires high-end hardware.",
    },

    # ── Table headers ──
    "col_original": {"tr": "ORİJİNAL", "en": "ORIGINAL"},
    "col_type": {"tr": "TÜR", "en": "TYPE"},
    "col_replacement": {"tr": "YERİNE", "en": "REPLACEMENT"},
    "col_conf": {"tr": "GÜVEN", "en": "CONF"},

    # ── Dynamic panel headers ──
    "doc_text_count": {
        "tr": "BELGE METNİ  ({active}/{total} KVK VURGULANMIŞ)",
        "en": "DOCUMENT TEXT  ({active}/{total} PII HIGHLIGHTED)",
    },
    "redacted_count": {
        "tr": "ANONİMLEŞTİRİLMİŞ ÖNİZLEME  ({active}/{total} ANONİMLEŞTİRİLMİŞ)",
        "en": "REDACTED PREVIEW  ({active}/{total} REDACTED)",
    },
    "pii_count": {
        "tr": "TESPİT EDİLEN KVK  ({active}/{total} AKTİF)",
        "en": "DETECTED PII  ({active}/{total} ACTIVE)",
    },

    # ── File info ──
    "file_chars": {
        "tr": "{name}  |  {count} karakter",
        "en": "{name}  |  {count} chars",
    },
    "file_image": {
        "tr": "{name}  |  GÖRÜNTÜ",
        "en": "{name}  |  IMAGE",
    },
    "doc_text_chars": {
        "tr": "BELGE METNİ  ({count} karakter)",
        "en": "DOCUMENT TEXT  ({count} chars)",
    },

    # ── Chat labels ──
    "chat_you": {"tr": "SİZ", "en": "YOU"},
    "chat_ai": {"tr": "YAPAY ZEKA", "en": "AI"},
    "chat_thinking": {"tr": "DÜŞÜNÜYOR...", "en": "THINKING..."},

    # ── Detected text (image) ──
    "detected_text_count": {
        "tr": "TESPİT EDİLEN METİN  ({count} öğe)",
        "en": "DETECTED TEXT  ({count} entities)",
    },
    "pii_in_image": {
        "tr": "Görüntüde KVK tespit edildi ({count} öğe):",
        "en": "PII detected in image ({count} entities):",
    },
    "image_scanned": {"tr": "Görüntü tarandı", "en": "Image scanned"},

    # ── Error/dialog messages ──
    "nothing_to_redact": {
        "tr": "Anonimleştirilecek veri yok",
        "en": "Nothing to redact",
    },
    "nothing_to_redact_msg": {
        "tr": "Anonimleştirme için hiçbir KVK öğesi seçilmedi.\nEn az bir öğeyi işaretleyip tekrar deneyin.",
        "en": "No PII items are selected for redaction.\nCheck at least one item and try again.",
    },
    "export_complete": {"tr": "Dışa Aktarma Tamamlandı", "en": "Export Complete"},
    "export_complete_msg": {
        "tr": "Anonimleştirilmiş dosya kaydedildi:\n{path}",
        "en": "Redacted file saved:\n{path}",
    },
    "export_failed": {
        "tr": "Dışa aktarma başarısız:\n{error}",
        "en": "Export failed:\n{error}",
    },
    "scan_failed": {
        "tr": "Tarama başarısız:\n{error}",
        "en": "Scan failed:\n{error}",
    },
    "file_read_failed": {
        "tr": "Dosya okunamadı:\n{error}",
        "en": "Failed to read file:\n{error}",
    },
    "unsupported_file": {
        "tr": "Desteklenmeyen dosya türü: {ext}\n\nDesteklenen: {supported}",
        "en": "Unsupported file type: {ext}\n\nSupported: {supported}",
    },
    "error_title": {"tr": "Hata", "en": "Error"},
    "open_document": {
        "tr": "Tıbbi Belge Aç",
        "en": "Open Medical Document",
    },
    "file_filter": {
        "tr": "Desteklenen Dosyalar ({exts});;Tüm Dosyalar (*)",
        "en": "Supported Files ({exts});;All Files (*)",
    },

    # ── Status messages ──
    "starting_server": {"tr": "LLAMA-SUNUCU BAŞLATILIYOR...", "en": "STARTING LLAMA-SERVER..."},
    "server_failed": {"tr": "LLAMA-SUNUCU BAŞARISIZ", "en": "LLAMA-SERVER FAILED"},

    # ── Status bar ──
    "engine_label": {"tr": "MOTOR:", "en": "ENGINE:"},
    "connected": {"tr": "BAĞLI", "en": "CONNECTED"},
    "offline": {"tr": "ÇEVRİMDIŞI", "en": "OFFLINE"},
    "checking": {"tr": "KONTROL EDİLİYOR...", "en": "CHECKING..."},
    "model_label": {"tr": "MODEL:", "en": "MODEL:"},
    "ready": {"tr": "HAZIR", "en": "READY"},
    "local": {"tr": "YEREL", "en": "LOCAL"},
    "inferencing": {"tr": "İŞLENİYOR...", "en": "INFERENCING..."},
    "status_ready": {"tr": "HAZIR", "en": "READY"},
    "status_not_ready": {"tr": "HAZIR DEĞİL", "en": "NOT READY"},
    "status_processing": {"tr": "YERELDE İŞLENİYOR...", "en": "PROCESSING LOCALLY..."},
    "status_error": {"tr": "HATA", "en": "ERROR"},
    "status_local_badge": {"tr": "%100 YEREL · İNTERNET GEREKMİYOR", "en": "100% LOCAL · NO INTERNET"},
}


def t(key: str, lang: Language = Language.EN, **kwargs) -> str:
    """Get a translated string.

    Usage:
        t("scan_for_pii", Language.TR)  -> "KİŞİSEL VERİ TARA"
        t("scanning_chunk", Language.EN, i=1, n=3)  -> "SCANNING CHUNK 1/3..."
    """
    entry = _STRINGS.get(key)
    if not entry:
        return key
    lang_key = "tr" if lang == Language.TR else "en"
    text = entry.get(lang_key, entry.get("en", key))
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text
