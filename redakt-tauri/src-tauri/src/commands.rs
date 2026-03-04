use crate::anonymizer;
use crate::download;
use crate::entities::{AppSettings, LlmStatus, ModelCatalogEntry, PIIEntity, ScanResult};
use crate::export;
use crate::llm::LlmState;
use crate::redactor;
use tauri::State;

/// Open and extract text from a file
#[tauri::command]
pub async fn open_file(path: String) -> Result<String, String> {
    let extension = std::path::Path::new(&path)
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_lowercase();

    match extension.as_str() {
        "txt" | "md" => {
            std::fs::read_to_string(&path).map_err(|e| format!("Failed to read file: {}", e))
        }
        "pdf" => extract_pdf_text(&path),
        "docx" => extract_docx_text(&path),
        _ => Err(format!("Unsupported file format: .{}", extension)),
    }
}

/// Run PII detection on the current document text
#[tauri::command]
pub async fn scan_document(
    text: String,
    language: String,
    age_mode: Option<bool>,
    llm: State<'_, LlmState>,
) -> Result<ScanResult, String> {
    let mut entities = anonymizer::detect_pii(&llm, &text, &language).await?;

    // Apply age conversion only when enabled (defaults to true)
    let detected_birth_date = if age_mode.unwrap_or(true) {
        anonymizer::apply_age_conversion(&mut entities, &text, &language)
    } else {
        // Still detect birth date for display, even if not converting
        anonymizer::detect_birth_date(&entities, &text)
            .map(|(d, _)| d.format("%d.%m.%Y").to_string())
    };

    let highlighted = redactor::render_highlighted_html(&text, &entities);
    let redacted = redactor::render_redacted_html(&text, &entities);

    let category_counts: std::collections::HashMap<&str, usize> = {
        let mut map = std::collections::HashMap::new();
        for e in &entities {
            *map.entry(e.category.as_str()).or_insert(0) += 1;
        }
        map
    };

    let summary = if language == "tr" {
        let cat_label_tr = |cat: &str| -> &'static str {
            match cat {
                "name" => "ad",
                "date" => "tarih",
                "id" => "kimlik",
                "address" => "adres",
                "phone" => "telefon",
                "email" => "e-posta",
                "institution" => "kurum",
                "age" => "yaş",
                _ => "diğer",
            }
        };
        format!(
            "{} KV tespit edildi: {}",
            entities.len(),
            category_counts
                .iter()
                .map(|(k, v)| format!("{} {}", v, cat_label_tr(k)))
                .collect::<Vec<_>>()
                .join(", ")
        )
    } else {
        format!(
            "{} PII entities found: {}",
            entities.len(),
            category_counts
                .iter()
                .map(|(k, v)| format!("{} {}", v, k))
                .collect::<Vec<_>>()
                .join(", ")
        )
    };

    Ok(ScanResult {
        entities,
        original_text: text,
        highlighted_html: highlighted,
        redacted_html: redacted,
        summary,
        detected_birth_date,
    })
}

/// Export the redacted document
#[tauri::command]
pub async fn export_document(
    text: String,
    entities: Vec<PIIEntity>,
    format: String,
    output_path: String,
) -> Result<String, String> {
    match format.as_str() {
        "txt" => {
            let redacted = redactor::render_redacted_plain(&text, &entities);
            std::fs::write(&output_path, &redacted)
                .map_err(|e| format!("Failed to write file: {}", e))?;
            Ok(output_path)
        }
        "md" => {
            let redacted = redactor::render_redacted_plain(&text, &entities);
            let md = format!(
                "# Redacted Document\n\n{}\n\n---\n*De-identified by Redakt*\n",
                redacted
            );
            std::fs::write(&output_path, &md)
                .map_err(|e| format!("Failed to write file: {}", e))?;
            Ok(output_path)
        }
        "pdf" => {
            export::export_pdf(&text, &entities, &output_path)?;
            Ok(output_path)
        }
        "docx" => {
            export::export_docx(&text, &entities, &output_path)?;
            Ok(output_path)
        }
        _ => Err(format!("Unsupported export format: {}", format)),
    }
}

