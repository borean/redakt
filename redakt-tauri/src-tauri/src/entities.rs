use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PIIEntity {
    pub original: String,
    pub category: String,
    pub subcategory: Option<String>,
    pub placeholder: String,
    pub confidence: f64,
    pub enabled: bool,
    pub start: Option<usize>,
    pub end: Option<usize>,
    #[serde(default)]
    pub manual: Option<bool>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScanResult {
    pub entities: Vec<PIIEntity>,
    pub original_text: String,
    pub highlighted_html: String,
    pub redacted_html: String,
    pub summary: String,
    pub detected_birth_date: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppSettings {
    pub language: String,
    pub theme: String,
    pub selected_model: String,
    pub gguf_path: Option<String>,
    pub llama_server_path: Option<String>,
    pub age_conversion: bool,
    pub birth_date: Option<String>,
}

impl Default for AppSettings {
    fn default() -> Self {
        Self {
            language: "en".to_string(),
            theme: "dark".to_string(),
            selected_model: "4b".to_string(),
            gguf_path: None,
            llama_server_path: None,
            age_conversion: false,
            birth_date: None,
        }
    }
}

/// A model available in the catalog, with download status
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelCatalogEntry {
    pub id: String,
    pub name: String,
    pub size_gb: f64,
    pub downloaded: bool,
    pub active: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LlmStatus {
    pub running: bool,
    pub model_name: Option<String>,
    pub model_path: Option<String>,
}

/// The 8 canonical PII categories
pub const CATEGORIES: &[&str] = &[
    "name", "date", "id", "address", "phone", "email", "institution", "age",
];

/// Map LLM free-form categories to canonical types
pub fn normalize_category(raw: &str) -> &'static str {
    let lower = raw.to_lowercase();
    let lower = lower.trim();

    // Name variants
    if lower.contains("name") || lower.contains("ad") || lower.contains("soyad")
        || lower == "doctor" || lower == "doktor" || lower == "patient" || lower == "hasta"
    {
        return "name";
    }

    // Date variants
    if lower.contains("date") || lower.contains("tarih") || lower.contains("birth")
        || lower.contains("doğum") || lower.contains("visit") || lower.contains("muayene")
    {
        return "date";
    }

    // ID variants
    if lower.contains("id") || lower.contains("kimlik") || lower.contains("tc")
        || lower.contains("ssn") || lower.contains("protocol") || lower.contains("protokol")
    {
        return "id";
    }

    // Address variants
    if lower.contains("address") || lower.contains("adres") || lower.contains("location")
        || lower.contains("konum") || lower.contains("city") || lower.contains("şehir")
    {
        return "address";
    }

    // Phone variants
    if lower.contains("phone") || lower.contains("telefon") || lower.contains("tel")
        || lower.contains("mobile") || lower.contains("cep")
    {
        return "phone";
    }

    // Email variants
    if lower.contains("email") || lower.contains("e-posta") || lower.contains("mail") {
        return "email";
    }

    // Institution variants
    if lower.contains("institution") || lower.contains("hospital") || lower.contains("hastane")
        || lower.contains("university") || lower.contains("üniversite") || lower.contains("kurum")
        || lower.contains("clinic") || lower.contains("klinik")
        || lower == "organization" || lower == "org" || lower.contains("school")
        || lower.contains("pharmacy") || lower.contains("eczane")
    {
        return "institution";
    }

    // Age variants
    if lower.contains("age") || lower.contains("yaş") {
        return "age";
    }

    // If nothing matched, try to find partial overlaps
    for cat in CATEGORIES {
        if lower == *cat {
            return cat;
        }
    }

    "name" // fallback
}
