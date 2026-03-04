use crate::entities::{normalize_category, PIIEntity};
use crate::llm::LlmState;
use chrono::{Datelike, NaiveDate};
use regex::Regex;
use serde::Deserialize;
use std::collections::HashMap;

#[derive(Debug, Deserialize)]
struct LlmPIIResponse {
    entities: Option<Vec<LlmEntity>>,
}

#[derive(Debug, Deserialize)]
struct LlmEntity {
    original: Option<String>,
    category: Option<String>,
    #[serde(default)]
    confidence: Option<f64>,
}

const SYSTEM_PROMPT_EN: &str = r#"You are a medical document de-identification specialist. Your task is to detect all personally identifiable information (PII) in the given text and report it in structured JSON format.

PII categories to detect:
- name: Patient name, physician name, parent name, nurse name, etc.
- date: Dates found in the document. Use specific subtypes as the category value:
  - date_of_birth: Birth date, date of birth, DOB
  - visit_date: Visit/examination/consultation date
  - report_date: Report date, result date
  - admission_date: Admission date, discharge date
  - date: Any other date that doesn't fit above
- id: National ID number, protocol number, patient number, insurance number
- address: Street, district, city, postal code
- phone: Phone numbers (landline and mobile). IMPORTANT: Date-time strings (e.g. "23.01.2023 11:55", "12.06.2023 18") are NOT phone numbers — classify them as "date".
- email: Email addresses
- institution: Hospital name, clinic name, school name, pharmacy name
- age: Patient age (e.g., "3 years old", "14 months old"). NOTE: Time intervals like "3 months later", "in 2 weeks", "after 1 year" are NOT PII.

Rules:
1. Medical terms, drug names, diagnosis codes (ICD) are NOT PII - do not include them.
2. Laboratory values are not PII.
3. Create incrementally numbered placeholders for each unique entity: [NAME_1], [NAME_2], [DATE_1], etc.
4. If the same person appears multiple times, use the SAME placeholder each time.
5. Use the EXACT text from the document in the "original" field (including case).
6. Only report information actually present in the text, do not fabricate.
7. Time intervals ("3 months later", "in 2 weeks", "after 1 year", "every 6 months") are NOT PII - do not include them.

IMPORTANT: Return your response as a valid JSON object with "entities" array and "summary" string. Every string key and value must use double quotes. Do NOT use markdown fences or trailing commas."#;

const SYSTEM_PROMPT_TR: &str = r#"Sen bir tıbbi belge anonimleştirme uzmanısın. Görevin, verilen metindeki tüm kişisel verileri (KVKK kapsamında) tespit etmek ve yapılandırılmış JSON formatında raporlamaktır.

Tespit etmen gereken kişisel veri kategorileri:
- name: Hasta adı, hekim adı, ebeveyn adı, hemşire adı, vb.
- date: Belgede geçen tarihler. Kategori olarak spesifik alt tip kullan:
  - date_of_birth: Doğum tarihi
  - visit_date: Muayene/kontrol tarihi
  - report_date: Rapor tarihi, sonuç tarihi
  - admission_date: Yatış/taburcu tarihi
  - date: Yukarıdakilere uymayan diğer tarihler
- id: TC Kimlik No, protokol numarası, hasta numarası, sigorta numarası
- address: Sokak, mahalle, ilçe, il, posta kodu
- phone: Telefon numaraları (sabit ve mobil). DİKKAT: Tarih ve saat bilgileri (örn: "23.01.2023 11:55", "12.06.2023 18") telefon numarası DEĞİLDİR — bunları "date" olarak sınıflandır.
- email: E-posta adresleri
- institution: Hastane adı, klinik adı, okul adı, eczane adı
- age: Hasta yaşı (örn: "3 yaşında", "14 aylık", "5 günlük"). DİKKAT: "3 ay sonra", "2 hafta sonra", "1 yıl içinde" gibi zaman aralıkları kişisel veri DEĞİLDİR.

