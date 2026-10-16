import logging
from io import StringIO
from pathlib import Path

from fastapi.testclient import TestClient

from treesleuth.analysis import AuditResponse, BiographyResponse, OllamaServiceError
from treesleuth.config import Settings
from treesleuth.pipeline import PipelineCoordinator
from treesleuth.__main__ import main
from treesleuth.logging_config import configure_logging
from treesleuth.main import create_app
import treesleuth.main as main_module


class FakeAnalyzer:
    def __init__(self, unavailable: bool = False) -> None:
        self.unavailable = unavailable

    async def available_models(self) -> list[str]:
        if self.unavailable:
            raise OllamaServiceError("Ollama is offline")
        return ["qwen2.5:14b"]


    async def audit(self, _model, _person, _documents, cluster=None) -> AuditResponse:
        return AuditResponse(findings=[])

    async def biography(self, _model, _person, documents, cluster=None) -> BiographyResponse:
        return BiographyResponse(
            biography="A local test biography.",
            claims=[
                {
                    "claim": "A source-backed statement.",
                    "source_ids": [documents[0].id],
                    "inferred": False,
                }
            ],
        )


class NoOcrExtractor:
    def extract_text(self, _source: Path) -> str:
        raise AssertionError("Directory preview must not start OCR")


class FakeTextExtractor:
    def extract_text(self, source: Path) -> str:
        return source.read_text(encoding="utf-8")


def client_for(analyzer: FakeAnalyzer, extractor=None) -> TestClient:
    coordinator = PipelineCoordinator(
        settings=Settings(max_workers=1),
        analyzer=analyzer,
        extractor=extractor or NoOcrExtractor(),
    )
    return TestClient(create_app(coordinator))


def test_system_check_returns_local_models() -> None:
    with client_for(FakeAnalyzer()) as client:
        response = client.get("/api/system-check")

    assert response.status_code == 200
    assert response.json() == {"ollama_available": True, "models": ["qwen2.5:14b"], "error": None}


def test_system_check_reports_ollama_unavailable() -> None:
    with client_for(FakeAnalyzer(unavailable=True)) as client:
        response = client.get("/api/system-check")

    assert response.status_code == 200
    assert response.json()["ollama_available"] is False
    assert response.json()["error"] == "Ollama is offline"
    assert response.json()["models"] == []


def test_directory_preview_is_structural_and_does_not_run_ocr(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "family.ged").write_text("0 HEAD", encoding="utf-8")
    (tmp_path / "nested" / "letter.pdf").write_bytes(b"pdf")
    (tmp_path / "note.txt").write_text("note", encoding="utf-8")
    with client_for(FakeAnalyzer()) as client:
        response = client.post("/api/analyze-directory", json={"path": str(tmp_path)})

    assert response.status_code == 200
    assert response.json()["gedcom_files"] == 1
    assert response.json()["document_files"] == 2
    assert response.json()["has_gedcom_baseline"] is True
    assert response.json()["files_by_type"] == {"gedcom": 1, "pdf": 1, "text": 1}


def test_directory_preview_returns_and_logs_path_specific_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    log_path = tmp_path / "logs" / "treesleuth.log"
    monkeypatch.setattr(main_module, "configure_logging", lambda: configure_logging(log_path.parent))
    with client_for(FakeAnalyzer()) as client:
        response = client.post(
            "/api/analyze-directory",
            json={"path": str(tmp_path / "missing")},
        )

    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"]
    log_content = log_path.read_text(encoding="utf-8")
    assert "API directory preview rejected path" in log_content
    assert str(tmp_path / "missing") in log_content
    assert "Traceback (most recent call last)" in log_content


