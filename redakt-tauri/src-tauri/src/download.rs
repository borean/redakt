use futures_util::StreamExt;
use serde::Serialize;
use std::path::PathBuf;
use tauri::{AppHandle, Emitter};

// ── Model Catalog ──────────────────────────────────────────────

pub struct ModelDef {
    pub id: &'static str,
    pub name: &'static str,
    pub filename: &'static str,
    pub url: &'static str,
    pub size_gb: f64,
}

pub const MODEL_CATALOG: &[ModelDef] = &[
    ModelDef {
        id: "9b",
        name: "Qwen 3.5 9B",
        filename: "Qwen_Qwen3.5-9B-Q4_K_M.gguf",
        url: "https://huggingface.co/bartowski/Qwen_Qwen3.5-9B-GGUF/resolve/main/Qwen_Qwen3.5-9B-Q4_K_M.gguf",
        size_gb: 5.87,
    },
    ModelDef {
        id: "27b",
        name: "Qwen 3.5 27B",
        filename: "Qwen_Qwen3.5-27B-Q4_K_M.gguf",
        url: "https://huggingface.co/bartowski/Qwen_Qwen3.5-27B-GGUF/resolve/main/Qwen_Qwen3.5-27B-Q4_K_M.gguf",
        size_gb: 17.13,
    },
    ModelDef {
        id: "35b-a3b",
        name: "Qwen 3.5 35B-A3B",
        filename: "Qwen3.5-35B-A3B-Q4_K_M.gguf",
        url: "https://huggingface.co/unsloth/Qwen3.5-35B-A3B-GGUF/resolve/main/Qwen3.5-35B-A3B-Q4_K_M.gguf",
        size_gb: 21.0,
    },
];

pub const DEFAULT_MODEL_ID: &str = "9b";

/// Find a model definition by its ID
pub fn find_model(id: &str) -> Option<&'static ModelDef> {
    MODEL_CATALOG.iter().find(|m| m.id == id)
}

// ── Download Progress ──────────────────────────────────────────

#[derive(Clone, Serialize)]
pub struct DownloadProgress {
    pub model_id: String,
    pub downloaded: u64,
    pub total: u64,
    pub percent: f64,
    pub speed_mbps: f64,
    pub eta_secs: u64,
}

// ── Model Directory ────────────────────────────────────────────

/// Get the Redakt model storage directory
pub fn get_model_dir() -> PathBuf {
    if let Some(home) = dirs::home_dir() {
        #[cfg(target_os = "macos")]
        {
            return home.join("Library/Application Support/Redakt/models");
        }
        #[cfg(not(target_os = "macos"))]
        {
            return dirs::config_dir()
                .unwrap_or_else(|| home.join(".config"))
                .join("Redakt")
                .join("models");
        }
    }
    PathBuf::from("models")
}

/// Get the settings file path
pub fn get_settings_path() -> PathBuf {
    if let Some(home) = dirs::home_dir() {
        #[cfg(target_os = "macos")]
        {
            return home.join("Library/Application Support/Redakt/settings.json");
        }
        #[cfg(not(target_os = "macos"))]
        {
            return dirs::config_dir()
                .unwrap_or_else(|| home.join(".config"))
                .join("Redakt")
                .join("settings.json");
        }
    }
    PathBuf::from("settings.json")
}

/// Path where a specific model will be stored
pub fn get_model_path(model_id: &str) -> Option<PathBuf> {
    find_model(model_id).map(|m| get_model_dir().join(m.filename))
}

/// Check if a specific model is already downloaded
pub fn is_model_downloaded(model_id: &str) -> bool {
    if let Some(path) = get_model_path(model_id) {
        path.exists() && std::fs::metadata(&path).map(|m| m.len() > 1_000_000).unwrap_or(false)
    } else {
        false
    }
}

/// Check if the default model needs to be downloaded (backward compat)
pub fn model_exists() -> bool {
    // Check if ANY model from the catalog is downloaded
    MODEL_CATALOG.iter().any(|m| {
        let path = get_model_dir().join(m.filename);
        path.exists() && std::fs::metadata(&path).map(|meta| meta.len() > 1_000_000).unwrap_or(false)
    })
}

/// Get the default model path (for backward compat)
pub fn get_default_model_path() -> PathBuf {
    get_model_path(DEFAULT_MODEL_ID).unwrap_or_else(|| get_model_dir().join("model.gguf"))
}

// ── Download ───────────────────────────────────────────────────