/// Recalculate entities with age mode toggled (no re-scan needed)
/// Accepts optional birth_date override (DD.MM.YYYY format)
#[tauri::command]
pub fn recalc_age_mode(
    text: String,
    mut entities: Vec<PIIEntity>,
    age_mode: bool,
    language: String,
    birth_date: Option<String>,
) -> Result<ScanResult, String> {
    // Reset all date entity placeholders to standard [DATE_N] format
    anonymizer::reassign_placeholders(&mut entities);

    // If age mode is on, apply age conversion (with optional birth date override)
    let detected_birth_date = if age_mode {
        anonymizer::apply_age_conversion_with_birth(
            &mut entities,
            &text,
            &language,
            birth_date.as_deref(),
        )
    } else {
        // Still detect for display
        anonymizer::detect_birth_date(&entities, &text)
            .map(|(d, _)| d.format("%d.%m.%Y").to_string())
    };

    let highlighted = redactor::render_highlighted_html(&text, &entities);
    let redacted = redactor::render_redacted_html(&text, &entities);

    let enabled = entities.iter().filter(|e| e.enabled).count();
    let total = entities.len();
    let summary = format!("{}/{} entities enabled", enabled, total);

    Ok(ScanResult {
        entities,
        original_text: text,
        highlighted_html: highlighted,
        redacted_html: redacted,
        summary,
        detected_birth_date,
    })
}

/// Get the current LLM server status
#[tauri::command]
pub async fn get_llm_status(llm: State<'_, LlmState>) -> Result<LlmStatus, String> {
    let healthy = llm.check_health().await;
    let model_path = llm.model_path.lock().unwrap().clone();

    Ok(LlmStatus {
        running: healthy,
        model_name: model_path
            .as_ref()
            .and_then(|p| p.file_stem())
            .map(|s| s.to_string_lossy().to_string()),
        model_path: model_path.map(|p| p.to_string_lossy().to_string()),
    })
}

/// Start the LLM server
#[tauri::command]
pub async fn start_llm_server(
    model_path: String,
    server_path: Option<String>,
    llm: State<'_, LlmState>,
) -> Result<bool, String> {
    llm.start_server(&model_path, server_path.as_deref())?;

    // Wait for server to become healthy
    let ready = llm.wait_for_ready(60).await;
    if !ready {
        llm.stop_server();
        return Err("Server failed to start within 60 seconds".to_string());
    }

    Ok(true)
}

/// Stop the LLM server
#[tauri::command]
pub async fn stop_llm_server(llm: State<'_, LlmState>) -> Result<(), String> {
    llm.stop_server();
    Ok(())
}

/// List all discovered GGUF model files (backward compat)
#[tauri::command]
pub fn list_models() -> Vec<crate::llm::GGUFInfo> {
    LlmState::find_models()
}

/// Check if llama-server binary is available
#[tauri::command]
pub fn find_server() -> Option<String> {
    LlmState::find_server().map(|p| p.to_string_lossy().to_string())
}

// ── Settings persistence ──────────────────────────────────────

fn load_settings_from_disk() -> AppSettings {
    let path = download::get_settings_path();
    if path.exists() {
        if let Ok(data) = std::fs::read_to_string(&path) {
            if let Ok(settings) = serde_json::from_str::<AppSettings>(&data) {
                return settings;
            }
        }
    }
    AppSettings::default()
}

fn save_settings_to_disk(settings: &AppSettings) -> Result<(), String> {
    let path = download::get_settings_path();
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| format!("Failed to create settings directory: {}", e))?;
    }
    let data = serde_json::to_string_pretty(settings)
        .map_err(|e| format!("Failed to serialize settings: {}", e))?;
    std::fs::write(&path, &data)
        .map_err(|e| format!("Failed to write settings: {}", e))?;
    Ok(())
}

/// Get application settings
#[tauri::command]
pub fn get_settings() -> AppSettings {
    load_settings_from_disk()
}

/// Save application settings
#[tauri::command]
pub fn save_settings(settings: AppSettings) -> Result<(), String> {
    save_settings_to_disk(&settings)
}

// ── Model catalog ─────────────────────────────────────────────

/// Get the model catalog with download status for each model
#[tauri::command]
pub fn get_model_catalog() -> Vec<ModelCatalogEntry> {
    let settings = load_settings_from_disk();
    download::MODEL_CATALOG
        .iter()
        .map(|m| ModelCatalogEntry {
            id: m.id.to_string(),
            name: m.name.to_string(),
            size_gb: m.size_gb,
            downloaded: download::is_model_downloaded(m.id),
            active: settings.selected_model == m.id,
        })
        .collect()
}

/// Download a specific model by ID
#[tauri::command]
pub async fn download_model(app: tauri::AppHandle, model_id: Option<String>) -> Result<String, String> {
    let id = model_id.unwrap_or_else(|| {
        let settings = load_settings_from_disk();
        settings.selected_model
    });
    download::download_model_by_id(app, &id).await
}

