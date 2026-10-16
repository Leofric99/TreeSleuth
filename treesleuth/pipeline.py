import asyncio
import logging
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Callable
from uuid import uuid4

from treesleuth.analysis import (
    AuditResponse,
    BiographyResponse,
    ModelInferenceError,
    OllamaAnalyzer,
    OllamaServiceError,
)
from treesleuth.cache import ExtractionCache
from treesleuth.config import Settings, get_settings
from treesleuth.discovery import DirectoryScan, scan_directory
from treesleuth.entity_resolution import (
    ProvisionalCluster,
    ResearchDocument,
    cluster_without_gedcom,
    correlate_documents,
)
from treesleuth.extraction import DoclingExtractor, DocumentExtractionError
from treesleuth.gedcom import GedcomIndex, IndividualRecord, parse_gedcom_files
from treesleuth.models import (
    PipelineEvent,
    PipelineEventKind,
    PipelineStatus,
    PersonRunResult,
    RunSnapshot,
)
from treesleuth.paths import validate_research_root
from treesleuth.results import OutputWriteError, SavedAnalysis, save_analysis_results

logger = logging.getLogger(__name__)
_EXTRACTION_PROGRESS_INTERVAL_SECONDS = 15


class PipelineCapacityError(RuntimeError):
    """Raised when the configured number of concurrent runs has been reached."""


class PipelineRunNotFoundError(LookupError):
    """Raised when a requested pipeline run is unknown."""


