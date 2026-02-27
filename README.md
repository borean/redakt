# DeIdentify (QwenKK)

Local medical document anonymization powered by Qwen LLM.
All processing happens on your machine -- no data leaves your computer.

**QwenKK** = Qwen + KVKK (Turkey's data protection law)

## How It Works

1. Download the app
2. Double-click to open
3. The app handles everything: installs Ollama, downloads the AI model
4. Drag your files in, click **Anonymize All**
5. Get back clean files with all patient data replaced

## Download

| Platform | Download |
|----------|----------|
| macOS | [DeIdentify.dmg](#) |
| Windows | [DeIdentify.exe](#) |
| Linux | [DeIdentify](#) |

## Supported File Types

- **DOCX** -- Word documents (formatting preserved)
- **PDF** -- including scanned documents (OCR)
- **XLSX** -- Excel spreadsheets
- **Images** -- PNG, JPG screenshots of medical records

## What Gets Anonymized

| Data Type | Example | Replaced With |
|-----------|---------|---------------|
| Patient names | Ahmet Yilmaz | [AD_1] |
| Dates | 15.03.2020 | [TARIH_1] |
| ID numbers | TC 12345678901 | [KIMLIK_1] |
| Addresses | Kadikoy, Istanbul | [ADRES_1] |
| Phone numbers | 0532 123 4567 | [TELEFON_1] |
| Institutions | Cerrahpasa Tip | [KURUM_1] |

Medical terms, lab values, and diagnoses are **not** touched.

## For Developers

```bash
git clone https://github.com/yourusername/QwenKK.git
cd QwenKK
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m qwenkk
```

### Build the Desktop App

```bash
# macOS
./scripts/build_macos.sh

# Windows
scripts\build_windows.bat

# Linux
./scripts/build_linux.sh
```

## Requirements

- 32 GB+ RAM recommended (model uses ~18 GB)
- ~18 GB disk space for the text model (one-time download)
- +6 GB for the vision model (downloaded on demand for image processing)
- macOS, Windows, or Linux

## License

MIT
