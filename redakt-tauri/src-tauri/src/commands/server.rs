use std::sync::Mutex;
use std::process::{Command, Child};
use tauri::State;

pub struct SidecarState {
    pub process: Mutex<Option<Child>>,
}

impl Default for SidecarState {
    fn default() -> Self {
        Self {
            process: Mutex::new(None),
        }
    }
}

#[tauri::command]
pub fn start_llama_server(
    state: State<'_, SidecarState>,
    binary_path: String,
    model_path: String,
    port: u16,
) -> Result<(), String> {
    let mut guard = state.process.lock().map_err(|e| e.to_string())?;

    // Kill existing process if any
    if let Some(mut proc) = guard.take() {
        let _ = proc.kill();
        let _ = proc.wait();
    }

    let child = Command::new(&binary_path)
        .args([
            "-m", &model_path,
            "-ngl", "99",
            "-c", "8192",
            "--port", &port.to_string(),
            "-fa", "on",
            "--reasoning-budget", "0",
        ])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .map_err(|e| format!("Failed to start llama-server: {e}"))?;

    *guard = Some(child);
    Ok(())
}

#[tauri::command]
pub fn stop_llama_server(state: State<'_, SidecarState>) -> Result<(), String> {
    let mut guard = state.process.lock().map_err(|e| e.to_string())?;
    if let Some(mut proc) = guard.take() {
        let _ = proc.kill();
        let _ = proc.wait();
    }
    Ok(())
}

#[tauri::command]
pub async fn check_server_health(host: String) -> bool {
    let url = format!("{host}/health");
    match reqwest::Client::new()
        .get(&url)
        .timeout(std::time::Duration::from_secs(3))
        .send()
        .await
    {
        Ok(resp) => {
            if resp.status().is_success() {
                if let Ok(json) = resp.json::<serde_json::Value>().await {
                    return json.get("status").and_then(|s| s.as_str()) == Some("ok");
                }
            }
            false
        }
        Err(_) => false,
    }
}

#[tauri::command]
pub fn find_llama_server_binary() -> Option<String> {
    // 1. Check PATH
    if let Ok(output) = Command::new("which").arg("llama-server").output() {
        if output.status.success() {
            let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if !path.is_empty() {
                return Some(path);
            }
        }
    }

    // 2. Homebrew (Apple Silicon)
    let brew_arm = "/opt/homebrew/bin/llama-server";
    if std::path::Path::new(brew_arm).exists() {
        return Some(brew_arm.to_string());
    }

    // 3. Homebrew (Intel Mac)
    let brew_intel = "/usr/local/bin/llama-server";
    if std::path::Path::new(brew_intel).exists() {
        return Some(brew_intel.to_string());
    }

    // 4. Common Linux paths
    for dir in &["/usr/bin", "/usr/local/bin", "/snap/bin"] {
        let p = format!("{dir}/llama-server");
        if std::path::Path::new(&p).exists() {
            return Some(p);
        }
    }

    None
}
