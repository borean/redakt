use futures_util::StreamExt;
use serde::Serialize;
use std::path::PathBuf;
use tauri::{AppHandle, Emitter};

const QWEN_MODEL_NAME: &str = "Qwen3.5-35B-A3B-Q4_K_M.gguf";
const QWEN_DOWNLOAD_URL: &str = "https://huggingface.co/unsloth/Qwen3.5-35B-A3B-GGUF/resolve/main/Qwen3.5-35B-A3B-Q4_K_M.gguf";
const QWEN_EXPECTED_SIZE: u64 = 22_016_023_168; // Exact file size from HuggingFace

#[derive(Clone, Serialize)]
pub struct DownloadProgress {
    pub downloaded: u64,
    pub total: u64,
    pub percent: f64,
    pub speed_mbps: f64,
    pub eta_secs: u64,
}

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

/// Path where the default Qwen model will be stored
pub fn get_default_model_path() -> PathBuf {
    get_model_dir().join(QWEN_MODEL_NAME)
}

/// Check if the default Qwen model already exists and has correct file size
pub fn model_exists() -> bool {
    let path = get_default_model_path();
    if !path.exists() {
        return false;
    }
    // Validate exact file size (catches corrupted resume downloads)
    if let Ok(meta) = std::fs::metadata(&path) {
        let size = meta.len();
        if size != QWEN_EXPECTED_SIZE {
            // File is corrupted — delete it so it gets re-downloaded
            eprintln!(
                "Model file size mismatch: expected {} bytes, got {} bytes. Deleting corrupt file.",
                QWEN_EXPECTED_SIZE, size
            );
            let _ = std::fs::remove_file(&path);
            return false;
        }
    }
    true
}

/// Download the Qwen 3.5 GGUF model with resume support and progress events
pub async fn download_model(app: AppHandle) -> Result<String, String> {
    let model_dir = get_model_dir();
    std::fs::create_dir_all(&model_dir)
        .map_err(|e| format!("Failed to create model directory: {}", e))?;

    let model_path = model_dir.join(QWEN_MODEL_NAME);
    let partial_path = model_dir.join(format!("{}.partial", QWEN_MODEL_NAME));

    // Already downloaded — return immediately
    if model_path.exists() {
        let _ = app.emit(
            "download-progress",
            DownloadProgress {
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
        .user_agent("Redakt/0.1")
        .build()
        .map_err(|e| format!("HTTP client error: {}", e))?;

    // Build request — with Range header for resume
    let mut req = client.get(QWEN_DOWNLOAD_URL);
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
        // Server accepted our Range request — append remaining bytes
        (content_length + existing_size, true)
    } else {
        // Server sent full file (200) — must start fresh, NOT append
        if existing_size > 0 {
            // Delete the partial to avoid appending to stale data
            let _ = std::fs::remove_file(&partial_path);
        }
        (content_length, false)
    };

    // Open file — append only if resuming, otherwise create fresh
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

        // Emit progress at most every 250ms (avoids flooding)
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
            downloaded: total_size,
            total: total_size,
            percent: 100.0,
            speed_mbps: 0.0,
            eta_secs: 0,
        },
    );

    Ok(model_path.to_string_lossy().to_string())
}
