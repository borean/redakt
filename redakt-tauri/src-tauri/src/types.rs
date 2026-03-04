use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocumentResult {
    pub text: String,
    pub metadata: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GGUFModel {
    pub path: String,
    pub name: String,
    pub quant: String,
    pub size_gb: f64,
    pub source: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SystemInfo {
    pub os: String,
    pub os_version: String,
    pub arch: String,
    pub cpu: String,
    pub ram_gb: u64,
    pub gpu: String,
    pub apple_silicon: bool,
    pub unified_memory_gb: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExportRequest {
    pub original_path: String,
    pub redacted_text: String,
    pub format: String,
    pub output_path: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DownloadProgress {
    pub percent: f64,
    pub downloaded_mb: f64,
    pub total_mb: f64,
    pub status: String,
}
