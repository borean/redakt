# Redakt

Local medical document de-identification powered by Qwen LLM.
All processing happens on your machine -- no data leaves your computer.

## How It Works

1. Download the app
2. Double-click to open
3. The app handles everything: downloads the AI model automatically
4. Drag your files in, click **Scan for PII**
5. Get back clean files with all patient data replaced

## Download

| Platform | Download |
|----------|----------|
| macOS | [Redakt.dmg](#) |
| Windows | [Redakt.exe](#) |
| Linux | [Redakt](#) |

## REST API

Run Redakt as a headless API server for hospital EMR integration:

```bash
redakt --serve --port 8080
```

```bash
curl -X POST http://localhost:8080/api/redact \
  -H 'Content-Type: application/json' \
  -d '{"text": "Ahmet Yilmaz, TC: 12345678901"}'
```

### npm Client

```bash
npm install redakt
```

```ts
import { Redakt } from 'redakt';
const client = new Redakt();
const result = await client.redact("Ahmet Yilmaz, TC: 12345678901");
```

## Supported File Types

- **DOCX** -- Word documents (formatting preserved)
- **PDF** -- including scanned documents (OCR)
- **XLSX** -- Excel spreadsheets
- **Images** -- PNG, JPG screenshots of medical records

## What Gets Anonymized

| Data Type | Example | Replaced With |
|-----------|---------|---------------|
| Patient names | Ahmet Yilmaz | [NAME_1] |
| Dates | 15.03.2020 | [DATE_1] |
| ID numbers | TC 12345678901 | [ID_1] |
| Addresses | Kadikoy, Istanbul | [ADDRESS_1] |
| Phone numbers | 0532 123 4567 | [PHONE_1] |
| Institutions | Cerrahpasa Tip | [INSTITUTION_1] |

Medical terms, lab values, and diagnoses are **not** touched.

## For Developers

```bash
git clone https://github.com/borean/redakt.git
cd redakt
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m redakt
```

### Build the Desktop App

```bash
pyinstaller Redakt.spec
```

## Requirements

- 32 GB+ RAM recommended (model uses ~18 GB)
- ~18 GB disk space for the text model (one-time download)
- +6 GB for the vision model (downloaded on demand for image processing)
- macOS, Windows, or Linux

## License

MIT