Kurallar:
1. Tıbbi terimler, ilaç adları, tanı kodları (ICD) KİŞİSEL VERİ DEĞİLDİR - bunları dahil etme.
2. Laboratuvar değerleri kişisel veri değildir.
3. Her benzersiz varlık için artan numaralı yer tutucular oluştur: [AD_1], [AD_2], [TARIH_1], vb.
4. Aynı kişi birden fazla kez geçiyorsa, her seferinde AYNI yer tutucuyu kullan.
5. "original" alanında metindeki TAM ifadeyi kullan (büyük/küçük harf dahil).
6. Sadece gerçekten metinde bulunan bilgileri raporla, uydurma ekleme.
7. Zaman aralıkları ("3 ay sonra", "2 hafta sonra", "1 yıl içinde", "her 6 ayda bir") kişisel veri DEĞİLDİR - bunları dahil etme.

ÖNEMLİ: Cevabını "entities" dizisi ve "summary" alanı içeren geçerli bir JSON nesnesi olarak döndür. Tüm anahtar ve değerlerde çift tırnak kullan. Markdown fence kullanma, sonda virgül bırakma."#;

/// Truncate text to fit within context window.
/// With 32K context, ~4K for system prompt + output, leaves ~28K tokens (~100K chars) for input.
fn truncate_for_context(text: &str, max_chars: usize) -> &str {
    if text.len() <= max_chars {
        return text;
    }
    // Find the last complete line within the limit
    match text[..max_chars].rfind('\n') {
        Some(pos) => &text[..pos],
        None => &text[..max_chars],
    }
}

/// Run the full PII detection pipeline
pub async fn detect_pii(
    llm: &LlmState,
    text: &str,
    language: &str,
) -> Result<Vec<PIIEntity>, String> {
    // Step 1: LLM inference
    let system_prompt = if language == "tr" {
        SYSTEM_PROMPT_TR
    } else {
        SYSTEM_PROMPT_EN
    };

    // Truncate very long documents to stay within context window
    // 32K context ≈ 100K chars max, minus system prompt and output headroom
    let safe_text = truncate_for_context(text, 90_000);

    let user_prompt = if language == "tr" {
        format!(
            "Aşağıdaki tıbbi belge metnindeki tüm kişisel verileri tespit et:\n\n---\n{}\n---",
            safe_text
        )
    } else {
        format!(
            "Detect all personally identifiable information in the following medical document text:\n\n---\n{}\n---",
            safe_text
        )
    };

    let raw_response = llm.chat_completion(system_prompt, &user_prompt).await?;

    // Step 2: Parse LLM response (with error recovery)
    let mut entities = parse_llm_response(&raw_response)?;

    // Step 3: Reclassify misidentified entities (dates tagged as phone, etc.)
    reclassify_misidentified(&mut entities);

    // Step 4: Post-LLM regex supplement
    let regex_entities = regex_supplement(text, language);
    for re in regex_entities {
        // Only add if not already found by LLM
        if !entities.iter().any(|e| e.original == re.original) {
            entities.push(re);
        }
    }

    // Step 5: Assign placeholders
    assign_placeholders(&mut entities);

    Ok(entities)
}

/// Convert LlmEntity vec to PIIEntity vec (shared by all parse paths)
fn convert_llm_entities(ents: Vec<LlmEntity>) -> Vec<PIIEntity> {
    ents.into_iter()
        .filter_map(|e| {
            let original = e.original?.trim().to_string();
            if original.is_empty() {
                return None;
            }
            let raw_cat = e.category?;
            let category = normalize_category(&raw_cat).to_string();
            let subcategory = if raw_cat.to_lowercase() != category {
                Some(raw_cat.to_lowercase())
            } else {
                None
            };
            Some(PIIEntity {
                original,
                category,
                subcategory,
                placeholder: String::new(),
                confidence: e.confidence.unwrap_or(0.9),
                enabled: true,
                start: None,
                end: None,
            })
        })
        .collect()
}