/// Switch to a different model: save settings + restart server
#[tauri::command]
pub async fn switch_model(
    model_id: String,
    llm: State<'_, LlmState>,
) -> Result<bool, String> {
    // Verify the model is downloaded
    let model_path = download::get_model_path(&model_id)
        .ok_or_else(|| format!("Unknown model: {}", model_id))?;

    if !model_path.exists() {
        return Err(format!("Model not downloaded yet: {}", model_id));
    }

    // Save the selection
    let mut settings = load_settings_from_disk();
    settings.selected_model = model_id.clone();
    save_settings_to_disk(&settings)?;

    // Restart LLM server with the new model
    llm.stop_server();
    llm.start_server(
        model_path.to_string_lossy().as_ref(),
        None,
    )?;

    let ready = llm.wait_for_ready(60).await;
    if !ready {
        llm.stop_server();
        return Err("Server failed to start with new model within 60 seconds".to_string());
    }

    Ok(true)
}

/// Check if the selected model needs to be downloaded
#[tauri::command]
pub fn needs_model_download() -> bool {
    let settings = load_settings_from_disk();
    !download::is_model_downloaded(&settings.selected_model)
}

/// Get the path where the selected model will be stored
#[tauri::command]
pub fn get_default_model_path() -> String {
    let settings = load_settings_from_disk();
    download::get_model_path(&settings.selected_model)
        .unwrap_or_else(download::get_default_model_path)
        .to_string_lossy()
        .to_string()
}

/// Toggle a specific entity on/off and return updated HTML
#[tauri::command]
pub fn toggle_entity(
    text: String,
    mut entities: Vec<PIIEntity>,
    index: usize,
    enabled: bool,
) -> Result<ScanResult, String> {
    if index >= entities.len() {
        return Err("Entity index out of bounds".to_string());
    }

    entities[index].enabled = enabled;

    let highlighted = redactor::render_highlighted_html(&text, &entities);
    let redacted = redactor::render_redacted_html(&text, &entities);

    let enabled_count = entities.iter().filter(|e| e.enabled).count();
    let total = entities.len();
    let summary = format!("{}/{} entities enabled", enabled_count, total);

    Ok(ScanResult {
        entities,
        original_text: text,
        highlighted_html: highlighted,
        redacted_html: redacted,
        summary,
        detected_birth_date: None,
    })
}

// ── File parsers ──────────────────────────────────────────────

fn extract_pdf_text(path: &str) -> Result<String, String> {
    pdf_extract::extract_text(path).map_err(|e| format!("PDF extraction failed: {}", e))
}

fn extract_docx_text(path: &str) -> Result<String, String> {
    let file = std::fs::File::open(path).map_err(|e| format!("Cannot open file: {}", e))?;
    let mut archive =
        zip::ZipArchive::new(file).map_err(|e| format!("Invalid DOCX file: {}", e))?;

    let mut doc_xml = String::new();
    if let Ok(mut entry) = archive.by_name("word/document.xml") {
        use std::io::Read;
        entry
            .read_to_string(&mut doc_xml)
            .map_err(|e| format!("Failed to read document.xml: {}", e))?;
    } else {
        return Err("No document.xml found in DOCX".to_string());
    }

    Ok(strip_xml_tags(&doc_xml))
}

fn strip_xml_tags(xml: &str) -> String {
    let mut result = String::new();
    let mut in_tag = false;
    let mut tag_buf = String::new();

    for ch in xml.chars() {
        match ch {
            '<' => {
                in_tag = true;
                tag_buf.clear();
            }
            '>' => {
                in_tag = false;
                let tag = tag_buf.as_str();

                if tag == "/w:p" {
                    if !result.ends_with('\n') {
                        result.push('\n');
                    }
                } else if tag == "w:br" || tag == "w:br/" || tag.starts_with("w:br ") {
                    result.push('\n');
                } else if tag == "w:tab" || tag == "w:tab/" || tag.starts_with("w:tab ") {
                    result.push('\t');
                }

                tag_buf.clear();
            }
            _ if in_tag => {
                tag_buf.push(ch);
            }
            _ => {
                result.push(ch);
            }
        }
    }

    let cleaned = result
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&apos;", "'");

    let mut final_result = String::new();
    let mut newline_count = 0;
    for ch in cleaned.chars() {
        if ch == '\n' {
            newline_count += 1;
            if newline_count <= 2 {
                final_result.push(ch);
            }
        } else {
            newline_count = 0;
            final_result.push(ch);
        }
    }

    final_result.trim().to_string()
}
