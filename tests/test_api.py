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

GEDCOM = """0 HEAD
1 SOUR test
1 GEDC
2 VERS 5.5
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Ada /Lovelace/
0 TRLR
"""


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


class NoTranscriptionExtractor:
    def extract_text(self, _source: Path) -> str:
        raise AssertionError("Directory preview must not start transcription")


class FakeTextExtractor:
    def extract_text(self, source: Path) -> str:
        return source.read_text(encoding="utf-8")


def client_for(analyzer: FakeAnalyzer, extractor=None, app_data_root: Path | None = None) -> TestClient:
    coordinator = PipelineCoordinator(
        settings=Settings(max_workers=1),
        analyzer=analyzer,
        extractor=extractor or NoTranscriptionExtractor(),
        app_data_root=app_data_root,
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


def test_directory_preview_is_structural_and_does_not_run_transcription(tmp_path: Path) -> None:
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
    with client_for(FakeAnalyzer(), FakeTextExtractor(), tmp_path / ".cache") as client:
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
    assert snapshot.json()["people"][0]["status"] == "Ready"
    assert snapshot.json()["people"][0]["biography"] is None


def test_story_generation_is_explicit_and_streams_its_own_run(tmp_path: Path) -> None:
    (tmp_path / "letter.txt").write_text(
        "Ada Lovelace lived in London from 1830 to 1850.", encoding="utf-8"
    )
    with client_for(FakeAnalyzer(), FakeTextExtractor(), tmp_path / ".cache") as client:
        start = client.post(
            "/api/run-pipeline",
            json={"path": str(tmp_path), "model": "qwen2.5:14b"},
        )
        preparation_id = start.json()["run_id"]
        preparation_events = client.get(start.json()["events_url"]).text
        prepared = client.get(f"/api/runs/{preparation_id}").json()
        person_id = prepared["people"][0]["id"]
        generation = client.post(
            f"/api/runs/{preparation_id}/generate",
            json={"person_id": person_id},
        )
        generation_events = client.get(generation.json()["events_url"]).text
        generated = client.get(f"/api/runs/{generation.json()['run_id']}").json()

    assert start.status_code == 202
    assert generation.status_code == 202
    assert "event: complete" in preparation_events
    assert "event: complete" in generation_events
    assert generated["parent_run_id"] == preparation_id
    assert generated["people"][0]["status"] == "Finished"
    assert generated["people"][0]["biography"] == "A local test biography."
    assert list((tmp_path / ".cache" / "results").rglob("*_LifeStory.txt"))


def test_story_generation_accepts_checked_people_as_a_batch(tmp_path: Path) -> None:
    (tmp_path / "family.ged").write_text(
        GEDCOM.replace(
            "0 TRLR",
            "0 @I2@ INDI\n1 NAME Grace /Hopper/\n0 TRLR",
        ),
        encoding="utf-8",
    )
    (tmp_path / "letter.txt").write_text(
        "Ada Lovelace lived in London from 1830 to 1850.", encoding="utf-8"
    )
    with client_for(FakeAnalyzer(), FakeTextExtractor(), tmp_path / ".cache") as client:
        preparation = client.post(
            "/api/run-pipeline",
            json={"path": str(tmp_path), "model": "qwen2.5:14b"},
        )
        preparation_id = preparation.json()["run_id"]
        client.get(preparation.json()["events_url"])
        prepared = client.get(f"/api/runs/{preparation_id}").json()
        selected_ids = [prepared["people"][0]["id"]]
        generation = client.post(
            f"/api/runs/{preparation_id}/generate",
            json={"person_ids": selected_ids},
        )
        client.get(generation.json()["events_url"])
        generated = client.get(f"/api/runs/{generation.json()['run_id']}").json()

    assert generation.status_code == 202
    assert {person["id"] for person in generated["people"]} == set(selected_ids)
    assert generated["people"][0]["status"] == "Finished"


def test_generation_rejects_unknown_person(tmp_path: Path) -> None:
    with client_for(FakeAnalyzer(), app_data_root=tmp_path / ".cache") as client:
        start = client.post(
            "/api/run-pipeline",
            json={"path": str(tmp_path), "model": "qwen2.5:14b"},
        )
        run_id = start.json()["run_id"]
        client.get(start.json()["events_url"])
        unknown_person = client.post(
            f"/api/runs/{run_id}/generate",
            json={"person_id": "not-a-person"},
        )

    assert unknown_person.status_code == 404


def test_generation_reports_ollama_failure_without_claiming_success(tmp_path: Path) -> None:
    (tmp_path / "letter.txt").write_text(
        "Ada Lovelace lived in London from 1830 to 1850.", encoding="utf-8"
    )
    with client_for(
        FakeAnalyzer(unavailable=True),
        FakeTextExtractor(),
        tmp_path / ".cache",
    ) as client:
        preparation = client.post(
            "/api/run-pipeline",
            json={"path": str(tmp_path), "model": "qwen2.5:14b"},
        )
        prepared_id = preparation.json()["run_id"]
        client.get(preparation.json()["events_url"])
        person_id = client.get(f"/api/runs/{prepared_id}").json()["people"][0]["id"]
        generation = client.post(
            f"/api/runs/{prepared_id}/generate",
            json={"person_id": person_id},
        )
        events = client.get(generation.json()["events_url"]).text
        snapshot = client.get(f"/api/runs/{generation.json()['run_id']}").json()

    assert generation.status_code == 202
    assert "event: error" in events
    assert snapshot["status"] == "failed"
    assert snapshot["people"][0]["status"] == "Failed"
    assert "Ollama is offline" in snapshot["people"][0]["error"]


def test_surname_mappings_are_validated_and_persisted_across_runs(tmp_path: Path) -> None:
    research_root = tmp_path / "research"
    research_root.mkdir()
    (research_root / "family.ged").write_text(GEDCOM, encoding="utf-8")
    with client_for(FakeAnalyzer(), app_data_root=tmp_path / ".cache") as client:
        first_start = client.post(
            "/api/run-pipeline",
            json={"path": str(research_root), "model": "qwen2.5:14b"},
        )
        client.get(first_start.json()["events_url"])
        first_run_id = first_start.json()["run_id"]
        person = client.get(f"/api/runs/{first_run_id}").json()["people"][0]
        saved = client.put(
            f"/api/runs/{first_run_id}/surname-mappings",
            json={"mappings": {"Lovelace": "Byron"}},
        )
        updated = client.get(f"/api/runs/{first_run_id}").json()
        invalid = client.put(
            f"/api/runs/{first_run_id}/surname-mappings",
            json={"mappings": {"Lovelace": ""}},
        )
        second_start = client.post(
            "/api/run-pipeline",
            json={"path": str(research_root), "model": "qwen2.5:14b"},
        )
        client.get(second_start.json()["events_url"])
        second_run = client.get(f"/api/runs/{second_start.json()['run_id']}").json()

    assert person["name"] == "Ada Lovelace"
    assert person["surname"] == "Lovelace"
    assert saved.status_code == 200
    assert saved.json()["mappings"] == {"lovelace": "Byron"}
    assert updated["surname_mappings"] == {"lovelace": "Byron"}
    assert updated["people"][0]["name"] == "Ada Lovelace"
    assert updated["people"][0]["display_surname"] == "Byron"
    assert invalid.status_code == 400
    assert second_run["surname_mappings"] == {"lovelace": "Byron"}
    assert second_run["people"][0]["display_surname"] == "Byron"


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
