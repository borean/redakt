use crate::entities::PIIEntity;
use crate::redactor;

/// Generate a proper PDF file with the redacted text
pub fn export_pdf(text: &str, entities: &[PIIEntity], output_path: &str) -> Result<(), String> {
    let redacted = redactor::render_redacted_tagged(text, entities);
    write_pdf(&redacted, output_path)
}

/// Generate a proper DOCX file with the redacted text
pub fn export_docx(text: &str, entities: &[PIIEntity], output_path: &str) -> Result<(), String> {
    let redacted = redactor::render_redacted_tagged(text, entities);
    write_docx(&redacted, output_path)
}

// ── PDF export ───────────────────────────────────────────────────

fn write_pdf(text: &str, output_path: &str) -> Result<(), String> {
    use printpdf::*;
    use std::fs::File;
    use std::io::BufWriter;

    let (doc, page1, layer1) = PdfDocument::new(
        "Redacted Document",
        Mm(210.0),
        Mm(297.0),
        "Text",
    );

    // Load system font (with Turkish/Unicode support)
    let font = load_system_font(&doc)?;

    let font_size = 10.0_f32;
    let line_height_mm = 4.5_f32; // ~12.75pt in mm
    let margin_left = 25.0_f32;
    let margin_top = 272.0_f32; // 297 - 25
    let margin_bottom = 25.0_f32;
    let usable_height = margin_top - margin_bottom;
    let max_lines_per_page = (usable_height / line_height_mm) as usize;

    let lines: Vec<&str> = text.lines().collect();
    let mut line_idx = 0;
    let mut page_idx = page1;
    let mut layer_idx = layer1;

    for line in &lines {
        // Check if we need a new page
        if line_idx > 0 && line_idx % max_lines_per_page == 0 {
            let (new_page, new_layer) =
                doc.add_page(Mm(210.0), Mm(297.0), "Text");
            page_idx = new_page;
            layer_idx = new_layer;
        }

        let y_pos = margin_top - ((line_idx % max_lines_per_page) as f32 * line_height_mm);

        let current_layer = doc.get_page(page_idx).get_layer(layer_idx);
        current_layer.use_text(line.to_string(), font_size, Mm(margin_left), Mm(y_pos), &font);

        line_idx += 1;
    }

    let file = File::create(output_path)
        .map_err(|e| format!("Failed to create PDF file: {}", e))?;
    doc.save(&mut BufWriter::new(file))
        .map_err(|e| format!("Failed to save PDF: {}", e))?;

    Ok(())
}

fn load_system_font(
    doc: &printpdf::PdfDocumentReference,
) -> Result<printpdf::IndirectFontRef, String> {
    // Try system fonts in order of preference (Unicode support)
    let font_paths = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        // Linux fallbacks
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        // Windows fallbacks
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\cour.ttf",
    ];

    for path in &font_paths {
        if let Ok(file) = std::fs::File::open(path) {
            match doc.add_external_font(file) {
                Ok(font) => return Ok(font),
                Err(_) => continue,
            }
        }
    }

    // Last resort: built-in Courier (ASCII only, Turkish chars may not render)
    doc.add_builtin_font(printpdf::BuiltinFont::Courier)
        .map_err(|e| format!("Failed to add fallback font: {}", e))
}

// ── DOCX export ──────────────────────────────────────────────────

fn write_docx(text: &str, output_path: &str) -> Result<(), String> {
    use std::io::Write;
    use zip::write::SimpleFileOptions;
    use zip::ZipWriter;

    let file = std::fs::File::create(output_path)
        .map_err(|e| format!("Failed to create DOCX file: {}", e))?;
    let mut zip = ZipWriter::new(file);
    let options = SimpleFileOptions::default()
        .compression_method(zip::CompressionMethod::Deflated);

    // [Content_Types].xml
    zip.start_file("[Content_Types].xml", options)
        .map_err(|e| format!("DOCX write error: {}", e))?;
    zip.write_all(CONTENT_TYPES_XML.as_bytes())
        .map_err(|e| format!("DOCX write error: {}", e))?;

    // _rels/.rels
    zip.start_file("_rels/.rels", options)
        .map_err(|e| format!("DOCX write error: {}", e))?;
    zip.write_all(RELS_XML.as_bytes())
        .map_err(|e| format!("DOCX write error: {}", e))?;

    // word/_rels/document.xml.rels
    zip.start_file("word/_rels/document.xml.rels", options)
        .map_err(|e| format!("DOCX write error: {}", e))?;
    zip.write_all(DOC_RELS_XML.as_bytes())
        .map_err(|e| format!("DOCX write error: {}", e))?;

    // word/document.xml — the actual content
    zip.start_file("word/document.xml", options)
        .map_err(|e| format!("DOCX write error: {}", e))?;
    let doc_xml = build_document_xml(text);
    zip.write_all(doc_xml.as_bytes())
        .map_err(|e| format!("DOCX write error: {}", e))?;

    zip.finish()
        .map_err(|e| format!("Failed to finalize DOCX: {}", e))?;

    Ok(())
}

fn xml_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

fn build_document_xml(text: &str) -> String {
    let mut paragraphs = String::new();

    for line in text.lines() {
        if line.trim().is_empty() {
            paragraphs.push_str("      <w:p/>\n");
        } else {
            paragraphs.push_str(&format!(
                "      <w:p><w:pPr><w:rPr><w:rFonts w:ascii=\"Courier New\" w:hAnsi=\"Courier New\" w:cs=\"Courier New\"/><w:sz w:val=\"20\"/></w:rPr></w:pPr><w:r><w:rPr><w:rFonts w:ascii=\"Courier New\" w:hAnsi=\"Courier New\" w:cs=\"Courier New\"/><w:sz w:val=\"20\"/></w:rPr><w:t xml:space=\"preserve\">{}</w:t></w:r></w:p>\n",
                xml_escape(line)
            ));
        }
    }

    format!(
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas"
            xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
            xmlns:o="urn:schemas-microsoft-com:office:office"
            xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
            xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"
            xmlns:v="urn:schemas-microsoft-com:vml"
            xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
            xmlns:w10="urn:schemas-microsoft-com:office:word"
            xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"
            xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup"
            xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk"
            xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml"
            xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
            mc:Ignorable="w14 wp14">
  <w:body>
{}    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>"#,
        paragraphs
    )
}

const CONTENT_TYPES_XML: &str = r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"#;

const RELS_XML: &str = r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"#;

const DOC_RELS_XML: &str = r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
</Relationships>"#;
