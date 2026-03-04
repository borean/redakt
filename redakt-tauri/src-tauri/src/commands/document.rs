use crate::parsers;
use crate::types::DocumentResult;

#[tauri::command]
pub fn read_document(path: String) -> Result<DocumentResult, String> {
    parsers::parse_document(&path)
}
