use calamine::{open_workbook, Reader, Xlsx};
use crate::types::DocumentResult;
use std::path::Path;

pub fn extract_text(path: &str) -> Result<DocumentResult, String> {
    let mut workbook: Xlsx<_> =
        open_workbook(path).map_err(|e| format!("Failed to open spreadsheet: {e}"))?;

    let mut all_text = Vec::new();
    let sheet_names: Vec<String> = workbook.sheet_names().to_vec();
    let sheet_count = sheet_names.len();

    for name in &sheet_names {
        if let Ok(range) = workbook.worksheet_range(name) {
            let mut sheet_lines = Vec::new();
            for row in range.rows() {
                let cells: Vec<String> = row
                    .iter()
                    .map(|cell| format!("{cell}"))
                    .filter(|s| !s.is_empty())
                    .collect();
                if !cells.is_empty() {
                    sheet_lines.push(cells.join("\t"));
                }
            }
            if !sheet_lines.is_empty() {
                all_text.push(sheet_lines.join("\n"));
            }
        }
    }

    let text = all_text.join("\n\n");
    let file_name = Path::new(path)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("")
        .to_string();

    Ok(DocumentResult {
        text: text.clone(),
        metadata: serde_json::json!({
            "type": "xlsx",
            "file_name": file_name,
            "sheets": sheet_count,
            "char_count": text.len(),
        }),
    })
}