fn parse_llm_response(raw: &str) -> Result<Vec<PIIEntity>, String> {
    // Strip <think>...</think> blocks (Qwen 3.5 thinking tokens)
    let mut text = raw.to_string();
    while let Some(start) = text.find("<think>") {
        if let Some(end) = text.find("</think>") {
            text = format!("{}{}", &text[..start], &text[end + 8..]);
        } else {
            // Unclosed think tag — strip everything from <think> onward
            text = text[..start].to_string();
            break;
        }
    }

    // Try to fix common JSON issues
    let cleaned = text
        .trim()
        .trim_start_matches("```json")
        .trim_start_matches("```")
        .trim_end_matches("```")
        .trim();

    // Try to parse as-is
    if let Ok(resp) = serde_json::from_str::<LlmPIIResponse>(cleaned) {
        if let Some(ents) = resp.entities {
            return Ok(convert_llm_entities(ents));
        }
    }

    // Try to extract entities array even from malformed JSON
    if let Some(start) = cleaned.find("[") {
        let from_bracket = &cleaned[start..];
        // Find matching close bracket
        let mut depth = 0;
        let mut end_idx = from_bracket.len();
        let mut found_close = false;
        for (i, ch) in from_bracket.char_indices() {
            match ch {
                '[' => depth += 1,
                ']' => {
                    depth -= 1;
                    if depth == 0 {
                        end_idx = i + 1;
                        found_close = true;
                        break;
                    }
                }
                _ => {}
            }
        }
        let array_str = &from_bracket[..end_idx];
        // Remove trailing commas before ]
        let fixed = Regex::new(r",\s*\]")
            .unwrap()
            .replace_all(array_str, "]");

        if let Ok(ents) = serde_json::from_str::<Vec<LlmEntity>>(&fixed) {
            return Ok(convert_llm_entities(ents));
        }

        // If the array wasn't closed, the response was truncated.
        // Salvage complete entity objects by finding individual {...} blocks.
        if !found_close {
            let mut salvaged = Vec::new();
            let mut search_start = 0;
            let bytes = from_bracket.as_bytes();
            while search_start < bytes.len() {
                if let Some(obj_start) = from_bracket[search_start..].find('{') {
                    let abs_start = search_start + obj_start;
                    let mut d = 0;
                    let mut obj_end = None;
                    for (i, ch) in from_bracket[abs_start..].char_indices() {
                        match ch {
                            '{' => d += 1,
                            '}' => {
                                d -= 1;
                                if d == 0 {
                                    obj_end = Some(abs_start + i + 1);
                                    break;
                                }
                            }
                            _ => {}
                        }
                    }
                    if let Some(oe) = obj_end {
                        let obj_str = &from_bracket[abs_start..oe];
                        if let Ok(e) = serde_json::from_str::<LlmEntity>(obj_str) {
                            salvaged.push(e);
                        }
                        search_start = oe;
                    } else {
                        break; // Incomplete object — stop
                    }
                } else {
                    break;
                }
            }
            if !salvaged.is_empty() {
                return Ok(convert_llm_entities(salvaged));
            }
        }
    }

    // Fallback: try to parse as flat key-value objects where keys are category names.
    // Small models (0.8B) sometimes return: {"entities": [{"name": "John", "date": "01.01.2000", ...}]}
    if let Some(start) = cleaned.find("[") {
        let from_bracket = &cleaned[start..];
        if let Ok(flat_objs) = serde_json::from_str::<Vec<serde_json::Map<String, serde_json::Value>>>(from_bracket)
            .or_else(|_| {
                // Try fixing truncated array
                let mut s = from_bracket.to_string();
                if !s.trim().ends_with(']') {
                    // Find last complete object
                    if let Some(last_close) = s.rfind('}') {
                        s.truncate(last_close + 1);
                        s.push(']');
                    }
                }
                let fixed = regex::Regex::new(r",\s*\]").unwrap().replace_all(&s, "]");
                serde_json::from_str::<Vec<serde_json::Map<String, serde_json::Value>>>(&fixed)
            })
        {
            let mut entities = Vec::new();
            for obj in &flat_objs {
                for (key, value) in obj {
                    let val_str = match value {
                        serde_json::Value::String(s) => s.trim().to_string(),
                        serde_json::Value::Number(n) => n.to_string(),
                        _ => continue,
                    };
                    if val_str.is_empty() {
                        continue;
                    }
                    // Skip non-PII keys like "summary", "count", etc.
                    let category = normalize_category(key);
                    // Only accept known PII categories
                    if !crate::entities::CATEGORIES.contains(&category) {
                        continue;
                    }
                    entities.push(PIIEntity {
                        original: val_str,
                        category: category.to_string(),
                        subcategory: if key.to_lowercase() != category {
                            Some(key.to_lowercase())
                        } else {
                            None
                        },
                        placeholder: String::new(),
                        confidence: 0.7, // Lower confidence for flat-format responses
                        enabled: true,
                        start: None,
                        end: None,
                    });
                }
            }
            if !entities.is_empty() {
                return Ok(entities);
            }
        }
    }

    // Include a snippet of the raw response for debugging
    let raw_preview: String = raw.chars().take(300).collect();
    Err(format!("Failed to parse LLM response as JSON. Raw response: {}", raw_preview))
}

