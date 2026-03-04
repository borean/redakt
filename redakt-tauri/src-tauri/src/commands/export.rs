use crate::types::ExportRequest;
use std::fs;

#[tauri::command]
pub fn export_redacted(request: ExportRequest) -> Result<String, String> {
    match request.format.as_str() {
        "txt" => export_txt(&request),
        "md" => export_md(&request),
        _ => export_txt(&request), // Fallback to plain text
    }
}

fn export_txt(request: &ExportRequest) -> Result<String, String> {
    fs::write(&request.output_path, &request.redacted_text)
        .map_err(|e| format!("Failed to write file: {e}"))?;
    Ok(request.output_path.clone())
}

fn export_md(request: &ExportRequest) -> Result<String, String> {
    let original_name = std::path::Path::new(&request.original_path)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("document");

    let content = format!(
        "# Redacted Document\n\n**Source**: {original_name}\n**Processed by**: Redakt (Local De-identification)\n\n---\n\n{}\n",
        request.redacted_text
    );

    fs::write(&request.output_path, &content)
        .map_err(|e| format!("Failed to write file: {e}"))?;
    Ok(request.output_path.clone())
}
