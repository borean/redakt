use crate::types::SystemInfo;
use sysinfo::System;

#[tauri::command]
pub fn get_system_info() -> SystemInfo {
    let mut sys = System::new_all();
    sys.refresh_all();

    let cpu = sys
        .cpus()
        .first()
        .map(|c| c.brand().to_string())
        .unwrap_or_default();

    let ram_gb = sys.total_memory() / (1024 * 1024 * 1024);

    let arch = std::env::consts::ARCH.to_string();
    let os = std::env::consts::OS.to_string();
    let os_version = System::os_version().unwrap_or_default();

    let apple_silicon = cfg!(target_os = "macos") && arch == "aarch64";

    // On Apple Silicon, RAM is unified memory
    let unified_memory_gb = if apple_silicon { ram_gb } else { 0 };

    // GPU detection: on macOS Apple Silicon, it's the integrated GPU
    let gpu = if apple_silicon {
        format!("Apple {} GPU", cpu.replace("Apple ", ""))
    } else {
        "Unknown".to_string()
    };

    SystemInfo {
        os,
        os_version,
        arch,
        cpu,
        ram_gb,
        gpu,
        apple_silicon,
        unified_memory_gb,
    }
}
