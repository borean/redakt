use crate::types::DocumentResult;
use std::fs;
use std::path::Path;

pub fn extract_text(path: &str) -> Result<DocumentResult, String> {
    let content = fs::read_to_string(path).map_err(|e| format!("Failed to read file: {e}"))?;
    let file_name = Path::new(path)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("")
        .to_string();

    Ok(DocumentResult {
        text: content.clone(),
        metadata: serde_json::json!({
            "type": "text",
            "file_name": file_name,
            "char_count": content.len(),
        }),
    })
}
