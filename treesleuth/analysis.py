import ipaddress
import json
import logging
from collections.abc import Callable, Mapping
from typing import Literal, Protocol
from urllib.parse import urlsplit

import httpx
from ollama import AsyncClient, ResponseError
from pydantic import BaseModel, Field, ValidationError

from treesleuth.config import Settings, get_settings
from treesleuth.entity_resolution import ProvisionalCluster, ResearchDocument
from treesleuth.gedcom import IndividualRecord

logger = logging.getLogger(__name__)


class OllamaServiceError(RuntimeError):
    """Raised when the selected local Ollama service is unavailable."""


class ModelInferenceError(RuntimeError):
    """Raised when the model response is missing, malformed, or incomplete."""


class AuditFinding(BaseModel):
    outcome: Literal["conflict", "uncertain"]
    person_id: str | None
    source_document_id: str
    source_claim: str = Field(min_length=1)
    baseline_source_id: str | None = None
    baseline_claim: str | None = None
    explanation: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class AuditResponse(BaseModel):
    findings: list[AuditFinding]


class BiographyClaim(BaseModel):
    claim: str = Field(min_length=1)
    source_ids: list[str]
    inferred: bool


class BiographyResponse(BaseModel):
    biography: str = Field(min_length=1)
    claims: list[BiographyClaim] = Field(min_length=1)


class OllamaClient(Protocol):
    async def list(self) -> object: ...

    async def chat(self, **kwargs: object) -> object: ...


ClientFactory = Callable[..., OllamaClient]


def _is_loopback_host(host: str) -> bool:
    hostname = urlsplit(host).hostname
    if hostname is None:
        return False
    if hostname.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _year_display(value: int | None) -> str:
    return str(value) if value is not None else "unknown"


def _individual_context(person: IndividualRecord | None) -> tuple[str, list[str]]:
    if person is None:
        return "No GEDCOM person is available; treat identity and events as provisional.", []
    baseline_ids: list[str] = []
    if person.birth_date or person.birth_place:
        baseline_ids.append(f"gedcom:{person.id}:birth")
    if person.death_date or person.death_place:
        baseline_ids.append(f"gedcom:{person.id}:death")
    events = [
        {
            "source_id": f"gedcom:{person.id}:event:{index}",
            "tag": event.tag,
            "date": event.date,
            "place": event.place,
            "value": event.value,
        }
        for index, event in enumerate(person.events)
    ]
    baseline_ids.extend(event["source_id"] for event in events)
    context = {
        "id": person.id,
        "name": person.name,
        "birth_date": person.birth_date,
        "birth_place": person.birth_place,
        "death_date": person.death_date,
        "death_place": person.death_place,
        "birth_year": person.birth_year,
        "death_year": person.death_year,
        "events": events,
        "baseline_source_ids": baseline_ids,
    }
    return json.dumps(context, ensure_ascii=False), baseline_ids


