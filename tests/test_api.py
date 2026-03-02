"""Tests for the Redakt REST API server."""

import pytest


@pytest.fixture
def api():
    """Create a RedaktAPI instance (no llama-server needed)."""
    from redakt.api.server import RedaktAPI

    api = RedaktAPI(language="en")
    api._ready = True  # Skip llama-server for unit tests
    return api


@pytest.fixture
def app(api):
    from redakt.api.server import _build_app

    return _build_app(api)


@pytest.fixture
def client(app):
    from starlette.testclient import TestClient

    return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "redakt"
        assert data["status"] == "ok"

    def test_health_returns_starting_when_not_ready(self, app):
        from starlette.testclient import TestClient

        # Modify the api to be not ready
        # The app's state is determined by the api instance
        from redakt.api.server import RedaktAPI

        api = RedaktAPI(language="en")
        api._ready = False
        from redakt.api.server import _build_app

        app2 = _build_app(api)
        client2 = TestClient(app2)
        resp = client2.get("/api/health")
        data = resp.json()
        assert data["status"] == "starting"


class TestRedactEndpoint:
    def test_redact_missing_text(self, client):
        resp = client.post("/api/redact", json={})
        assert resp.status_code == 400
        assert "text" in resp.json()["error"].lower()

    def test_redact_empty_text(self, client):
        resp = client.post("/api/redact", json={"text": ""})
        assert resp.status_code == 400

    def test_redact_invalid_json(self, client):
        resp = client.post(
            "/api/redact",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400

    def test_redact_not_ready_returns_503(self):
        from starlette.testclient import TestClient

        from redakt.api.server import RedaktAPI, _build_app

        api = RedaktAPI(language="en")
        api._ready = False
        app = _build_app(api)
        client = TestClient(app)
        resp = client.post("/api/redact", json={"text": "hello"})
        assert resp.status_code == 503

    def test_redact_with_language_override(self, client):
        # Ensures the language field is accepted (actual redaction needs llama-server)
        resp = client.post("/api/redact", json={"text": "test", "language": "tr"})
        # Will either succeed or fail with 500 (no llama-server), but not 400
        assert resp.status_code != 400


class TestRedactFileEndpoint:
    def test_redact_file_no_file(self, client):
        resp = client.post("/api/redact/file")
        assert resp.status_code == 400

    def test_redact_file_not_ready_returns_503(self):
        from starlette.testclient import TestClient

        from redakt.api.server import RedaktAPI, _build_app

        api = RedaktAPI(language="en")
        api._ready = False
        app = _build_app(api)
        client = TestClient(app)
        resp = client.post("/api/redact/file", files={"file": ("test.txt", b"hello")})
        assert resp.status_code == 503


class TestCORS:
    def test_cors_headers_present(self, client):
        resp = client.options(
            "/api/redact",
            headers={
                "origin": "http://localhost:3000",
                "access-control-request-method": "POST",
            },
        )
        assert "access-control-allow-origin" in resp.headers


class TestCLI:
    def test_help_flag(self):
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "redakt", "--help"],
            capture_output=True,
            text=True,
            cwd="/Users/bora/Projects/QwenKK",
        )
        assert result.returncode == 0
        assert "--serve" in result.stdout
        assert "redakt" in result.stdout.lower()

    def test_serve_flag_recognized(self):
        import subprocess
        import sys

        # Just verify --serve doesn't crash immediately (it will try to start server)
        result = subprocess.run(
            [sys.executable, "-m", "redakt", "--serve", "--help"],
            capture_output=True,
            text=True,
            cwd="/Users/bora/Projects/QwenKK",
        )
        # --help should take precedence and show help
        assert result.returncode == 0