@dataclass
class RunRecord:
    run_id: str
    root: Path
    model: str
    event_limit: int
    status: PipelineStatus = "queued"
    events: deque[PipelineEvent] = field(default_factory=deque)
    sequence: int = 0
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    task: asyncio.Task[None] | None = None
    people: dict[str, PersonRunResult] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    async def publish(
        self,
        event: PipelineEventKind,
        stage: str,
        message: str,
        *,
        person_id: str | None = None,
        source_path: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        async with self.condition:
            if event == "complete":
                self.status = "completed"
            elif event == "error":
                self.status = "failed"
            current = PipelineEvent(
                run_id=self.run_id,
                sequence=self.sequence,
                event=event,
                stage=stage,
                message=message,
                person_id=person_id,
                source_path=source_path,
                payload=payload or {},
            )
            self.sequence += 1
            self.events.append(current)
            while len(self.events) > self.event_limit:
                self.events.popleft()
            self.condition.notify_all()

    def snapshot(self) -> RunSnapshot:
        return RunSnapshot(
            run_id=self.run_id,
            status=self.status,
            people=list(self.people.values()),
            warnings=list(self.warnings),
            error=self.error,
        )


class PipelineCoordinator:
    def __init__(
        self,
        settings: Settings | None = None,
        extractor: DoclingExtractor | None = None,
        analyzer: OllamaAnalyzer | None = None,
        scanner: Callable[[str | Path], DirectoryScan] = scan_directory,
        gedcom_parser: Callable[[list[Path]], GedcomIndex] = parse_gedcom_files,
        cache_factory: Callable[[Path, str], ExtractionCache] = ExtractionCache,
    ) -> None:
        self.settings = settings or get_settings()
        self.extractor = extractor or DoclingExtractor()
        self.analyzer = analyzer or OllamaAnalyzer(self.settings)
        self.scanner = scanner
        self.gedcom_parser = gedcom_parser
        self.cache_factory = cache_factory
        self._runs: dict[str, RunRecord] = {}
        self._lock = asyncio.Lock()
        self._executor = ThreadPoolExecutor(max_workers=self.settings.max_workers)

    async def start(self, path: str | Path, model: str) -> RunRecord:
        root = validate_research_root(path)
        if not model.strip():
            raise ValueError("A local Ollama model must be selected")
        async with self._lock:
            active = sum(run.status in {"queued", "running"} for run in self._runs.values())
            if active >= self.settings.max_active_runs:
                raise PipelineCapacityError("The maximum number of active analysis runs has been reached")
            run = RunRecord(
                run_id=str(uuid4()),
                root=root,
                model=model.strip(),
                event_limit=self.settings.max_run_events,
                status="running",
            )
            self._runs[run.run_id] = run
            run.task = asyncio.create_task(self._execute(run))
            return run

    def get_run(self, run_id: str) -> RunRecord:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise PipelineRunNotFoundError(f"Pipeline run not found: {run_id}") from exc

    async def stream_events(self, run: RunRecord, after_sequence: int = -1) -> AsyncIterator[PipelineEvent]:
        cursor = after_sequence
        while True:
            async with run.condition:
                pending = [event for event in run.events if event.sequence > cursor]
                if not pending and run.status not in {"completed", "failed"}:
                    await run.condition.wait()
                    pending = [event for event in run.events if event.sequence > cursor]
                finished = run.status in {"completed", "failed"}
            for event in pending:
                cursor = event.sequence
                yield event
            if finished and not pending:
                return

    async def _run_blocking(self, function: Callable[..., object], *args: object) -> object:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, function, *args)

    async def _run_blocking_with_progress(
        self,
        run: RunRecord,
        description: str,
        source_path: str,
        function: Callable[..., object],
        *args: object,
    ) -> object:
        task = asyncio.create_task(self._run_blocking(function, *args))
        loop = asyncio.get_running_loop()
        started_at = loop.time()
        try:
            while True:
                done, _ = await asyncio.wait(
                    {task},
                    timeout=_EXTRACTION_PROGRESS_INTERVAL_SECONDS,
                )
                if done:
                    return await task
                elapsed = max(1, round(loop.time() - started_at))
                await run.publish(
                    "file",
                    "Parsing Records",
                    f"Still processing {description} ({elapsed}s elapsed)",
                    source_path=source_path,
                )
        finally:
            if not task.done():
                task.cancel()

    async def _execute(self, run: RunRecord) -> None:
        logger.info(
            "Starting pipeline run %s for research root %s with model %s",
            run.run_id,
            run.root,
            run.model,
        )
        try:
            await run.publish("stage", "Scanning", "Checking local model and scanning the selected directory")
            available = await self.analyzer.available_models()
            if run.model not in available:
                raise OllamaServiceError(f"Selected model is not installed locally: {run.model}")

            scan = await self._run_blocking(self.scanner, run.root)
            if not isinstance(scan, DirectoryScan):
                raise TypeError("Directory scanner returned an invalid result")
            await run.publish(
                "stage",
                "Parsing Records",
                f"Discovered {len(scan.gedcom_files)} GEDCOM files and {len(scan.document_files)} documents",
                payload={
                    "gedcom_count": len(scan.gedcom_files),
                    "document_count": len(scan.document_files),
                    "has_gedcom_baseline": bool(scan.gedcom_files),
                },
            )
            for error in scan.errors:
                await self._warning(run, error)

            index = await self._run_blocking(
                self.gedcom_parser,
                [item.path for item in scan.gedcom_files],
            )
            if not isinstance(index, GedcomIndex):
                raise TypeError("GEDCOM parser returned an invalid result")
            for error in index.errors:
                await self._warning(run, error)
            if index.individuals:
                await run.publish(
                    "file",
                    "Parsing Records",
                    f"GEDCOM baseline loaded: {len(index.individuals)} individuals found",
                    payload={"individual_count": len(index.individuals)},
                )
            else:
                await self._warning(run, "No parseable GEDCOM baseline was found; person groups are provisional.")

            documents = await self._extract_documents(run, scan)
            if index.individuals:
                await self._analyze_indexed_people(run, index, documents)
            else:
                await self._analyze_provisional_people(run, documents)
            await run.publish(
                "complete",
                "Finished",
                "Analysis pipeline completed",
                payload={"snapshot": run.snapshot().model_dump(mode="json")},
            )
        except asyncio.CancelledError:
            run.error = "Pipeline run was cancelled before completion"
            logger.warning(
                "Pipeline run %s for research root %s was cancelled",
                run.run_id,
                run.root,
                exc_info=True,
            )
            await run.publish("error", "Failed", run.error)
            raise
        except Exception as exc:
            logger.exception(
                "Pipeline run %s failed for research root %s with model %s",
                run.run_id,
                run.root,
                run.model,
            )
            run.error = str(exc)
            await run.publish("error", "Failed", f"Pipeline failed: {exc}")

    async def _warning(self, run: RunRecord, message: str, *, exc_info: bool = False) -> None:
        logger.warning("Pipeline run %s: %s", run.run_id, message, exc_info=exc_info)
        run.warnings.append(message)
        await run.publish("warning", "Warning", message)

    async def _extract_documents(
        self,
        run: RunRecord,
        scan: DirectoryScan,
    ) -> list[ResearchDocument]:
        cache = self.cache_factory(run.root, "treesleuth-docling-extraction-v1")
        documents: list[ResearchDocument] = []
        total = len(scan.document_files)
        for index, discovered in enumerate(scan.document_files, start=1):
            source_id = str(discovered.relative_path)
            await run.publish(
                "file",
                "Parsing Records",
                f"Extracting document {index} of {total}: {source_id}",
                source_path=str(discovered.path),
            )
            try:
                cached = await self._run_blocking_with_progress(
                    run,
                    f"document {index} of {total}: {source_id}",
                    str(discovered.path),
                    cache.get_or_extract,
                    discovered.path,
                    self.extractor.extract_text,
                )
                text = getattr(cached, "text", None)
                if not isinstance(text, str) or not text.strip():
                    raise DocumentExtractionError(f"No readable text was extracted from {discovered.path}")
                documents.append(ResearchDocument(id=source_id, path=discovered.path, text=text))
                logger.debug(
                    "Extracted source for pipeline run %s from %s: %s",
                    run.run_id,
                    discovered.path,
                    text,
                )
                for warning in cached.warnings:
                    await self._warning(run, warning)
                await run.publish(
                    "file",
                    "Parsing Records",
                    f"Extracted text from {source_id}",
                    source_path=str(discovered.path),
                    payload={"cache_hit": cached.cache_hit},
                )
            except (DocumentExtractionError, OSError) as exc:
                await self._warning(
                    run,
                    f"Document extraction failed for {discovered.path}: {exc}",
                    exc_info=True,
                )
        return documents

    async def _analyze_indexed_people(
        self,
        run: RunRecord,
        index: GedcomIndex,
        documents: list[ResearchDocument],
    ) -> None:
        associations = correlate_documents(documents, list(index.individuals.values()))
        documents_by_person: dict[str, list[ResearchDocument]] = {}
        docs_by_id = {document.id: document for document in documents}
        for association in associations:
            if association.status == "matched" and association.person_id:
                documents_by_person.setdefault(association.person_id, []).append(
                    docs_by_id[association.document_id]
                )
                await run.publish(
                    "file",
                    "Comparing with GEDCOM",
                    f"Correlated {association.document_id} to {association.person_id}",
                    person_id=association.person_id,
                    source_path=str(docs_by_id[association.document_id].path),
                    payload={"confidence": association.candidates[0].confidence},
                )
            elif association.status == "ambiguous":
                candidate_ids = [candidate.person_id for candidate in association.candidates]
                await self._warning(
                    run,
                    f"Could not confidently associate {association.document_id}; candidates: {', '.join(candidate_ids)}",
                )
            else:
                await self._warning(run, f"No GEDCOM individual matched {association.document_id}")

        for person in index.individuals.values():
            await self._analyze_person(
                run,
                person.id,
                person.name,
                person.birth_year,
                person.death_year,
                person,
                documents_by_person.get(person.id, []),
                None,
            )

    async def _analyze_provisional_people(
        self,
        run: RunRecord,
        documents: list[ResearchDocument],
    ) -> None:
        clusters = cluster_without_gedcom(documents)
        docs_by_id = {document.id: document for document in documents}
        for cluster in clusters:
            cluster_documents = [docs_by_id[document_id] for document_id in cluster.document_ids]
            await self._analyze_person(
                run,
                cluster.id,
                cluster.name,
                min(cluster.years) if cluster.years else None,
                max(cluster.years) if cluster.years else None,
                None,
                cluster_documents,
                cluster,
            )

    async def _analyze_person(
        self,
        run: RunRecord,
        person_id: str,
        name: str,
        birth_year: int | None,
        death_year: int | None,
        person: IndividualRecord | None,
        documents: list[ResearchDocument],
        cluster: ProvisionalCluster | None,
    ) -> None:
        progress = PersonRunResult(
            id=person_id,
            name=name,
            birth_year=birth_year,
            death_year=death_year,
            document_count=len(documents),
            status="Parsing Records",
        )
        run.people[person_id] = progress
        await self._publish_person(run, progress)
        logger.debug(
            "Analysis context for pipeline run %s, person %s (%s): GEDCOM=%r, provisional_cluster=%r, sources=%r",
            run.run_id,
            person_id,
            name,
            person,
            cluster,
            [(document.id, document.text) for document in documents],
        )
        try:
            progress.status = "Comparing with GEDCOM"
            await self._publish_person(run, progress)
            audit = await self.analyzer.audit(
                run.model,
                person,
                documents,
                cluster=cluster,
            )
            progress.status = "Writing Biography"
            await self._publish_person(run, progress)
            biography = await self.analyzer.biography(
                run.model,
                person,
                documents,
                cluster=cluster,
            )
            saved = await self._run_blocking(
                save_analysis_results,
                run.root,
                person_id,
                name,
                biography,
                audit,
            )
            if not isinstance(saved, SavedAnalysis):
                raise TypeError("Result writer returned an invalid result")
            progress.status = "Finished"
            progress.biography = biography.biography
            progress.biography_path = str(saved.biography_path)
            progress.conflicts = [finding.model_dump(mode="json") for finding in audit.findings]
            await self._publish_person(run, progress)
        except (ModelInferenceError, OllamaServiceError, OutputWriteError, OSError, ValueError) as exc:
            progress.status = "Failed"
            progress.error = str(exc)
            await self._publish_person(run, progress)
            await self._warning(
                run,
                f"Analysis failed for {name} ({person_id}): {exc}",
                exc_info=True,
            )

    async def _publish_person(self, run: RunRecord, progress: PersonRunResult) -> None:
        await run.publish(
            "person",
            progress.status,
            f"{progress.name}: {progress.status}",
            person_id=progress.id,
            payload=progress.model_dump(mode="json"),
        )

    async def shutdown(self) -> None:
        for run in self._runs.values():
            if run.task and not run.task.done():
                run.task.cancel()
        pending = [run.task for run in self._runs.values() if run.task]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._executor.shutdown(wait=True, cancel_futures=True)