/// Reclassify entities the LLM mis-categorized.
/// Common case: dates with hours (e.g. "23.01.2023 11") tagged as "phone".
fn reclassify_misidentified(entities: &mut Vec<PIIEntity>) {
    let date_re = Regex::new(
        r"(?:\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}|\d{4}-\d{1,2}-\d{1,2}|\d{4}/\d{1,2}/\d{1,2})"
    ).unwrap();
    for entity in entities.iter_mut() {
        if entity.category == "phone" && date_re.is_match(&entity.original) {
            entity.category = "date".to_string();
            entity.subcategory = Some("date".to_string());
        }
    }
}

/// Regex-based PII supplement (catches what LLM misses)
/// Only supplements TC Kimlik IDs — phone/email detection is left to the LLM
/// to avoid false positives where dates get matched as phone numbers.
fn regex_supplement(text: &str, _language: &str) -> Vec<PIIEntity> {
    let mut entities = Vec::new();

    // Turkish TC Kimlik (11-digit national ID)
    let tc_re = Regex::new(r"\b\d{11}\b").unwrap();
    for m in tc_re.find_iter(text) {
        let val = m.as_str();
        // Basic TC validation: first digit != 0
        if val.starts_with('0') {
            continue;
        }
        entities.push(PIIEntity {
            original: val.to_string(),
            category: "id".to_string(),
            subcategory: Some("tc_kimlik".to_string()),
            placeholder: String::new(),
            confidence: 0.85,
            enabled: true,
            start: Some(m.start()),
            end: Some(m.end()),
        });
    }

    entities
}

/// Public re-assign: clear all placeholders and re-number from scratch.
/// Used when toggling age mode (to reset date placeholders before optionally re-applying age conversion).
pub fn reassign_placeholders(entities: &mut Vec<PIIEntity>) {
    assign_placeholders(entities);
}

/// Assign unique placeholders like [AD_1], [TARİH_2]
fn assign_placeholders(entities: &mut Vec<PIIEntity>) {
    let mut counters = HashMap::new();

    let label_map = HashMap::from([
        ("name", "NAME"),
        ("date", "DATE"),
        ("id", "ID"),
        ("address", "ADDR"),
        ("phone", "PHONE"),
        ("email", "EMAIL"),
        ("institution", "INST"),
        ("age", "AGE"),
    ]);

    for entity in entities.iter_mut() {
        let label = label_map
            .get(entity.category.as_str())
            .unwrap_or(&"PII");
        let count = counters
            .entry(entity.category.clone())
            .or_insert(0u32);
        *count += 1;
        entity.placeholder = format!("[{}_{}]", label, count);
    }
}

// ── Age conversion system ────────────────────────────────────────────

/// Turkish month name → month number
fn turkish_month(s: &str) -> Option<u32> {
    match s {
        "ocak" => Some(1),
        "şubat" | "subat" => Some(2),
        "mart" => Some(3),
        "nisan" => Some(4),
        "mayıs" | "mayis" => Some(5),
        "haziran" => Some(6),
        "temmuz" => Some(7),
        "ağustos" | "agustos" => Some(8),
        "eylül" | "eylul" => Some(9),
        "ekim" => Some(10),
        "kasım" | "kasim" => Some(11),
        "aralık" | "aralik" => Some(12),
        _ => None,
    }
}

