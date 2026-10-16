from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class SystemCheckResponse(BaseModel):
    ollama_available: bool
    models: list[str] = Field(default_factory=list)
    error: str | None = None


class DirectoryAnalyzeRequest(BaseModel):
    path: Path


class DirectoryAnalyzeResponse(BaseModel):
    root: str
    gedcom_files: int
    document_files: int
    files_by_type: dict[str, int]
    has_gedcom_baseline: bool


class PipelineStartRequest(BaseModel):
    path: Path
    model: str = Field(min_length=1)


class PipelineStartResponse(BaseModel):
    run_id: str
    events_url: str


PipelineEventKind = Literal["stage", "file", "person", "warning", "error", "complete"]
PipelineStatus = Literal["queued", "running", "completed", "failed"]


class PipelineEvent(BaseModel):
    run_id: str
    sequence: int = Field(ge=0)
    event: PipelineEventKind
    stage: str
    message: str
    person_id: str | None = None
    source_path: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)


class PersonRunResult(BaseModel):
    id: str
    name: str
    birth_year: int | None = None
    death_year: int | None = None
    document_count: int = Field(ge=0)
    status: Literal[
        "Idle",
        "Parsing Records",
        "Comparing with GEDCOM",
        "Writing Biography",
        "Finished",
        "Failed",
    ]
    error: str | None = None
    biography: str | None = None
    biography_path: str | None = None
    conflicts: list[dict[str, object]] = Field(default_factory=list)


class RunSnapshot(BaseModel):
    run_id: str
    status: PipelineStatus
    people: list[PersonRunResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
