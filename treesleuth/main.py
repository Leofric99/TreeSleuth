import logging
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from treesleuth.discovery import scan_directory
from treesleuth.gedcom import parse_gedcom_files
from treesleuth.logging_config import configure_logging
from treesleuth.validator import GedcomValidator, ValidationIssue
from treesleuth.models import (
    GedcomValidationRequest,
    GedcomValidationResponse,
    ValidationIssueModel,
)
from treesleuth.paths import PathValidationError

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create FastAPI app for GEDCOM validation."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        configure_logging()
        yield

    app = FastAPI(title="TreeSleuth", version="0.1.0", lifespan=lifespan)

    @app.post("/api/validate-gedcom", response_model=GedcomValidationResponse)
    async def validate_gedcom(request: GedcomValidationRequest) -> GedcomValidationResponse:
        """Validate GEDCOM files in a directory for logical errors and inconsistencies."""
        try:
            scan = await run_in_threadpool(scan_directory, request.path)
        except PathValidationError as exc:
            logger.warning("API GEDCOM validation rejected path %s: %s", request.path, exc, exc_info=True)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        
        if not scan.gedcom_files:
            logger.info("API GEDCOM validation found no GEDCOM files in %s", request.path)
            return GedcomValidationResponse(
                gedcom_files=0,
                total_individuals=0,
                total_families=0,
                issues_found=0,
                errors=0,
                warnings=0,
                parse_errors=[],
            )
        
        # Parse GEDCOM files
        index = await run_in_threadpool(parse_gedcom_files, [f.path for f in scan.gedcom_files])
        
        # Run validation
        validator = GedcomValidator(index)
        issues: list[ValidationIssue] = validator.validate()
        
        # Convert to response models
        error_count = sum(1 for issue in issues if issue.severity == "error")
        warning_count = sum(1 for issue in issues if issue.severity == "warning")
        
        response_issues = [
            ValidationIssueModel(
                severity=issue.severity,
                category=issue.category,
                person_id=issue.person_id,
                person_name=issue.person_name,
                message=issue.message,
                details=issue.details,
            )
            for issue in issues
        ]
        
        return GedcomValidationResponse(
            gedcom_files=len(scan.gedcom_files),
            total_individuals=len(index.individuals),
            total_families=len(index.families),
            issues_found=len(issues),
            errors=error_count,
            warnings=warning_count,
            issues=response_issues,
            parse_errors=list(index.errors),
        )

    @app.post("/api/validate-gedcom-upload", response_model=GedcomValidationResponse)
    async def validate_gedcom_upload(file: UploadFile = File(...)) -> GedcomValidationResponse:
        """Validate an uploaded GEDCOM file for logical errors and inconsistencies."""
        if not file.filename or not file.filename.endswith(".ged"):
            raise HTTPException(status_code=400, detail="Only .ged files are accepted")
        
        try:
            # Save uploaded file to temporary directory
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir) / file.filename
                content = await file.read()
                temp_path.write_bytes(content)
                
                # Parse the GEDCOM file
                index = await run_in_threadpool(parse_gedcom_files, [temp_path])
                
                # Run validation
                validator = GedcomValidator(index)
                issues: list[ValidationIssue] = validator.validate()
                
                # Convert to response models
                error_count = sum(1 for issue in issues if issue.severity == "error")
                warning_count = sum(1 for issue in issues if issue.severity == "warning")
                
                response_issues = [
                    ValidationIssueModel(
                        severity=issue.severity,
                        category=issue.category,
                        person_id=issue.person_id,
                        person_name=issue.person_name,
                        message=issue.message,
                        details=issue.details,
                    )
                    for issue in issues
                ]
                
                return GedcomValidationResponse(
                    gedcom_files=1,
                    total_individuals=len(index.individuals),
                    total_families=len(index.families),
                    issues_found=len(issues),
                    errors=error_count,
                    warnings=warning_count,
                    issues=response_issues,
                    parse_errors=list(index.errors),
                )
        except Exception as exc:
            logger.exception("Error validating uploaded GEDCOM file %s", file.filename)
            raise HTTPException(status_code=500, detail=f"Validation failed: {str(exc)}") from exc

    static_directory = Path(__file__).resolve().parent.parent / "static"
    app.mount("/", StaticFiles(directory=static_directory, html=True), name="dashboard")
    return app


app = create_app()
