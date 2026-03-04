mod commands;
mod download;
mod entities;
mod llm;
mod anonymizer;
mod redactor;

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .manage(llm::LlmState::default())
        .invoke_handler(tauri::generate_handler![
            commands::open_file,
            commands::scan_document,
            commands::export_document,
            commands::get_llm_status,
            commands::start_llm_server,
            commands::stop_llm_server,
            commands::get_settings,
            commands::save_settings,
            commands::toggle_entity,
            commands::list_models,
            commands::find_server,
            commands::download_model,
            commands::needs_model_download,
            commands::get_default_model_path,
            commands::get_model_catalog,
            commands::switch_model,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
