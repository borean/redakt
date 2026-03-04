use crate::types::{DownloadProgress, GGUFModel};
use std::path::{Path, PathBuf};
use tauri::{Emitter, Window};

const KNOWN_QUANTS: &[&str] = &[
    "Q4_K_M", "Q8_0", "Q4_K_S", "Q5_K_M", "Q5_K_S", "Q6_K", "BF16", "F16",
    "Q2_K", "Q3_K_M", "Q3_K_S", "Q3_K_L", "IQ4_XS", "IQ4_NL",
];

pub fn get_data_dir_path() -> PathBuf {
    if cfg!(target_os = "macos") {
        dirs::home_dir()
            .unwrap_or_default()
            .join("Library/Application Support/Redakt/models")
    } else if cfg!(target_os = "windows") {
        dirs::data_local_dir()
            .unwrap_or_default()
            .join("Redakt/models")
    } else {
        dirs::data_dir()
            .unwrap_or_else(|| dirs::home_dir().unwrap_or_default().join(".local/share"))
            .join("redakt/models")
    }
}

#[tauri::command]
pub fn get_data_dir() -> String {
    get_data_dir_path().to_string_lossy().to_string()
}

#[tauri::command]
pub fn find_gguf_models() -> Vec<GGUFModel> {
    let mut results = Vec::new();
    let mut seen = std::collections::HashSet::new();

    let search_dirs = vec![
        get_data_dir_path(),
        dirs::home_dir().unwrap_or_default().join(".redakt/models"),
        dirs::home_dir().unwrap_or_default().join("models"),
    ];

    for dir in search_dirs {
        if !dir.exists() {
            continue;
        }
        if let Ok(entries) = std::fs::read_dir(&dir) {
            let mut gguf_files: Vec<_> = entries
                .filter_map(|e| e.ok())
                .filter(|e| {
                    e.path()
                        .extension()
                        .and_then(|ext| ext.to_str())
                        .map(|ext| ext == "gguf")
                        .unwrap_or(false)
                })
                .collect();
            // Sort by size descending
            gguf_files.sort_by(|a, b| {
                b.metadata()
                    .map(|m| m.len())
                    .unwrap_or(0)
                    .cmp(&a.metadata().map(|m| m.len()).unwrap_or(0))
            });

            for entry in gguf_files {
                let path = entry.path();
                let path_str = path.to_string_lossy().to_string();
                if seen.contains(&path_str) {
                    continue;
                }
                seen.insert(path_str.clone());

                let size_bytes = entry.metadata().map(|m| m.len()).unwrap_or(0);
                let size_gb = size_bytes as f64 / (1024.0 * 1024.0 * 1024.0);
                let stem = path
                    .file_stem()
                    .and_then(|s| s.to_str())
                    .unwrap_or("")
                    .to_string();
                let stem_upper = stem.to_uppercase();

                let mut quant = "Unknown".to_string();
                for q in KNOWN_QUANTS {
                    if stem_upper.contains(q) {
                        quant = q.to_string();
                        break;
                    }
                }
                // Infer from size if filename is opaque
                if quant == "Unknown" {
                    if (18.0..=24.0).contains(&size_gb) {
                        quant = "Q4_K_M".to_string();
                    } else if (30.0..=38.0).contains(&size_gb) {
                        quant = "Q8_0".to_string();
                    }
                }

                let name = friendly_name(&stem, size_gb, &quant);

                results.push(GGUFModel {
                    path: path_str,
                    name,
                    quant,
                    size_gb: (size_gb * 10.0).round() / 10.0,
                    source: "local".to_string(),
                });
            }
        }
    }

    results
}

fn friendly_name(stem: &str, _size_gb: f64, quant: &str) -> String {
    let is_opaque = stem.starts_with("sha256-")
        || stem.starts_with("sha512-")
        || (stem.len() > 40
            && stem
                .chars()
                .all(|c| c.is_ascii_hexdigit() || c == '-'));

    if is_opaque {
        let q = if quant != "Unknown" { quant } else { "" };
        format!("Qwen3.5 35B-A3B {q}").trim().to_string()
    } else {
        stem.to_string()
    }
}

#[tauri::command]
pub async fn download_model(window: Window, url: String, dest_dir: String) -> Result<String, String> {
    let dest_path = Path::new(&dest_dir);
    std::fs::create_dir_all(dest_path).map_err(|e| format!("Failed to create dir: {e}"))?;

    let file_name = url
        .rsplit('/')
        .next()
        .unwrap_or("model.gguf")
        .to_string();
    let final_path = dest_path.join(&file_name);
    let partial_path = dest_path.join(format!("{file_name}.partial"));

    // Check existing partial download for resume
    let existing_size = if partial_path.exists() {
        std::fs::metadata(&partial_path)
            .map(|m| m.len())
            .unwrap_or(0)
    } else {
        0
    };

    let client = reqwest::Client::new();
    let mut request = client.get(&url);
    if existing_size > 0 {
        request = request.header("Range", format!("bytes={existing_size}-"));
    }

    let response = request.send().await.map_err(|e| format!("Download failed: {e}"))?;

    let total_size = if existing_size > 0 {
        response
            .content_length()
            .map(|cl| cl + existing_size)
            .unwrap_or(0)
    } else {
        response.content_length().unwrap_or(0)
    };

    use futures_util::StreamExt;
    use std::io::Write;

    let mut file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&partial_path)
        .map_err(|e| format!("Failed to open file: {e}"))?;

    let mut downloaded = existing_size;
    let mut stream = response.bytes_stream();

    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(|e| format!("Download error: {e}"))?;
        file.write_all(&chunk).map_err(|e| format!("Write error: {e}"))?;
        downloaded += chunk.len() as u64;

        let percent = if total_size > 0 {
            (downloaded as f64 / total_size as f64) * 100.0
        } else {
            0.0
        };

        let _ = window.emit(
            "download-progress",
            DownloadProgress {
                percent,
                downloaded_mb: downloaded as f64 / (1024.0 * 1024.0),
                total_mb: total_size as f64 / (1024.0 * 1024.0),
                status: "downloading".to_string(),
            },
        );
    }

    // Rename partial to final
    std::fs::rename(&partial_path, &final_path)
        .map_err(|e| format!("Failed to finalize download: {e}"))?;

    let _ = window.emit(
        "download-progress",
        DownloadProgress {
            percent: 100.0,
            downloaded_mb: downloaded as f64 / (1024.0 * 1024.0),
            total_mb: total_size as f64 / (1024.0 * 1024.0),
            status: "complete".to_string(),
        },
    );

    Ok(final_path.to_string_lossy().to_string())
}
