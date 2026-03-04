use crate::entities::PIIEntity;

/// Category colors matching the manifesto demo exactly
pub fn category_color(category: &str) -> &'static str {
    match category {
        "name" => "#d46b6b",
        "date" => "#d4884e",
        "id" => "#d4a04e",
        "address" => "#6bbd6b",
        "phone" => "#5ba8b5",
        "email" => "#7aabdb",
        "institution" => "#9b8ec4",
        "age" => "#c47a8e",
        "manual" => "#6b8fd4",
        _ => "#808080",
    }
}

/// Render HTML with colored PII highlights (left pane)
pub fn render_highlighted_html(text: &str, entities: &[PIIEntity]) -> String {
    if entities.is_empty() {
        return html_escape(text).replace('\n', "<br>");
    }

    // Find all entity spans in the text
    let mut spans: Vec<(usize, usize, &PIIEntity)> = Vec::new();

    for entity in entities {
        if !entity.enabled {
            continue;
        }
        // Find all occurrences of this entity's original text
        let search = &entity.original;
        let mut start = 0;
        while let Some(pos) = text[start..].find(search.as_str()) {
            let abs_start = start + pos;
            let abs_end = abs_start + search.len();
            spans.push((abs_start, abs_end, entity));
            start = abs_end;
        }
    }

    // Sort by start position, longest first for overlaps
    spans.sort_by(|a, b| a.0.cmp(&b.0).then(b.1.cmp(&a.1)));

    // Remove overlapping spans (keep first/longest)
    let mut filtered: Vec<(usize, usize, &PIIEntity)> = Vec::new();
    let mut last_end = 0;
    for span in &spans {
        if span.0 >= last_end {
            filtered.push(*span);
            last_end = span.1;
        }
    }

    // Build HTML
    let mut html = String::new();
    let mut pos = 0;

    for (start, end, entity) in &filtered {
        // Text before this span
        if *start > pos {
            html.push_str(&html_escape(&text[pos..*start]).replace('\n', "<br>"));
        }
        // The highlighted span
        let color = category_color(&entity.category);
        html.push_str(&format!(
            "<span class=\"pii highlight {}\" style=\"background:{}22;color:{};border:1px solid {}66;border-radius:2px;padding:0 2px;font-weight:600\" title=\"{}: {}\">",
            entity.category, color, color, color, entity.category.to_uppercase(), entity.placeholder
        ));
        html.push_str(&html_escape(&text[*start..*end]));
        html.push_str("</span>");
        pos = *end;
    }

    // Remaining text
    if pos < text.len() {
        html.push_str(&html_escape(&text[pos..]).replace('\n', "<br>"));
    }

    html
}

/// Render HTML with redaction bars (right pane)
pub fn render_redacted_html(text: &str, entities: &[PIIEntity]) -> String {
    if entities.is_empty() {
        return html_escape(text).replace('\n', "<br>");
    }

    let mut spans: Vec<(usize, usize, &PIIEntity)> = Vec::new();

    for entity in entities {
        if !entity.enabled {
            continue;
        }
        let search = &entity.original;
        let mut start = 0;
        while let Some(pos) = text[start..].find(search.as_str()) {
            let abs_start = start + pos;
            let abs_end = abs_start + search.len();
            spans.push((abs_start, abs_end, entity));
            start = abs_end;
        }
    }

    spans.sort_by(|a, b| a.0.cmp(&b.0).then(b.1.cmp(&a.1)));

    let mut filtered: Vec<(usize, usize, &PIIEntity)> = Vec::new();
    let mut last_end = 0;
    for span in &spans {
        if span.0 >= last_end {
            filtered.push(*span);
            last_end = span.1;
        }
    }

    let mut html = String::new();
    let mut pos = 0;

    for (start, end, entity) in &filtered {
        if *start > pos {
            html.push_str(&html_escape(&text[pos..*start]).replace('\n', "<br>"));
        }
        // Age-converted placeholders show readable text instead of blocks
        if is_age_placeholder(&entity.placeholder) {
            let color = category_color("age");
            html.push_str(&format!(
                "<span class=\"pii highlight age\" style=\"background:{}22;color:{};border:1px solid {}66;border-radius:2px;padding:0 2px;font-weight:600\">{}</span>",
                color, color, color, html_escape(&entity.placeholder)
            ));
        } else {
            let block_len = entity.original.len().max(3);
            let blocks: String = std::iter::repeat('\u{2588}').take(block_len).collect();
            html.push_str(&format!(
                "<span class=\"pii redacted\" style=\"background:#808080;color:#808080;border-radius:1px;letter-spacing:-0.5px;font-size:0.65rem;user-select:none\">{}</span>",
                blocks
            ));
        }
        pos = *end;
    }

    if pos < text.len() {
        html.push_str(&html_escape(&text[pos..]).replace('\n', "<br>"));
    }

    html
}

/// Render plain text with placeholder tags for document export (PDF/DOCX)
/// Uses [NAME_1], [DATE_2] etc. instead of block characters for readability
pub fn render_redacted_tagged(text: &str, entities: &[PIIEntity]) -> String {
    let mut result = text.to_string();

    // Sort entities by length descending to replace longest first
    let mut sorted: Vec<&PIIEntity> = entities.iter().filter(|e| e.enabled).collect();
    sorted.sort_by(|a, b| b.original.len().cmp(&a.original.len()));

    for entity in sorted {
        result = result.replace(&entity.original, &entity.placeholder);
    }

    result
}

/// Render plain text with block characters for export
pub fn render_redacted_plain(text: &str, entities: &[PIIEntity]) -> String {
    let mut result = text.to_string();

    // Sort entities by length descending to replace longest first
    let mut sorted: Vec<&PIIEntity> = entities.iter().filter(|e| e.enabled).collect();
    sorted.sort_by(|a, b| b.original.len().cmp(&a.original.len()));

    for entity in sorted {
        if is_age_placeholder(&entity.placeholder) {
            // Age-converted: show the readable age text
            result = result.replace(&entity.original, &entity.placeholder);
        } else {
            let block_len = entity.original.len().max(3);
            let blocks: String = std::iter::repeat('\u{2588}').take(block_len).collect();
            result = result.replace(&entity.original, &blocks);
        }
    }

    result
}

/// Check if a placeholder is an age-converted value (not a standard [TAG_N] placeholder)
fn is_age_placeholder(placeholder: &str) -> bool {
    if placeholder.is_empty() {
        return false;
    }
    // Standard placeholders are like [DATE_1], [NAME_2] etc.
    // Age-converted ones are like "at age 13.67 yrs", "13.67 yaşında", "doğduğu gün"
    !placeholder.starts_with('[')
}

fn html_escape(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}
