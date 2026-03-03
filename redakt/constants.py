from enum import Enum

# ── Backend (llama.cpp only — no user setup required) ─────────────────

class Backend(str, Enum):
    LLAMACPP = "llamacpp"

# llama.cpp backend (serves Qwen3.5 via llama-server)
LLAMACPP_HOST = "http://localhost:8081"
LLAMACPP_MODEL = "Qwen3.5-35B-A3B-Q4_K_M"
LLAMACPP_API_MODEL = "qwen"  # Model name sent in API requests

# GGUF model download configuration
GGUF_HF_REPO = "unsloth/Qwen3.5-35B-A3B-GGUF"
GGUF_HF_BASE_URL = "https://huggingface.co/unsloth/Qwen3.5-35B-A3B-GGUF/resolve/main"
GGUF_DEFAULT_QUANT = "Q4_K_M"

# Redakt API server defaults
API_DEFAULT_HOST = "127.0.0.1"
API_DEFAULT_PORT = 8080

# ── File handling ────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS = {".docx", ".pdf", ".xlsx", ".png", ".jpg", ".jpeg", ".bmp", ".tiff"}


class Language(str, Enum):
    TR = "tr"
    EN = "en"


class FileType(str, Enum):
    DOCX = "docx"
    PDF = "pdf"
    EXCEL = "xlsx"
    IMAGE = "image"
