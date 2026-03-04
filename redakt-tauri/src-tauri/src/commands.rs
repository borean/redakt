use crate::anonymizer;
use crate::download;
use crate::entities::{AppSettings, LlmStatus, PIIEntity, ScanResult};
use crate::llm::{GGUFInfo, LlmState};
use crate::redactor;
use serde::Serialize;
use std::sync::Mutex;
use tauri::State;

struct AppState {
    current_text: Mutex<String>,
    entities: Mutex<Vec<PIIEntity>>,
    settings: Mutex<AppSettings>,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            current_text: Mutex::new(String::new()),
            entities: Mutex::new(Vec::new()),
            settings: Mutex::new(AppSettings::default()),
        }
    }
}

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
    llm: State<'_, LlmState>,
) -> Result<ScanResult, String> {
    let mut entities = anonymizer::detect_pii(&llm, &text, &language).await?;

    // Apply age conversion (converts date placeholders to age-relative)
    anonymizer::apply_age_conversion(&mut entities, &text, &language);

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
        _ => Err(format!("Unsupported export format: {}", format)),
    }
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

/// List all discovered GGUF model files
#[tauri::command]
pub fn list_models() -> Vec<GGUFInfo> {
    LlmState::find_models()
}

/// Check if llama-server binary is available
#[tauri::command]
pub fn find_server() -> Option<String> {
    LlmState::find_server().map(|p| p.to_string_lossy().to_string())
}

/// Get application settings
#[tauri::command]
pub fn get_settings() -> AppSettings {
    // TODO: Load from persistent storage
    AppSettings::default()
}

/// Save application settings
#[tauri::command]
pub fn save_settings(settings: AppSettings) -> Result<(), String> {
    // TODO: Save to persistent storage
    Ok(())
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
    })
}

/// Download the default Qwen 3.5 model with progress events
#[tauri::command]
pub async fn download_model(app: tauri::AppHandle) -> Result<String, String> {
    download::download_model(app).await
}

/// Check if the default model needs to be downloaded
#[tauri::command]
pub fn needs_model_download() -> bool {
    !download::model_exists()
}

/// Get the path where the default model will be stored
#[tauri::command]
pub fn get_default_model_path() -> String {
    download::get_default_model_path()
        .to_string_lossy()
        .to_string()
}

// ── File parsers ──

fn extract_pdf_text(path: &str) -> Result<String, String> {
    pdf_extract::extract_text(path).map_err(|e| format!("PDF extraction failed: {}", e))
}

fn extract_docx_text(path: &str) -> Result<String, String> {
    // Simple DOCX extraction: unzip and parse document.xml
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

    // Strip XML tags, extract text content
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

                // End of paragraph → newline
                if tag == "/w:p" {
                    if !result.ends_with('\n') {
                        result.push('\n');
                    }
                }
                // Line break within paragraph
                else if tag == "w:br" || tag == "w:br/" || tag.starts_with("w:br ") {
                    result.push('\n');
                }
                // Tab character
                else if tag == "w:tab" || tag == "w:tab/" || tag.starts_with("w:tab ") {
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

    // Clean up XML entities
    let cleaned = result
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&apos;", "'");

    // Collapse excessive blank lines (3+ newlines → 2)
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
