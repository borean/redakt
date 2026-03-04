use crate::types::DocumentResult;
use std::path::Path;

pub fn extract_text(path: &str) -> Result<DocumentResult, String> {
    let bytes = std::fs::read(path).map_err(|e| format!("Failed to read PDF: {e}"))?;
    let text = pdf_extract::extract_text_from_mem(&bytes)
        .map_err(|e| format!("Failed to extract text from PDF: {e}"))?;

    let file_name = Path::new(path)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("")
        .to_string();

    // Count approximate pages by form feeds or large gaps
    let page_count = text.matches('\u{0C}').count().max(1);

    Ok(DocumentResult {
        text,
        metadata: serde_json::json!({
            "type": "pdf",
            "file_name": file_name,
            "pages": page_count,
        }),
    })
}
