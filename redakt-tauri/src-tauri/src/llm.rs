use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use tokio::time::{sleep, Duration};

pub struct LlmState {
    pub server_process: Mutex<Option<Child>>,
    pub model_path: Mutex<Option<PathBuf>>,
    pub server_path: Mutex<Option<PathBuf>>,
    pub healthy: Mutex<bool>,
}

impl Default for LlmState {
    fn default() -> Self {
        Self {
            server_process: Mutex::new(None),
            model_path: Mutex::new(None),
            server_path: Mutex::new(None),
            healthy: Mutex::new(false),
        }
    }
}

#[derive(Debug, Serialize, Deserialize)]
pub struct GGUFInfo {
    pub path: String,
    pub name: String,
    pub size_gb: f64,
    pub quantization: String,
}

const API_BASE: &str = "http://localhost:8081";

impl LlmState {
    /// Find all GGUF model files in common locations
    pub fn find_models() -> Vec<GGUFInfo> {
        let mut models = Vec::new();
        let search_dirs = get_model_search_dirs();

        for dir in search_dirs {
            if !dir.exists() {
                continue;
            }
            if let Ok(entries) = std::fs::read_dir(&dir) {
                for entry in entries.flatten() {
                    let path = entry.path();
                    if path.extension().map_or(false, |e| e == "gguf") {
                        let name = path.file_stem()
                            .unwrap_or_default()
                            .to_string_lossy()
                            .to_string();
                        let size = std::fs::metadata(&path)
                            .map(|m| m.len() as f64 / 1_073_741_824.0)
                            .unwrap_or(0.0);
                        let quant = detect_quantization(&name, size);
                        models.push(GGUFInfo {
                            path: path.to_string_lossy().to_string(),
                            name,
                            size_gb: (size * 100.0).round() / 100.0,
                            quantization: quant,
                        });
                    }
                }
            }
        }

        // Sort: Qwen models first, then by size descending
        models.sort_by(|a, b| {
            let a_qwen = a.name.to_lowercase().contains("qwen");
            let b_qwen = b.name.to_lowercase().contains("qwen");
            match (a_qwen, b_qwen) {
                (true, false) => std::cmp::Ordering::Less,
                (false, true) => std::cmp::Ordering::Greater,
                _ => b.size_gb.partial_cmp(&a.size_gb).unwrap_or(std::cmp::Ordering::Equal),
            }
        });
        models
    }

    /// Find llama-server binary
    pub fn find_server() -> Option<PathBuf> {
        let candidates = [
            // Homebrew (macOS ARM)
            "/opt/homebrew/bin/llama-server",
            // Homebrew (macOS Intel)
            "/usr/local/bin/llama-server",
            // Snap (Linux)
            "/snap/bin/llama-server",
            // Common PATH locations
            "/usr/bin/llama-server",
        ];

        // Check PATH first
        if let Ok(output) = Command::new("which").arg("llama-server").output() {
            if output.status.success() {
                let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
                if !path.is_empty() {
                    return Some(PathBuf::from(path));
                }
            }
        }

        for candidate in &candidates {
            let path = PathBuf::from(candidate);
            if path.exists() {
                return Some(path);
            }
        }

        None
    }

    /// Start the llama-server process
    pub fn start_server(&self, model_path: &str, server_path: Option<&str>) -> Result<(), String> {
        // Kill existing server if any
        self.stop_server();

        let server_bin = if let Some(p) = server_path {
            PathBuf::from(p)
        } else {
            Self::find_server().ok_or("llama-server not found. Install via: brew install llama.cpp")?
        };

        let model = PathBuf::from(model_path);
        if !model.exists() {
            return Err(format!("Model file not found: {}", model_path));
        }

        // Match Python version's proven server parameters exactly
        let child = Command::new(&server_bin)
            .arg("-m")
            .arg(&model)
            .arg("-ngl")
            .arg("99") // Offload all layers to GPU
            .arg("-c")
            .arg("32768") // 32K context window
            .arg("--port")
            .arg("8081")
            .arg("-fa")
            .arg("on") // Flash attention
            .arg("--reasoning-budget")
            .arg("0") // Disable thinking/reasoning (Qwen 3.5)
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .map_err(|e| format!("Failed to start llama-server: {}", e))?;

        *self.server_process.lock().unwrap() = Some(child);
        *self.model_path.lock().unwrap() = Some(model);
        *self.server_path.lock().unwrap() = Some(server_bin);

        Ok(())
    }

    /// Stop the llama-server process
    pub fn stop_server(&self) {
        if let Some(mut child) = self.server_process.lock().unwrap().take() {
            let _ = child.kill();
            let _ = child.wait();
        }
        *self.healthy.lock().unwrap() = false;
    }

    /// Check if the server is healthy
    pub async fn check_health(&self) -> bool {
        let client = reqwest::Client::new();
        match client
            .get(format!("{}/health", API_BASE))
            .timeout(Duration::from_secs(2))
            .send()
            .await
        {
            Ok(resp) => {
                let ok = resp.status().is_success();
                *self.healthy.lock().unwrap() = ok;
                ok
            }
            Err(_) => {
                *self.healthy.lock().unwrap() = false;
                false
            }
        }
    }