/// English month name → month number
fn english_month(s: &str) -> Option<u32> {
    match s {
        "january" | "jan" => Some(1),
        "february" | "feb" => Some(2),
        "march" | "mar" => Some(3),
        "april" | "apr" => Some(4),
        "may" => Some(5),
        "june" | "jun" => Some(6),
        "july" | "jul" => Some(7),
        "august" | "aug" => Some(8),
        "september" | "sep" => Some(9),
        "october" | "oct" => Some(10),
        "november" | "nov" => Some(11),
        "december" | "dec" => Some(12),
        _ => None,
    }
}

fn any_month(s: &str) -> Option<u32> {
    turkish_month(s).or_else(|| english_month(s))
}

fn expand_year(y: i32) -> i32 {
    if y < 50 { y + 2000 } else if y < 100 { y + 1900 } else { y }
}

/// Parse date text into NaiveDate (ports Python _parse_date)
fn parse_date(text: &str) -> Option<NaiveDate> {
    let text = text.trim().replace('\u{00a0}', " ");

    // DD.MM.YYYY or DD/MM/YYYY or DD-MM-YYYY
    let re1 = Regex::new(r"^(\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})\b").unwrap();
    if let Some(caps) = re1.captures(&text) {
        let d: u32 = caps[1].parse().ok()?;
        let m: u32 = caps[2].parse().ok()?;
        let y: i32 = caps[3].parse().ok()?;
        if let Some(date) = NaiveDate::from_ymd_opt(expand_year(y), m, d) {
            return Some(date);
        }
    }

    // YYYY-MM-DD (ISO)
    let re2 = Regex::new(r"^(\d{4})-(\d{1,2})-(\d{1,2})\b").unwrap();
    if let Some(caps) = re2.captures(&text) {
        let y: i32 = caps[1].parse().ok()?;
        let m: u32 = caps[2].parse().ok()?;
        let d: u32 = caps[3].parse().ok()?;
        if let Some(date) = NaiveDate::from_ymd_opt(y, m, d) {
            return Some(date);
        }
    }

    // YYYY/MM/DD
    let re3 = Regex::new(r"^(\d{4})/(\d{1,2})/(\d{1,2})\b").unwrap();
    if let Some(caps) = re3.captures(&text) {
        let y: i32 = caps[1].parse().ok()?;
        let m: u32 = caps[2].parse().ok()?;
        let d: u32 = caps[3].parse().ok()?;
        if let Some(date) = NaiveDate::from_ymd_opt(y, m, d) {
            return Some(date);
        }
    }

    // DD Month YYYY (Turkish or English)
    let re4 = Regex::new(r"(?i)^(\d{1,2})[\s.\-]+([a-zA-ZçğıöşüÇĞİÖŞÜ]+)[\s.\-]+(\d{4})\b").unwrap();
    if let Some(caps) = re4.captures(&text) {
        let d: u32 = caps[1].parse().ok()?;
        let month_str = caps[2].to_lowercase();
        let y: i32 = caps[3].parse().ok()?;
        if let Some(m) = any_month(&month_str) {
            if let Some(date) = NaiveDate::from_ymd_opt(y, m, d) {
                return Some(date);
            }
        }
    }

    // Month DD, YYYY (English: "March 15, 2012")
    let re5 = Regex::new(r"(?i)^([a-zA-ZçğıöşüÇĞİÖŞÜ]+)[\s.\-]+(\d{1,2}),?\s*(\d{4})\b").unwrap();
    if let Some(caps) = re5.captures(&text) {
        let month_str = caps[1].to_lowercase();
        let d: u32 = caps[2].parse().ok()?;
        let y: i32 = caps[3].parse().ok()?;
        if let Some(m) = any_month(&month_str) {
            if let Some(date) = NaiveDate::from_ymd_opt(y, m, d) {
                return Some(date);
            }
        }
    }

    // Month YYYY ("Ekim 2019", "Mar 2012") — day defaults to 1
    let re6 = Regex::new(r"(?i)^([a-zA-ZçğıöşüÇĞİÖŞÜ]+)[\s.\-]+(\d{4})\b").unwrap();
    if let Some(caps) = re6.captures(&text) {
        let month_str = caps[1].to_lowercase();
        let y: i32 = caps[2].parse().ok()?;
        if let Some(m) = any_month(&month_str) {
            if let Some(date) = NaiveDate::from_ymd_opt(y, m, 1) {
                return Some(date);
            }
        }
    }

    // YYYY Month ("2019 Ekim")
    let re7 = Regex::new(r"(?i)^(\d{4})[\s.\-]+([a-zA-ZçğıöşüÇĞİÖŞÜ]+)\b").unwrap();
    if let Some(caps) = re7.captures(&text) {
        let y: i32 = caps[1].parse().ok()?;
        let month_str = caps[2].to_lowercase();
        if let Some(m) = any_month(&month_str) {
            if let Some(date) = NaiveDate::from_ymd_opt(y, m, 1) {
                return Some(date);
            }
        }
    }

    // MM/YYYY or MM.YYYY
    let re8 = Regex::new(r"^(\d{1,2})[./](\d{4})\b").unwrap();
    if let Some(caps) = re8.captures(&text) {
        let m: u32 = caps[1].parse().ok()?;
        let y: i32 = caps[2].parse().ok()?;
        if (1..=12).contains(&m) {
            if let Some(date) = NaiveDate::from_ymd_opt(y, m, 1) {
                return Some(date);
            }
        }
    }

    // Standalone 4-digit year
    let re9 = Regex::new(r"^(\d{4})$").unwrap();
    if let Some(caps) = re9.captures(text.trim()) {
        let y: i32 = caps[1].parse().ok()?;
        if (1900..=2100).contains(&y) {
            return NaiveDate::from_ymd_opt(y, 1, 1);
        }
    }

    // Fallback: search for a date anywhere in the text
    let re_fb1 = Regex::new(r"(\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})").unwrap();
    if let Some(caps) = re_fb1.captures(&text) {
        let d: u32 = caps[1].parse().ok()?;
        let m: u32 = caps[2].parse().ok()?;
        let y: i32 = caps[3].parse().ok()?;
        if let Some(date) = NaiveDate::from_ymd_opt(expand_year(y), m, d) {
            return Some(date);
        }
    }

    let re_fb2 = Regex::new(r"(\d{4})-(\d{1,2})-(\d{1,2})").unwrap();
    if let Some(caps) = re_fb2.captures(&text) {
        let y: i32 = caps[1].parse().ok()?;
        let m: u32 = caps[2].parse().ok()?;
        let d: u32 = caps[3].parse().ok()?;
        if let Some(date) = NaiveDate::from_ymd_opt(y, m, d) {
            return Some(date);
        }
    }

    // Fallback: standalone year anywhere in text (e.g. "menarş 2022")
    let re_fb3 = Regex::new(r"\b(\d{4})\b").unwrap();
    if let Some(caps) = re_fb3.captures(&text) {
        let y: i32 = caps[1].parse().ok()?;
        if (1900..=2100).contains(&y) {
            return NaiveDate::from_ymd_opt(y, 1, 1);
        }
    }

    None
}

