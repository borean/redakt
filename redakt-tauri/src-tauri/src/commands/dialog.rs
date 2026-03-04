use tauri_plugin_dialog::DialogExt;

#[tauri::command]
pub async fn open_file_dialog(app: tauri::AppHandle) -> Option<String> {
    let file = app
        .dialog()
        .file()
        .set_title("Open Medical Document")
        .add_filter(
            "Supported Files",
            &["pdf", "docx", "xlsx", "xls", "txt", "png", "jpg", "jpeg", "bmp", "tiff"],
        )
        .add_filter("All Files", &["*"])
        .blocking_pick_file();

    file.map(|f| f.path.to_string_lossy().to_string())
}

#[tauri::command]
pub async fn save_file_dialog(
    app: tauri::AppHandle,
    default_name: String,
    filter_name: String,
    extensions: Vec<String>,
) -> Option<String> {
    let ext_refs: Vec<&str> = extensions.iter().map(|s| s.as_str()).collect();
    let file = app
        .dialog()
        .file()
        .set_title("Export Redacted Document")
        .set_file_name(&default_name)
        .add_filter(&filter_name, &ext_refs)
        .blocking_save_file();

    file.map(|f| f.path.to_string_lossy().to_string())
}