    /// Wait for the server to become healthy (with timeout)
    pub async fn wait_for_ready(&self, timeout_secs: u64) -> bool {
        let deadline = tokio::time::Instant::now() + Duration::from_secs(timeout_secs);
        while tokio::time::Instant::now() < deadline {
            if self.check_health().await {
                return true;
            }
            sleep(Duration::from_millis(500)).await;
        }
        false
    }

    /// Send a chat completion request to the LLM
    pub async fn chat_completion(
        &self,
        system_prompt: &str,
        user_prompt: &str,
    ) -> Result<String, String> {
        if !*self.healthy.lock().unwrap() {
            return Err("LLM server is not ready".to_string());
        }

        let client = reqwest::Client::new();
        let body = serde_json::json!({
            "model": "qwen",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 4096,
            "response_format": {"type": "json_object"}
        });

        let resp = client
            .post(format!("{}/v1/chat/completions", API_BASE))
            .json(&body)
            .timeout(Duration::from_secs(300))
            .send()
            .await
            .map_err(|e| format!("LLM request failed: {}", e))?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body_text = resp.text().await.unwrap_or_default();
            eprintln!("LLM error {}: {}", status, body_text);

            // If 400, try again without response_format (some models/versions don't support it)
            if status == reqwest::StatusCode::BAD_REQUEST {
                let fallback_body = serde_json::json!({
                    "model": "qwen",
                    "messages": [
                        {"role": "system", "content": format!("{}\n\nYou MUST respond with valid JSON only. No markdown, no extra text.", system_prompt)},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 4096
                });

                let resp2 = client
                    .post(format!("{}/v1/chat/completions", API_BASE))
                    .json(&fallback_body)
                    .timeout(Duration::from_secs(300))
                    .send()
                    .await
                    .map_err(|e| format!("LLM fallback request failed: {}", e))?;

                if !resp2.status().is_success() {
                    let s2 = resp2.status();
                    let b2 = resp2.text().await.unwrap_or_default();
                    return Err(format!("LLM returned status {} — {}", s2, b2));
                }

                let json: serde_json::Value = resp2
                    .json()
                    .await
                    .map_err(|e| format!("Failed to parse LLM response: {}", e))?;

                let content = json["choices"][0]["message"]["content"]
                    .as_str()
                    .unwrap_or("");

                if !content.is_empty() {
                    return Ok(content.to_string());
                }

                return Err("Empty content in LLM fallback response".to_string());
            }

            return Err(format!("LLM returned status {} — {}", status, body_text));
        }

        let json: serde_json::Value = resp
            .json()
            .await
            .map_err(|e| format!("Failed to parse LLM response: {}", e))?;

        // Try content field first, then check for reasoning_content + content
        let content = json["choices"][0]["message"]["content"]
            .as_str()
            .unwrap_or("");

        if !content.is_empty() {
            return Ok(content.to_string());
        }

        // Some llama.cpp versions put thinking in reasoning_content
        // and the actual response in content (which may be empty if still thinking)
        Err(format!(
            "Empty content in LLM response. Full response: {}",
            serde_json::to_string_pretty(&json).unwrap_or_default()
        ))
    }

    pub fn is_running(&self) -> bool {
        self.server_process.lock().unwrap().is_some()
    }
}

fn get_model_search_dirs() -> Vec<PathBuf> {
    let mut dirs = Vec::new();

    if let Some(home) = dirs::home_dir() {
        // Dedicated model directories
        dirs.push(home.join(".redakt").join("models"));
        dirs.push(home.join("models"));

        // LM Studio models (very common)
        dirs.push(home.join(".lmstudio").join("models"));
        // Recurse into LM Studio subdirs
        let lmstudio = home.join(".lmstudio").join("models");
        if lmstudio.exists() {
            if let Ok(entries) = std::fs::read_dir(&lmstudio) {
                for entry in entries.flatten() {
                    let path = entry.path();
                    if path.is_dir() {
                        dirs.push(path);
                    }
                }
            }
        }

        // Ollama models
        dirs.push(home.join(".ollama").join("models"));

        // macOS Application Support
        #[cfg(target_os = "macos")]
        {
            dirs.push(home.join("Library/Application Support/Redakt/models"));
            dirs.push(home.join("Library/Application Support/LM Studio/models"));
        }

        // Linux/Windows config
        #[cfg(not(target_os = "macos"))]
        if let Some(config) = dirs::config_dir() {
            dirs.push(config.join("Redakt").join("models"));
        }
    }

    dirs
}

fn detect_quantization(name: &str, size_gb: f64) -> String {
    let upper = name.to_uppercase();
    let quant_types = [
        "Q2_K", "Q3_K_S", "Q3_K_M", "Q3_K_L",
        "Q4_0", "Q4_1", "Q4_K_S", "Q4_K_M",
        "Q5_0", "Q5_1", "Q5_K_S", "Q5_K_M",
        "Q6_K", "Q8_0", "F16", "F32",
    ];

    for q in &quant_types {
        if upper.contains(q) {
            return q.to_string();
        }
    }

    // Infer from size
    if size_gb < 3.0 {
        "Q4_0".to_string()
    } else if size_gb < 5.0 {
        "Q4_K_M".to_string()
    } else if size_gb < 8.0 {
        "Q5_K_M".to_string()
    } else if size_gb < 12.0 {
        "Q6_K".to_string()
    } else {
        "Q8_0".to_string()
    }
}
