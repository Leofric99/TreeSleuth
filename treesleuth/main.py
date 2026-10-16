import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from treesleuth.analysis import OllamaServiceError
from treesleuth.discovery import scan_directory
from treesleuth.logging_config import configure_logging
from treesleuth.models import (
    DirectoryAnalyzeRequest,
    DirectoryAnalyzeResponse,
    PipelineStartRequest,
    PipelineStartResponse,
    RunSnapshot,
    SystemCheckResponse,
)
from treesleuth.paths import PathValidationError
from treesleuth.pipeline import (
    PipelineCapacityError,
    PipelineCoordinator,
    PipelineRunNotFoundError,
)

logger = logging.getLogger(__name__)


def create_app(coordinator: PipelineCoordinator | None = None) -> FastAPI:
    pipeline = coordinator or PipelineCoordinator()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        configure_logging()
        yield
        await pipeline.shutdown()

    app = FastAPI(title="TreeSleuth", version="0.1.0", lifespan=lifespan)
    app.state.pipeline = pipeline

    @app.get("/api/system-check", response_model=SystemCheckResponse)
    async def system_check() -> SystemCheckResponse:
        try:
            models = await pipeline.analyzer.available_models()
        except OllamaServiceError as exc:
            logger.warning("API system check failed querying local Ollama: %s", exc, exc_info=True)
            return SystemCheckResponse(ollama_available=False, error=str(exc))
        return SystemCheckResponse(ollama_available=True, models=models)

    @app.post("/api/analyze-directory", response_model=DirectoryAnalyzeResponse)
    async def analyze_directory(request: DirectoryAnalyzeRequest) -> DirectoryAnalyzeResponse:
        try:
            scan = await run_in_threadpool(scan_directory, request.path)
        except PathValidationError as exc:
            logger.warning("API directory preview rejected path %s: %s", request.path, exc, exc_info=True)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return DirectoryAnalyzeResponse(
            root=str(scan.root),
            gedcom_files=len(scan.gedcom_files),
            document_files=len(scan.document_files),
            files_by_type=scan.files_by_type,
            has_gedcom_baseline=bool(scan.gedcom_files),
        )

    @app.post("/api/run-pipeline", response_model=PipelineStartResponse, status_code=202)
    async def start_pipeline(request: PipelineStartRequest) -> PipelineStartResponse:
        try:
            run = await pipeline.start(request.path, request.model)
        except PathValidationError as exc:
            logger.warning("API pipeline start rejected path %s: %s", request.path, exc, exc_info=True)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PipelineCapacityError as exc:
            logger.warning("API pipeline start reached capacity for path %s: %s", request.path, exc, exc_info=True)
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except ValueError as exc:
            logger.warning(
                "API pipeline start rejected model %s for path %s: %s",
                request.model,
                request.path,
                exc,
                exc_info=True,
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return PipelineStartResponse(
            run_id=run.run_id,
            events_url=f"/api/runs/{run.run_id}/events",
        )

    @app.get("/api/runs/{run_id}", response_model=RunSnapshot)
    async def get_run(run_id: str) -> RunSnapshot:
        try:
            run = pipeline.get_run(run_id)
        except PipelineRunNotFoundError as exc:
            logger.warning("API run lookup failed for run %s: %s", run_id, exc, exc_info=True)
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return run.snapshot()

    @app.get("/api/runs/{run_id}/events")
    async def stream_run_events(
        run_id: str,
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        try:
            run = pipeline.get_run(run_id)
        except PipelineRunNotFoundError as exc:
            logger.warning("API event stream lookup failed for run %s: %s", run_id, exc, exc_info=True)
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        try:
            after_sequence = int(last_event_id) if last_event_id is not None else -1
        except ValueError as exc:
            logger.warning(
                "API event stream received invalid Last-Event-ID %r for run %s: %s",
                last_event_id,
                run_id,
                exc,
                exc_info=True,
            )
            raise HTTPException(status_code=400, detail="Last-Event-ID must be an integer") from exc
        if after_sequence < -1:
            logger.warning(
                "API event stream received negative Last-Event-ID %s for run %s",
                after_sequence,
                run_id,
            )
            raise HTTPException(status_code=400, detail="Last-Event-ID must be -1 or greater")

        async def events():
            async for event in pipeline.stream_events(run, after_sequence):
                yield (
                    f"id: {event.sequence}\n"
                    f"event: {event.event}\n"
                    f"data: {event.model_dump_json()}\n\n"
                )

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    static_directory = Path(__file__).resolve().parent.parent / "static"
    app.mount("/", StaticFiles(directory=static_directory, html=True), name="dashboard")
    return app


app = create_app()
