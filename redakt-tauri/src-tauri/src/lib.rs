mod commands;
mod parsers;
mod types;

use commands::server::SidecarState;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .manage(SidecarState::default())
        .invoke_handler(tauri::generate_handler![
            commands::dialog::open_file_dialog,
            commands::dialog::save_file_dialog,
            commands::document::read_document,
            commands::server::start_llama_server,
            commands::server::stop_llama_server,
            commands::server::check_server_health,
            commands::server::find_llama_server_binary,
            commands::model::find_gguf_models,
            commands::model::get_data_dir,
            commands::model::download_model,
            commands::export::export_redacted,
            commands::sysinfo::get_system_info,
        ])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.try_state::<SidecarState>() {
                    if let Ok(mut guard) = state.process.lock() {
                        if let Some(mut proc) = guard.take() {
                            let _ = proc.kill();
                            let _ = proc.wait();
                        }
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