/// Calculate (years, months) difference between birth and event date
fn calc_age_diff(birth: NaiveDate, event: NaiveDate) -> (i32, i32) {
    let mut years = event.year() - birth.year();
    let mut months = event.month() as i32 - birth.month() as i32;
    if event.day() < birth.day() {
        months -= 1;
    }
    if months < 0 {
        years -= 1;
        months += 12;
    }
    (years.max(0), months.max(0))
}

fn is_plausible_birth_date(d: NaiveDate) -> bool {
    let today = chrono::Local::now().date_naive();
    let age = today.year() - d.year() - if (today.month(), today.day()) < (d.month(), d.day()) { 1 } else { 0 };
    (0..=120).contains(&age)
}

/// Birth date subcategories the LLM might assign
const BIRTH_DATE_SUBCATS: &[&str] = &[
    "birth_date", "date_of_birth", "dob", "dogum_tarihi", "doğum_tarihi", "dogum", "doğum",
];

/// Context patterns BEFORE a date that indicate birth date
const BIRTH_CONTEXT_BEFORE: &[&str] = &[
    "doğum tarihi", "dogum tarihi", "doğum tar.", "d.tarihi", "dtarihi", "d. tarihi", "d tarihi",
    "doğum:", "dogum:", "doğ.tar.", "doğ.tar:", "doğ tar",
    "d.t.", "d.t:", "dt:", "dt.",
    "yaş:", "yas:", "yaşı:", "yasi:",
    "doğ:", "dog:",
    "date of birth", "birth date", "birthdate", "born on", "born:",
    "dob:", "dob ", "dob.", "d.o.b.", "d.o.b:",
    "doğum", "dogum",
];

