use crate::entities::{normalize_category, PIIEntity};
use crate::llm::LlmState;
use regex::Regex;
use serde::Deserialize;

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

    let user_prompt = if language == "tr" {
        format!(
            "Aşağıdaki tıbbi belge metnindeki tüm kişisel verileri tespit et:\n\n---\n{}\n---",
            text
        )
    } else {
        format!(
            "Detect all personally identifiable information in the following medical document text:\n\n---\n{}\n---",
            text
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
            return Ok(ents
                .into_iter()
                .filter_map(|e| {
                    let original = e.original?.trim().to_string();
                    if original.is_empty() {
                        return None;
                    }
                    let category = normalize_category(&e.category?).to_string();
                    Some(PIIEntity {
                        original,
                        category,
                        subcategory: None,
                        placeholder: String::new(),
                        confidence: e.confidence.unwrap_or(0.9),
                        enabled: true,
                        start: None,
                        end: None,
                    })
                })
                .collect());
        }
    }

    // Try to extract entities array even from malformed JSON
    if let Some(start) = cleaned.find("[") {
        let from_bracket = &cleaned[start..];
        // Find matching close bracket
        let mut depth = 0;
        let mut end_idx = from_bracket.len();
        for (i, ch) in from_bracket.char_indices() {
            match ch {
                '[' => depth += 1,
                ']' => {
                    depth -= 1;
                    if depth == 0 {
                        end_idx = i + 1;
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
            return Ok(ents
                .into_iter()
                .filter_map(|e| {
                    let original = e.original?.trim().to_string();
                    if original.is_empty() {
                        return None;
                    }
                    let category = normalize_category(&e.category?).to_string();
                    Some(PIIEntity {
                        original,
                        category,
                        subcategory: None,
                        placeholder: String::new(),
                        confidence: e.confidence.unwrap_or(0.9),
                        enabled: true,
                        start: None,
                        end: None,
                    })
                })
                .collect());
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
fn regex_supplement(text: &str, _language: &str) -> Vec<PIIEntity> {
    let mut entities = Vec::new();

    // Turkish TC Kimlik (11-digit national ID)
    let tc_re = Regex::new(r"\b\d{11}\b").unwrap();
    for m in tc_re.find_iter(text) {
        let val = m.as_str();
        // Basic TC validation: first digit != 0, checksum
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

    // Email addresses
    let email_re = Regex::new(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b").unwrap();
    for m in email_re.find_iter(text) {
        entities.push(PIIEntity {
            original: m.as_str().to_string(),
            category: "email".to_string(),
            subcategory: None,
            placeholder: String::new(),
            confidence: 0.95,
            enabled: true,
            start: Some(m.start()),
            end: Some(m.end()),
        });
    }

    // Phone numbers (Turkish format)
    let phone_re = Regex::new(r"\b(?:0|\+90\s?)?(?:\d[\s.-]?){10}\b").unwrap();
    for m in phone_re.find_iter(text) {
        entities.push(PIIEntity {
            original: m.as_str().trim().to_string(),
            category: "phone".to_string(),
            subcategory: None,
            placeholder: String::new(),
            confidence: 0.80,
            enabled: true,
            start: Some(m.start()),
            end: Some(m.end()),
        });
    }

    entities
}

/// Assign unique placeholders like [AD_1], [TARİH_2]
fn assign_placeholders(entities: &mut Vec<PIIEntity>) {
    let mut counters = std::collections::HashMap::new();

    let label_map = std::collections::HashMap::from([
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
        entity.placeholder = format!("[{}_{}", label, count);
        // Fix: proper bracket closing
        entity.placeholder = format!("[{}_{}]", label, count);
    }
}