class OllamaAnalyzer:
    def __init__(
        self,
        settings: Settings | None = None,
        client_factory: ClientFactory = AsyncClient,
    ) -> None:
        self.settings = settings or get_settings()
        if not _is_loopback_host(self.settings.ollama_host):
            raise ValueError("Ollama host must resolve to localhost or a loopback address")
        self._client_factory = client_factory

    def _client(self) -> OllamaClient:
        return self._client_factory(
            host=self.settings.ollama_host,
            timeout=self.settings.ollama_timeout_seconds,
        )

    async def available_models(self) -> list[str]:
        try:
            response = await self._client().list()
        except (httpx.HTTPError, ResponseError, TimeoutError, OSError) as exc:
            raise OllamaServiceError(f"Could not query local Ollama: {exc}") from exc
        models = getattr(response, "models", None)
        if not isinstance(models, list):
            raise OllamaServiceError("Local Ollama returned an invalid model list")
        names = [getattr(model, "model", None) for model in models]
        if any(not isinstance(name, str) or not name for name in names):
            raise OllamaServiceError("Local Ollama returned a model without a name")
        return sorted(names)

    async def _structured_chat(
        self,
        model: str,
        system_prompt: str,
        user_payload: Mapping[str, object],
        response_type: type[BaseModel],
    ) -> BaseModel:
        if not model.strip():
            raise ModelInferenceError("A local Ollama model must be selected")
        client = self._client()
        try:
            response = await client.chat(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
                format=response_type.model_json_schema(),
                stream=False,
            )
        except (httpx.HTTPError, ResponseError, TimeoutError, OSError) as exc:
            raise OllamaServiceError(f"Local Ollama inference failed for model {model}: {exc}") from exc

        message = getattr(response, "message", None)
        content = getattr(message, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise ModelInferenceError("Local Ollama returned an empty response")
        try:
            return response_type.model_validate_json(content)
        except ValidationError as exc:
            raise ModelInferenceError(f"Local Ollama returned an invalid structured response: {exc}") from exc

    async def audit(
        self,
        model: str,
        person: IndividualRecord | None,
        documents: list[ResearchDocument],
        cluster: ProvisionalCluster | None = None,
    ) -> AuditResponse:
        person_context, baseline_ids = _individual_context(person)
        valid_source_ids = {document.id for document in documents}
        valid_baseline_ids = set(baseline_ids)
        if cluster:
            person_context = json.dumps(
                {
                    "provisional_person": cluster.name,
                    "cluster_id": cluster.id,
                    "years": cluster.years,
                    "status": cluster.status,
                },
                ensure_ascii=False,
            )

        response = await self._structured_chat(
            model=model,
            system_prompt=(
                "Audit genealogical source claims against the provided GEDCOM facts. "
                "Return only the requested JSON. Report a conflict only when the evidence "
                "supports a material contradiction; use uncertain when identity or evidence "
                "is insufficient. Cite only provided source_document_id and baseline_source_id "
                "values. Never invent facts or citations."
            ),
            user_payload={
                "person": person_context,
                "documents": [{"id": document.id, "text": document.text} for document in documents],
                "baseline_source_ids": baseline_ids,
            },
            response_type=AuditResponse,
        )
        assert isinstance(response, AuditResponse)
        for finding in response.findings:
            if finding.source_document_id not in valid_source_ids:
                raise ModelInferenceError(
                    f"Audit response cited unknown document id: {finding.source_document_id}"
                )
            if finding.baseline_source_id and finding.baseline_source_id not in valid_baseline_ids:
                raise ModelInferenceError(
                    f"Audit response cited unknown baseline id: {finding.baseline_source_id}"
                )
            if person and finding.person_id not in {None, person.id}:
                raise ModelInferenceError(f"Audit response cited an unknown person id: {finding.person_id}")
        return response

    async def biography(
        self,
        model: str,
        person: IndividualRecord | None,
        documents: list[ResearchDocument],
        cluster: ProvisionalCluster | None = None,
    ) -> BiographyResponse:
        person_context, baseline_ids = _individual_context(person)
        allowed_sources = {document.id for document in documents} | set(baseline_ids)
        if cluster:
            person_context = json.dumps(
                {
                    "provisional_person": cluster.name,
                    "cluster_id": cluster.id,
                    "years": cluster.years,
                    "status": cluster.status,
                },
                ensure_ascii=False,
            )
        if not documents and not baseline_ids:
            raise ModelInferenceError("There is insufficient evidence to generate a biography")

        response = await self._structured_chat(
            model=model,
            system_prompt=(
                "Write a chronological, evidence-grounded life story. Return JSON with a non-empty "
                "biography and claim citations. Each claim must cite provided source ids, unless it "
                "is explicitly marked inferred. Identify provisional details as uncertain, do not "
                "invent events, and cite only the provided ids."
            ),
            user_payload={
                "person": person_context,
                "documents": [{"id": document.id, "text": document.text} for document in documents],
                "baseline_source_ids": baseline_ids,
            },
            response_type=BiographyResponse,
        )
        assert isinstance(response, BiographyResponse)
        for claim in response.claims:
            if not claim.inferred and not claim.source_ids:
                raise ModelInferenceError("A sourced biography claim must include at least one source id")
            unknown_sources = set(claim.source_ids) - allowed_sources
            if unknown_sources:
                raise ModelInferenceError(
                    f"Biography response cited unknown source ids: {', '.join(sorted(unknown_sources))}"
                )
        return response