/// Download a model by its catalog ID with resume support and progress events
pub async fn download_model_by_id(app: AppHandle, model_id: &str) -> Result<String, String> {
    let model_def = find_model(model_id)
        .ok_or_else(|| format!("Unknown model: {}", model_id))?;

    let model_dir = get_model_dir();
    std::fs::create_dir_all(&model_dir)
        .map_err(|e| format!("Failed to create model directory: {}", e))?;

    let model_path = model_dir.join(model_def.filename);
    let partial_path = model_dir.join(format!("{}.partial", model_def.filename));

    // Already downloaded — return immediately
    if model_path.exists() && std::fs::metadata(&model_path).map(|m| m.len() > 1_000_000).unwrap_or(false) {
        let _ = app.emit(
            "download-progress",
            DownloadProgress {
                model_id: model_id.to_string(),
                downloaded: 1,
                total: 1,
                percent: 100.0,
                speed_mbps: 0.0,
                eta_secs: 0,
            },
        );
        return Ok(model_path.to_string_lossy().to_string());
    }

    // Check for partial download (resume support)
    let existing_size = if partial_path.exists() {
        std::fs::metadata(&partial_path)
            .map(|m| m.len())
            .unwrap_or(0)
    } else {
        0
    };

    let client = reqwest::Client::builder()
        .user_agent("Redakt/0.3.1")
        .build()
        .map_err(|e| format!("HTTP client error: {}", e))?;

    // Build request — with Range header for resume
    let mut req = client.get(model_def.url);
    if existing_size > 0 {
        req = req.header("Range", format!("bytes={}-", existing_size));
    }

    let resp = req
        .send()
        .await
        .map_err(|e| format!("Download request failed: {}", e))?;

    // Validate response
    let status = resp.status();
    if !status.is_success() && status.as_u16() != 206 {
        return Err(format!("Download failed with HTTP {}", status));
    }

    let content_length = resp.content_length().unwrap_or(0);
    let (total_size, resume) = if existing_size > 0 && status.as_u16() == 206 {
        (content_length + existing_size, true)
    } else {
        if existing_size > 0 {
            let _ = std::fs::remove_file(&partial_path);
        }
        (content_length, false)
    };

    // Open file — append only if resuming
    use std::io::Write;
    let mut file = if resume {
        std::fs::OpenOptions::new()
            .append(true)
            .open(&partial_path)
            .map_err(|e| format!("Failed to open file for append: {}", e))?
    } else {
        std::fs::OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(true)
            .open(&partial_path)
            .map_err(|e| format!("Failed to create download file: {}", e))?
    };

    let mut downloaded = if resume { existing_size } else { 0 };
    let start_time = std::time::Instant::now();
    let mut last_emit = std::time::Instant::now();

    let mut stream = resp.bytes_stream();

    while let Some(chunk_result) = stream.next().await {
        let chunk = chunk_result.map_err(|e| format!("Download stream error: {}", e))?;
        file.write_all(&chunk)
            .map_err(|e| format!("File write error: {}", e))?;
        downloaded += chunk.len() as u64;

        // Emit progress at most every 250ms
        if last_emit.elapsed().as_millis() >= 250 {
            let elapsed = start_time.elapsed().as_secs_f64();
            let new_bytes = (downloaded - existing_size) as f64;
            let speed_bytes = if elapsed > 0.0 {
                new_bytes / elapsed
            } else {
                0.0
            };
            let speed_mbps = speed_bytes / 1_048_576.0;

            let remaining = if speed_bytes > 0.0 && total_size > downloaded {
                ((total_size - downloaded) as f64 / speed_bytes) as u64
            } else {
                0
            };

            let progress = DownloadProgress {
                model_id: model_id.to_string(),
                downloaded,
                total: total_size,
                percent: if total_size > 0 {
                    (downloaded as f64 / total_size as f64 * 100.0).min(100.0)
                } else {
                    0.0
                },
                speed_mbps: (speed_mbps * 100.0).round() / 100.0,
                eta_secs: remaining,
            };

            let _ = app.emit("download-progress", &progress);
            last_emit = std::time::Instant::now();
        }
    }

    // Flush and close
    file.flush()
        .map_err(|e| format!("File flush error: {}", e))?;
    drop(file);

    // Rename .partial → final
    std::fs::rename(&partial_path, &model_path)
        .map_err(|e| format!("Failed to finalize download: {}", e))?;

    // Final progress event
    let _ = app.emit(
        "download-progress",
        DownloadProgress {
            model_id: model_id.to_string(),
            downloaded: total_size,
            total: total_size,
            percent: 100.0,
            speed_mbps: 0.0,
            eta_secs: 0,
        },
    );

    Ok(model_path.to_string_lossy().to_string())
}

/// Backward-compat wrapper: download the default model
pub async fn download_model(app: AppHandle) -> Result<String, String> {
    download_model_by_id(app, DEFAULT_MODEL_ID).await
}