/// Context patterns AFTER a date that indicate birth date
const BIRTH_CONTEXT_AFTER: &[&str] = &[
    "doğumlu", "dogumlu", "doğ.", "doğumludur", "dogumludur",
    "born", "d.t.", "doğum tarihli", "dogum tarihli",
];

/// Strategy 0: Regex scan the document text for explicit birth date references
fn find_birth_date_by_regex_scan(document_text: &str) -> Option<NaiveDate> {
    if document_text.is_empty() {
        return None;
    }

    let date_num = r"(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4})";
    let date_iso = r"(\d{4}-\d{1,2}-\d{1,2})";
    let date_named = r"(\d{1,2}\s+\w+\s+\d{4})";
    let opt_paren = r"(?:\s*\([^)]*\))?";

    let raw_patterns = vec![
        // Turkish
        format!(r"(?i)do[gğ]um\s*tarihi{}\s*[:=]?\s*{}", opt_paren, date_num),
        format!(r"(?i)do[gğ]um\s*tarihi{}\s*[:=]?\s*{}", opt_paren, date_iso),
        format!(r"(?i)do[gğ]um\s*tarihi{}\s*[:=]?\s*{}", opt_paren, date_named),
        format!(r"(?i)d\.?\s*tarihi{}\s*[:=]?\s*{}", opt_paren, date_num),
        format!(r"(?i)d\.?\s*tarihi{}\s*[:=]?\s*{}", opt_paren, date_iso),
        format!(r"(?i)d\.?\s*t\.?\s*[:=]\s*{}", date_num),
        format!(r"(?i)do[gğ]umlu\s*[:=]?\s*{}", date_num),
        format!(r"(?i){}\s*do[gğ]umlu", date_num),
        format!(r"(?i)do[gğ]\.?\s*tar\.?\s*[:=]?\s*{}", date_num),
        // English
        format!(r"(?i)(?:date\s*of\s*birth|dob|birth\s*date){}\s*[:=]?\s*{}", opt_paren, date_num),
        format!(r"(?i)(?:date\s*of\s*birth|dob|birth\s*date){}\s*[:=]?\s*{}", opt_paren, date_iso),
        format!(r"(?i)born\s+(?:on\s+)?{}", date_num),
        format!(r"(?i)d\.o\.b\.?\s*[:=]?\s*{}", date_num),
    ];

    for pat in &raw_patterns {
        if let Ok(re) = Regex::new(pat) {
            if let Some(caps) = re.captures(document_text) {
                if let Some(date_str) = caps.get(1) {
                    if let Some(parsed) = parse_date(date_str.as_str()) {
                        if is_plausible_birth_date(parsed) {
                            return Some(parsed);
                        }
                    }
                }
            }
        }
    }

    None
}

/// Strategy 2: Find birth date by scanning document context around date entities
fn find_birth_date_by_context(
    entities: &[PIIEntity],
    document_text: &str,
) -> Option<(NaiveDate, usize)> {
    if document_text.is_empty() {
        return None;
    }

    let text_lower = document_text.to_lowercase();

    for (idx, e) in entities.iter().enumerate() {
        if e.category != "date" {
            continue;
        }
        let orig_lower = e.original.to_lowercase();
        if let Some(pos) = text_lower.find(&orig_lower) {
            // Check 120 chars BEFORE
            let context_start = pos.saturating_sub(120);
            let context_before = &text_lower[context_start..pos];
            for pattern in BIRTH_CONTEXT_BEFORE {
                if context_before.contains(pattern) {
                    if let Some(parsed) = parse_date(&e.original) {
                        return Some((parsed, idx));
                    }
                }
            }

            // Check 40 chars AFTER
            let after_start = pos + orig_lower.len();
            let after_end = (after_start + 40).min(text_lower.len());
            let context_after = &text_lower[after_start..after_end];
            for pattern in BIRTH_CONTEXT_AFTER {
                if context_after.contains(pattern) {
                    if let Some(parsed) = parse_date(&e.original) {
                        return Some((parsed, idx));
                    }
                }
            }
        }
    }

    None
}

