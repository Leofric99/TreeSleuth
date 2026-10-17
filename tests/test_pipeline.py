import asyncio
import threading
from pathlib import Path

import pytest

from treesleuth.analysis import AuditResponse, BiographyResponse
from treesleuth.config import Settings
from treesleuth.pipeline import (
    PipelineCapacityError,
    PipelineCoordinator,
    PipelineGenerationInProgressError,
    PipelinePersonNotFoundError,
    PipelinePreparationNotReadyError,
    RunRecord,
)
from treesleuth import pipeline as pipeline_module


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
        self.audit_calls = 0
        self.biography_calls = 0

    async def available_models(self) -> list[str]:
        if self.block:
            await self.block.wait()
        return ["local-model"]

    async def audit(self, _model: str, _person, documents, cluster=None) -> AuditResponse:
        self.audit_calls += 1
        return AuditResponse(findings=[])

    async def biography(self, _model: str, _person, documents, cluster=None) -> BiographyResponse:
        self.biography_calls += 1
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
async def test_gedcom_people_are_published_before_blocked_document_extraction(
    tmp_path: Path,
) -> None:
    research_folder(tmp_path)
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
            if event.event == "person":
                assert event.payload["name"] == "Ada Lovelace"
                assert event.payload["document_count"] == 0
                assert not extractor.started.is_set()
                assert await asyncio.to_thread(extractor.started.wait, timeout=1)
                break
        else:
            pytest.fail("GEDCOM person was not published before document extraction")
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
    assert all(person.status == "Ready" for person in run.people.values())
    assert all(person.document_count == 1 for person in run.people.values())
    assert not (tmp_path / "output").exists()
    assert coordinator.analyzer.audit_calls == 0
    assert coordinator.analyzer.biography_calls == 0
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_pipeline_enforces_active_run_limit(tmp_path: Path) -> None:
    research_folder(tmp_path)
    extractor = BlockingExtractor()
    coordinator = PipelineCoordinator(
        settings=Settings(max_workers=1, max_active_runs=1),
        extractor=extractor,
        analyzer=FakeAnalyzer(),
    )

    first = await coordinator.start(tmp_path, "local-model")
    assert await asyncio.to_thread(extractor.started.wait, timeout=1)
    with pytest.raises(PipelineCapacityError, match="maximum number"):
        await coordinator.start(tmp_path, "local-model")
    extractor.release.set()
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
    extractor = BlockingExtractor()
    coordinator = PipelineCoordinator(
        settings=Settings(max_workers=1),
        extractor=extractor,
        analyzer=FakeAnalyzer(),
    )
    run = await coordinator.start(tmp_path, "local-model")
    stream = coordinator.stream_events(run)
    first_event = await anext(stream)
    await stream.aclose()
    assert await asyncio.to_thread(extractor.started.wait, timeout=1)

    assert first_event.event == "stage"
    assert run.status == "running"
    assert run.task is not None and not run.task.cancelled()
    extractor.release.set()
    await run.task
    assert run.status == "completed"
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_preparation_does_not_require_ollama_or_generate_stories(tmp_path: Path) -> None:
    research_folder(tmp_path)

    class UnavailableAnalyzer(FakeAnalyzer):
        async def available_models(self) -> list[str]:
            raise ConnectionError("Ollama is offline")

    analyzer = UnavailableAnalyzer()
    coordinator = PipelineCoordinator(
        settings=Settings(max_workers=1),
        extractor=FakeExtractor(),
        analyzer=analyzer,
    )
    run = await coordinator.start(tmp_path, "local-model")
    events = [event async for event in coordinator.stream_events(run)]
    await run.task

    assert run.status == "completed"
    assert run.prepared
    assert events[-1].event == "complete"
    assert analyzer.audit_calls == 0
    assert analyzer.biography_calls == 0
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_preparation_creates_provisional_people_without_generation(tmp_path: Path) -> None:
    (tmp_path / "record.txt").write_text(
        "Jane Doe was born in 1840 and lived in London.", encoding="utf-8"
    )
    analyzer = FakeAnalyzer()
    coordinator = PipelineCoordinator(
        settings=Settings(max_workers=1),
        extractor=FakeExtractor(),
        analyzer=analyzer,
    )
    run = await coordinator.start(tmp_path, "local-model")
    await run.task

    assert run.status == "completed"
    assert run.prepared
    assert len(run.people) == 1
    assert next(iter(run.people.values())).status == "Ready"
    assert next(iter(run.people.values())).document_count == 1
    assert analyzer.audit_calls == 0
    assert analyzer.biography_calls == 0
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_generation_reuses_prepared_evidence_and_rejects_duplicate_person_jobs(
    tmp_path: Path,
) -> None:
    research_folder(tmp_path)
    release = asyncio.Event()
    analyzer = FakeAnalyzer(block=release)
    coordinator = PipelineCoordinator(
        settings=Settings(max_workers=1),
        extractor=FakeExtractor(),
        analyzer=analyzer,
        app_data_root=tmp_path / ".cache",
    )
    prepared_run = await coordinator.start(tmp_path, "local-model")
    with pytest.raises(PipelinePreparationNotReadyError, match="must complete"):
        await coordinator.generate(prepared_run.run_id)
    await prepared_run.task
    person_id = next(iter(prepared_run.prepared_people))

    generation_run = await coordinator.generate(prepared_run.run_id, person_id)
    await asyncio.sleep(0)
    with pytest.raises(PipelineGenerationInProgressError, match="already in progress"):
        await coordinator.generate(prepared_run.run_id, person_id)
    release.set()
    await generation_run.task

    assert generation_run.status == "completed"
    assert generation_run.parent_run_id == prepared_run.run_id
    assert generation_run.people[person_id].status == "Finished"
    assert analyzer.audit_calls == 1
    assert analyzer.biography_calls == 1
    assert prepared_run.people[person_id].status == "Finished"
    with pytest.raises(PipelinePersonNotFoundError, match="Person not found"):
        await coordinator.generate(prepared_run.run_id, "not-a-person")
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_generate_all_continues_after_a_person_without_evidence_fails(
    tmp_path: Path,
) -> None:
    research_folder(tmp_path)
    gedcom = tmp_path / "tree" / "family.ged"
    gedcom.write_text(
        GEDCOM.replace(
            "0 TRLR",
            "0 @I2@ INDI\n1 NAME Grace /Hopper/\n0 TRLR",
        ),
        encoding="utf-8",
    )
    coordinator = PipelineCoordinator(
        settings=Settings(max_workers=1),
        extractor=FakeExtractor(),
        analyzer=FakeAnalyzer(),
        app_data_root=tmp_path / ".cache",
    )
    prepared_run = await coordinator.start(tmp_path, "local-model")
    await prepared_run.task

    generation_run = await coordinator.generate(prepared_run.run_id)
    events = [event async for event in coordinator.stream_events(generation_run)]
    await generation_run.task

    assert generation_run.status == "completed"
    assert {person.status for person in generation_run.people.values()} == {"Finished", "Failed"}
    assert any(event.event == "warning" for event in events)
    assert events[-1].event == "complete"
    await coordinator.shutdown()