def test_pipeline_start_and_sse_report_ordered_completion(tmp_path: Path) -> None:
    (tmp_path / "letter.txt").write_text(
        "Ada Lovelace lived in London from 1830 to 1850.", encoding="utf-8"
    )
    with client_for(FakeAnalyzer(), FakeTextExtractor()) as client:
        start = client.post(
            "/api/run-pipeline",
            json={"path": str(tmp_path), "model": "qwen2.5:14b"},
        )
        assert start.status_code == 202
        run_id = start.json()["run_id"]
        events_url = start.json()["events_url"]
        with client.stream("GET", events_url) as stream:
            event_text = "".join(stream.iter_text())
        snapshot = client.get(f"/api/runs/{run_id}")

    assert "event: stage" in event_text
    assert "event: person" in event_text
    assert "event: complete" in event_text
    assert snapshot.status_code == 200
    assert snapshot.json()["status"] == "completed"
    assert snapshot.json()["people"][0]["status"] == "Finished"


def test_sse_rejects_invalid_last_event_id(tmp_path: Path) -> None:
    with client_for(FakeAnalyzer()) as client:
        start = client.post(
            "/api/run-pipeline",
            json={"path": str(tmp_path), "model": "qwen2.5:14b"},
        )
        response = client.get(
            f"/api/runs/{start.json()['run_id']}/events",
            headers={"Last-Event-ID": "not-a-number"},
        )

    assert response.status_code == 400


def test_run_detail_returns_not_found_for_unknown_run() -> None:
    with client_for(FakeAnalyzer()) as client:
        response = client.get("/api/runs/not-a-run")

    assert response.status_code == 404


def test_default_server_binding_is_localhost(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(app: str, *, host: str, port: int) -> None:
        captured.update({"app": app, "host": host, "port": port})

    monkeypatch.setattr("treesleuth.__main__.uvicorn.run", fake_run)
    monkeypatch.setattr(
        "treesleuth.__main__.configure_logging",
        lambda: configure_logging(tmp_path / "logs"),
    )
    main()

    assert captured == {
        "app": "treesleuth.main:app",
        "host": "127.0.0.1",
        "port": 8000,
    }
    assert (tmp_path / "logs" / "treesleuth.log").is_file()
    assert len(
        [
            handler
            for handler in logging.getLogger("treesleuth").handlers
            if getattr(handler, "_treesleuth_file_handler", False)
        ]
    ) == 1


def test_asgi_startup_configures_file_logging_without_replacing_console_handler(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_logger = logging.getLogger("treesleuth")
    console_stream = StringIO()
    console_handler = logging.StreamHandler(console_stream)
    package_logger.addHandler(console_handler)
    monkeypatch.setattr(main_module, "configure_logging", lambda: configure_logging(tmp_path / "logs"))

    try:
        with TestClient(create_app(PipelineCoordinator(settings=Settings(max_workers=1)))) as client:
            assert client.get("/").status_code == 200

        assert console_handler in package_logger.handlers
        file_handlers = [
            handler
            for handler in package_logger.handlers
            if getattr(handler, "_treesleuth_file_handler", False)
        ]
        assert len(file_handlers) == 1
        assert (tmp_path / "logs" / "treesleuth.log").is_file()
    finally:
        package_logger.removeHandler(console_handler)
        console_handler.close()


def test_api_does_not_enable_cross_origin_access_or_arbitrary_file_reads(tmp_path: Path) -> None:
    with client_for(FakeAnalyzer()) as client:
        preflight = client.options(
            "/api/system-check",
            headers={
                "Origin": "https://remote.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        arbitrary_file = client.get("/api/files", params={"path": str(tmp_path / "secret.txt")})

    assert "access-control-allow-origin" not in preflight.headers
    assert arbitrary_file.status_code == 404


def test_dashboard_assets_are_served_without_frontend_build() -> None:
    with client_for(FakeAnalyzer()) as client:
        page = client.get("/")
        script = client.get("/app.js")

    assert page.status_code == 200
    assert 'src="https://cdn.tailwindcss.com"' in page.text
    assert 'id="directoryPath"' in page.text
    assert 'id="modelSelect"' in page.text
    assert script.status_code == 200
    assert "EventSource" in script.text