/// Detect the birth date from entities and document text using a multi-strategy cascade.
/// Returns (birth_date, entity_index) if found.
pub fn detect_birth_date(
    entities: &[PIIEntity],
    document_text: &str,
) -> Option<(NaiveDate, usize)> {
    // Strategy 0: Regex scan of entire document text
    if let Some(regex_birth) = find_birth_date_by_regex_scan(document_text) {
        for (idx, e) in entities.iter().enumerate() {
            if e.category != "date" {
                continue;
            }
            if let Some(parsed) = parse_date(&e.original) {
                if parsed == regex_birth {
                    return Some((regex_birth, idx));
                }
            }
        }
    }

    // Strategy 1: Find by subcategory (LLM classified as date_of_birth)
    for (idx, e) in entities.iter().enumerate() {
        if let Some(ref sub) = e.subcategory {
            let sub_lower = sub.to_lowercase();
            if BIRTH_DATE_SUBCATS.iter().any(|s| *s == sub_lower) {
                if let Some(parsed) = parse_date(&e.original) {
                    return Some((parsed, idx));
                }
            }
        }
    }

    // Strategy 2: Find by document context
    if let Some((parsed, idx)) = find_birth_date_by_context(entities, document_text) {
        return Some((parsed, idx));
    }

    // Strategy 3: Earliest date heuristic (when 2+ dates exist)
    let mut date_candidates: Vec<(NaiveDate, usize)> = Vec::new();
    for (idx, e) in entities.iter().enumerate() {
        if e.category != "date" {
            continue;
        }
        if let Some(parsed) = parse_date(&e.original) {
            date_candidates.push((parsed, idx));
        }
    }
    if date_candidates.len() >= 2 {
        date_candidates.sort_by_key(|(d, _)| *d);
        return Some(date_candidates[0]);
    }

    None
}

/// Apply age conversion to date entities.
/// If `override_birth` is Some, uses that date instead of auto-detecting.
pub fn apply_age_conversion(
    entities: &mut Vec<PIIEntity>,
    document_text: &str,
    language: &str,
) -> Option<String> {
    apply_age_conversion_with_birth(entities, document_text, language, None)
}

/// Apply age conversion with an optional user-specified birth date override.
/// Returns the birth date used (as DD.MM.YYYY string) if age conversion was applied.
pub fn apply_age_conversion_with_birth(
    entities: &mut Vec<PIIEntity>,
    document_text: &str,
    language: &str,
    override_birth: Option<&str>,
) -> Option<String> {
    let (birth, birth_idx) = if let Some(date_str) = override_birth {
        // User-specified birth date
        let parsed = parse_date(date_str)?;
        // Find matching entity index if any
        let idx = entities.iter().position(|e| {
            e.category == "date" && parse_date(&e.original) == Some(parsed)
        });
        (parsed, idx)
    } else {
        // Auto-detect
        let (d, i) = detect_birth_date(entities, document_text)?;
        (d, Some(i))
    };

    let birth_str = birth.format("%d.%m.%Y").to_string();

    // Convert other dates to age-relative placeholders
    for (idx, entity) in entities.iter_mut().enumerate() {
        if entity.category != "date" || Some(idx) == birth_idx {
            continue;
        }
        if let Some(parsed) = parse_date(&entity.original) {
            let (years, months) = calc_age_diff(birth, parsed);
            if language == "tr" {
                if years == 0 && months == 0 {
                    entity.placeholder = "doğduğu gün".to_string();
                } else if months == 0 {
                    entity.placeholder = format!("{} yaşında", years);
                } else {
                    entity.placeholder = format!("{} yıl {} ay", years, months);
                }
            } else if years == 0 && months == 0 {
                entity.placeholder = "at birth".to_string();
            } else if months == 0 {
                entity.placeholder = format!("age {}", years);
            } else {
                entity.placeholder = format!("age {} yr {} mo", years, months);
            }
        }
    }

    Some(birth_str)
}
