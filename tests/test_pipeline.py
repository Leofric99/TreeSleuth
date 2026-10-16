import asyncio
import threading
from pathlib import Path

import pytest

from treesleuth.analysis import AuditResponse, BiographyResponse
from treesleuth.config import Settings
from treesleuth.pipeline import PipelineCapacityError, PipelineCoordinator, RunRecord
from treesleuth.models import PipelineEvent
from treesleuth import pipeline as pipeline_module
from treesleuth.logging_config import configure_logging


GEDCOM = """0 HEAD
1 SOUR test
1 GEDC
2 VERS 5.5
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Ada /Lovelace/
1 BIRT
2 DATE 10 DEC 1815
1 DEAT
2 DATE 27 NOV 1852
0 TRLR
"""


class FakeExtractor:
    def extract_text(self, source: Path) -> str:
        return source.read_text(encoding="utf-8")


class BlockingExtractor(FakeExtractor):
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def extract_text(self, source: Path) -> str:
        self.started.set()
        if not self.release.wait(timeout=5):
            raise TimeoutError("Test extractor was not released")
        return super().extract_text(source)


class FakeAnalyzer:
    def __init__(self, block: asyncio.Event | None = None) -> None:
        self.block = block

    async def available_models(self) -> list[str]:
        if self.block:
            await self.block.wait()
        return ["local-model"]

    async def audit(self, _model: str, _person, documents, cluster=None) -> AuditResponse:
        return AuditResponse(findings=[])

    async def biography(self, _model: str, _person, documents, cluster=None) -> BiographyResponse:
        if not documents:
            raise ValueError("No source evidence")
        return BiographyResponse(
            biography="A source-attributed life story.",
            claims=[{"claim": "A documented fact.", "source_ids": [documents[0].id], "inferred": False}],
        )


def research_folder(root: Path) -> None:
    (root / "tree").mkdir()
    (root / "records").mkdir()
    (root / "tree" / "family.ged").write_text(GEDCOM, encoding="utf-8")
    (root / "records" / "letter.txt").write_text(
        "Ada Lovelace wrote a letter in 1840.", encoding="utf-8"
    )


@pytest.mark.asyncio
async def test_pipeline_reports_progress_while_document_extraction_is_running(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    research_folder(tmp_path)
    monkeypatch.setattr(pipeline_module, "_EXTRACTION_PROGRESS_INTERVAL_SECONDS", 0.01)
    extractor = BlockingExtractor()
    coordinator = PipelineCoordinator(
        settings=Settings(max_workers=1),
        extractor=extractor,
        analyzer=FakeAnalyzer(),
    )
    run = await coordinator.start(tmp_path, "local-model")
    stream = coordinator.stream_events(run)

    try:
        async for event in stream:
            if event.message.startswith("Still processing document"):
                assert f"document 1 of 1: {Path('records') / 'letter.txt'}" in event.message
                assert "(1s elapsed)" in event.message
                assert event.source_path == str(tmp_path / "records" / "letter.txt")
                break
        else:
            pytest.fail("No extraction progress event was emitted")
    finally:
        extractor.release.set()
        await stream.aclose()
        assert run.task is not None
        await run.task
        await coordinator.shutdown()


@pytest.mark.asyncio
async def test_pipeline_emits_ordered_stages_and_terminal_completion(tmp_path: Path) -> None:
    research_folder(tmp_path)
    coordinator = PipelineCoordinator(
        settings=Settings(max_workers=1, max_active_runs=1),
        extractor=FakeExtractor(),
        analyzer=FakeAnalyzer(),
    )

    run = await coordinator.start(tmp_path, "local-model")
    events = [event async for event in coordinator.stream_events(run)]
    await run.task

    assert run.status == "completed"
    assert events[-1].event == "complete"
    assert [event.sequence for event in events] == list(range(len(events)))
    assert any(event.stage == "Comparing with GEDCOM" for event in events)
    assert any(person.status == "Finished" for person in run.people.values())
    assert (tmp_path / "output").is_dir()
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_pipeline_enforces_active_run_limit(tmp_path: Path) -> None:
    research_folder(tmp_path)
    release = asyncio.Event()
    coordinator = PipelineCoordinator(
        settings=Settings(max_workers=1, max_active_runs=1),
        extractor=FakeExtractor(),
        analyzer=FakeAnalyzer(block=release),
    )

    first = await coordinator.start(tmp_path, "local-model")
    with pytest.raises(PipelineCapacityError, match="maximum number"):
        await coordinator.start(tmp_path, "local-model")
    release.set()
    await first.task

    assert first.status == "completed"
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_run_event_buffer_is_bounded_and_sequence_is_monotonic() -> None:
    run = RunRecord(run_id="run", root=Path("."), model="local", event_limit=10)

    for index in range(20):
        await run.publish("stage", "Working", f"event {index}")

    assert len(run.events) == 10
    assert [event.sequence for event in run.events] == list(range(10, 20))


@pytest.mark.asyncio
async def test_closing_event_stream_does_not_cancel_pipeline(tmp_path: Path) -> None:
    research_folder(tmp_path)
    release = asyncio.Event()
    coordinator = PipelineCoordinator(
        settings=Settings(max_workers=1),
        extractor=FakeExtractor(),
        analyzer=FakeAnalyzer(block=release),
    )
    run = await coordinator.start(tmp_path, "local-model")
    stream = coordinator.stream_events(run)
    first_event = await anext(stream)
    await stream.aclose()

    assert first_event.event == "stage"
    assert run.status == "running"
    assert run.task is not None and not run.task.cancelled()
    release.set()
    await run.task
    assert run.status == "completed"
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_model_failure_sets_terminal_failed_status(tmp_path: Path) -> None:
    research_folder(tmp_path)
    log_path = configure_logging(tmp_path / "logs")

    class UnavailableAnalyzer(FakeAnalyzer):
        async def available_models(self) -> list[str]:
            raise ConnectionError("Ollama is offline")

    coordinator = PipelineCoordinator(
        settings=Settings(max_workers=1),
        extractor=FakeExtractor(),
        analyzer=UnavailableAnalyzer(),
    )
    run = await coordinator.start(tmp_path, "local-model")
    events = [event async for event in coordinator.stream_events(run)]
    await run.task

    assert run.status == "failed"
    assert events[-1].event == "error"
    assert "Ollama is offline" in (run.error or "")
    log_content = log_path.read_text(encoding="utf-8")
    assert f"Pipeline run {run.run_id} failed" in log_content
    assert str(tmp_path) in log_content
    assert "ConnectionError: Ollama is offline" in log_content
    assert "Traceback (most recent call last)" in log_content
    await coordinator.shutdown()
