pub mod pdf;
pub mod docx;
pub mod xlsx;
pub mod txt;

use crate::types::DocumentResult;
use std::path::Path;

pub fn parse_document(path: &str) -> Result<DocumentResult, String> {
    let ext = Path::new(path)
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_lowercase();

    match ext.as_str() {
        "pdf" => pdf::extract_text(path),
        "docx" => docx::extract_text(path),
        "xlsx" | "xls" => xlsx::extract_text(path),
        "txt" | "text" | "csv" => txt::extract_text(path),
        "png" | "jpg" | "jpeg" | "bmp" | "tiff" | "tif" => {
            // Images: return empty text, frontend sends to LLM vision
            Ok(DocumentResult {
                text: String::new(),
                metadata: serde_json::json!({
                    "type": "image",
                    "requires_vision": true,
                    "file_name": Path::new(path).file_name().and_then(|n| n.to_str()).unwrap_or(""),
                }),
            })
        }
        _ => Err(format!("Unsupported file type: .{ext}")),
    }
}
