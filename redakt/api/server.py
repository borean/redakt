"""Redakt HTTP API server for hospital EMR integration.

Run with: redakt --serve [--host 127.0.0.1] [--port 8080] [--language tr]

Endpoints:
    GET  /api/health        — Server health check
    POST /api/redact         — Redact text (JSON body)
    POST /api/redact/file    — Redact uploaded file (multipart)
"""

import asyncio
import logging
import sys
import tempfile
from pathlib import Path

from redakt import __version__
from redakt.constants import API_DEFAULT_HOST, API_DEFAULT_PORT, Backend, Language
from redakt.core.anonymizer import Anonymizer
from redakt.core.redactor import (
    find_entity_spans,
    render_placeholder_text,
    render_redacted_plain,
)

log = logging.getLogger("redakt.api")


class RedaktAPI:
    """Core API logic, decoupled from the HTTP framework."""

    def __init__(self, language: str = "tr"):
        self.language = Language(language)
        self.anonymizer = Anonymizer(
            language=self.language,
            backend=Backend.LLAMACPP,
        )
        self._ready = False
        self._llamacpp = None

    async def ensure_ready(self) -> bool:
        """Start llama-server and wait for health."""
        from redakt.api.llamacpp_headless import HeadlessLlamaCpp

        self._llamacpp = HeadlessLlamaCpp()
        self._ready = await self._llamacpp.ensure_ready()
        return self._ready

    async def redact_text(self, text: str, language: str | None = None) -> dict:
        """Detect PII and produce redacted + placeholder text."""
        if language:
            self.anonymizer.language = Language(language)

        # Chunk and detect
        chunks = self.anonymizer.chunk_text(text)
        all_entities = {}

        for chunk in chunks:
            response = await self.anonymizer.detect_pii_from_text(chunk)
            for entity in response.entities:
                if entity.original not in all_entities:
                    all_entities[entity.original] = entity

        entities = self.anonymizer._renumber_placeholders(list(all_entities.values()))

        # Find spans and render
        spans = find_entity_spans(text, entities)
        redacted_text = render_redacted_plain(text, spans)
        placeholder_text = render_placeholder_text(text, spans)

        return {
            "entities": [
                {
                    "original": e.original,
                    "category": e.category,
                    "placeholder": e.placeholder,
                    "confidence": e.confidence,
                    "subcategory": e.subcategory,
                }
                for e in entities
            ],
            "redacted_text": redacted_text,
            "placeholder_text": placeholder_text,
            "entity_count": len(entities),
        }

    def shutdown(self):
        if self._llamacpp:
            self._llamacpp.stop_server()


def _build_app(api: RedaktAPI):
    """Build the Starlette ASGI application."""
    from starlette.applications import Starlette
    from starlette.middleware.cors import CORSMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def health(request: Request):
        return JSONResponse({
            "status": "ok" if api._ready else "starting",
            "service": "redakt",
            "version": __version__,
        })

    async def redact(request: Request):
        if not api._ready:
            return JSONResponse(
                {"error": "Server is still starting. Try again in a moment."},
                status_code=503,
            )

        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                {"error": "Invalid JSON body. Expected: {\"text\": \"...\"}"},
                status_code=400,
            )

        text = body.get("text")
        if not text or not isinstance(text, str):
            return JSONResponse(
                {"error": "Missing or invalid 'text' field. Must be a non-empty string."},
                status_code=400,
            )

        language = body.get("language")

        try:
            result = await api.redact_text(text, language=language)
            return JSONResponse(result)
        except Exception as e:
            log.exception("Redaction failed")
            return JSONResponse(
                {"error": f"Redaction failed: {e}"},
                status_code=500,
            )

    async def redact_file(request: Request):
        if not api._ready:
            return JSONResponse({"error": "Server starting"}, status_code=503)

        try:
            form = await request.form()
        except Exception:
            return JSONResponse(
                {"error": "Invalid multipart form data"},
                status_code=400,
            )

        upload = form.get("file")
        if not upload:
            return JSONResponse(
                {"error": "No file uploaded. Send a 'file' field."},
                status_code=400,
            )

        language = form.get("language")
        suffix = Path(upload.filename).suffix if upload.filename else ".txt"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            content = await upload.read()
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            from redakt.parsers import get_parser

            parser = get_parser(tmp_path)
            parse_result = parser.extract_text(tmp_path)
            result = await api.redact_text(parse_result.text, language=language)
            result["filename"] = upload.filename
            return JSONResponse(result)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        except Exception as e:
            log.exception("File redaction failed")
            return JSONResponse(
                {"error": f"File redaction failed: {e}"},
                status_code=500,
            )
        finally:
            tmp_path.unlink(missing_ok=True)

    routes = [
        Route("/api/health", health, methods=["GET"]),
        Route("/api/redact", redact, methods=["POST"]),
        Route("/api/redact/file", redact_file, methods=["POST"]),
    ]

    app = Starlette(routes=routes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app


def run_server(
    host: str = API_DEFAULT_HOST,
    port: int = API_DEFAULT_PORT,
    language: str = "tr",
):
    """Entry point for --serve mode."""
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )

    api = RedaktAPI(language=language)
    app = _build_app(api)

    @app.on_event("startup")
    async def on_startup():
        ready = await api.ensure_ready()
        if not ready:
            log.error("Failed to start llama-server. API will return 503.")

    @app.on_event("shutdown")
    async def on_shutdown():
        api.shutdown()

    print(f"\n  REDAKT API SERVER v{__version__}")
    print(f"  Listening on http://{host}:{port}")
    print()
    print("  Endpoints:")
    print("    GET  /api/health        Health check")
    print("    POST /api/redact        Redact text (JSON)")
    print("    POST /api/redact/file   Redact file (multipart)")
    print()

    uvicorn.run(app, host=host, port=port, log_level="info")
