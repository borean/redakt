use crate::types::DocumentResult;
use quick_xml::events::Event;
use quick_xml::reader::Reader;
use std::io::Read;
use std::path::Path;

pub fn extract_text(path: &str) -> Result<DocumentResult, String> {
    let file = std::fs::File::open(path).map_err(|e| format!("Failed to open DOCX: {e}"))?;
    let mut archive = zip::ZipArchive::new(file).map_err(|e| format!("Invalid DOCX (not a ZIP): {e}"))?;

    // Read word/document.xml
    let mut doc_xml = String::new();
    {
        let mut entry = archive
            .by_name("word/document.xml")
            .map_err(|e| format!("Missing word/document.xml: {e}"))?;
        entry
            .read_to_string(&mut doc_xml)
            .map_err(|e| format!("Failed to read document.xml: {e}"))?;
    }

    let text = extract_text_from_xml(&doc_xml);

    let file_name = Path::new(path)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("")
        .to_string();

    Ok(DocumentResult {
        text: text.clone(),
        metadata: serde_json::json!({
            "type": "docx",
            "file_name": file_name,
            "char_count": text.len(),
        }),
    })
}

fn extract_text_from_xml(xml: &str) -> String {
    let mut reader = Reader::from_str(xml);
    let mut paragraphs: Vec<String> = Vec::new();
    let mut current_paragraph = String::new();
    let mut in_text = false;
    let mut in_paragraph = false;
    let mut buf = Vec::new();

    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::Start(ref e)) => {
                let local = e.local_name();
                match local.as_ref() {
                    b"p" => {
                        in_paragraph = true;
                        current_paragraph.clear();
                    }
                    b"t" => {
                        in_text = true;
                    }
                    b"tab" => {
                        if in_paragraph {
                            current_paragraph.push('\t');
                        }
                    }
                    b"br" => {
                        if in_paragraph {
                            current_paragraph.push('\n');
                        }
                    }
                    _ => {}
                }
            }
            Ok(Event::End(ref e)) => {
                let local = e.local_name();
                match local.as_ref() {
                    b"p" => {
                        if in_paragraph {
                            paragraphs.push(current_paragraph.clone());
                            current_paragraph.clear();
                            in_paragraph = false;
                        }
                    }
                    b"t" => {
                        in_text = false;
                    }
                    _ => {}
                }
            }
            Ok(Event::Text(ref e)) => {
                if in_text && in_paragraph {
                    if let Ok(text) = e.unescape() {
                        current_paragraph.push_str(&text);
                    }
                }
            }
            Ok(Event::Eof) => break,
            Err(e) => {
                eprintln!("XML parse error: {e}");
                break;
            }
            _ => {}
        }
        buf.clear();
    }

    paragraphs.join("\n")
}
