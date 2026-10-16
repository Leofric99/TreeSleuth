import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from treesleuth.analysis import (
    BiographyResponse,
    ModelInferenceError,
    OllamaAnalyzer,
    OllamaServiceError,
)
from treesleuth.config import Settings
from treesleuth.entity_resolution import ResearchDocument
from treesleuth.gedcom import IndividualRecord


class FakeOllamaClient:
    def __init__(self, responses: list[str] | None = None, error: Exception | None = None) -> None:
        self.responses = list(responses or [])
        self.error = error
        self.chat_requests: list[dict[str, object]] = []

    async def list(self) -> SimpleNamespace:
        if self.error:
            raise self.error
        return SimpleNamespace(models=[SimpleNamespace(model="qwen2.5:14b")])

    async def chat(self, **kwargs: object) -> SimpleNamespace:
        self.chat_requests.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(message=SimpleNamespace(content=self.responses.pop(0)))


def person() -> IndividualRecord:
    return IndividualRecord(
        id="tree#@I1@",
        name="Ada Lovelace",
        given_name="Ada",
        surname="Lovelace",
        sex="F",
        birth_date="10 DEC 1815",
        birth_place="London",
        death_date="27 NOV 1852",
        death_place="London",
        birth_year=1815,
        death_year=1852,
        events=(),
        family_ids=(),
        source_file="family.ged",
    )


def analyzer(client: FakeOllamaClient) -> OllamaAnalyzer:
    return OllamaAnalyzer(client_factory=lambda **_kwargs: client)


@pytest.mark.asyncio
async def test_local_model_inventory_and_structured_analysis(tmp_path: Path) -> None:
    audit = {
        "findings": [
            {
                "outcome": "conflict",
                "person_id": "tree#@I1@",
                "source_document_id": "doc-1",
                "source_claim": "The record states the person lived in 1860.",
                "baseline_source_id": "gedcom:tree#@I1@:death",
                "baseline_claim": "Recorded death was 27 NOV 1852.",
                "explanation": "The record is dated after the recorded death.",
                "confidence": 0.92,
            }
        ]
    }
    biography = {
        "biography": "Ada Lovelace was born in London in 1815.",
        "claims": [
            {
                "claim": "Ada Lovelace was born in London in 1815.",
                "source_ids": ["gedcom:tree#@I1@:birth", "doc-1"],
                "inferred": False,
            }
        ],
    }
    client = FakeOllamaClient([json.dumps(audit), json.dumps(biography)])
    document = ResearchDocument("doc-1", tmp_path / "record.txt", "Ada Lovelace record")
    service = analyzer(client)

    assert await service.available_models() == ["qwen2.5:14b"]
    audit_result = await service.audit("qwen2.5:14b", person(), [document])
    biography_result = await service.biography("qwen2.5:14b", person(), [document])

    assert audit_result.findings[0].outcome == "conflict"
    assert isinstance(biography_result, BiographyResponse)
    assert client.chat_requests[0]["format"] == type(audit_result).model_json_schema()
    assert client.chat_requests[1]["format"] == BiographyResponse.model_json_schema()


@pytest.mark.asyncio
async def test_invalid_or_incomplete_model_response_is_rejected(tmp_path: Path) -> None:
    client = FakeOllamaClient(['{"biography":"","claims":[]}'])
    service = analyzer(client)
    document = ResearchDocument("doc-1", tmp_path / "record.txt", "Ada Lovelace")

    with pytest.raises(ModelInferenceError, match="invalid structured response"):
        await service.biography("qwen2.5:14b", person(), [document])


@pytest.mark.asyncio
async def test_biography_without_cited_claims_is_incomplete(tmp_path: Path) -> None:
    client = FakeOllamaClient([json.dumps({"biography": "An unsupported story.", "claims": []})])
    service = analyzer(client)
    document = ResearchDocument("doc-1", tmp_path / "record.txt", "Ada Lovelace")

    with pytest.raises(ModelInferenceError, match="invalid structured response"):
        await service.biography("qwen2.5:14b", person(), [document])


@pytest.mark.asyncio
async def test_unknown_model_citations_are_rejected(tmp_path: Path) -> None:
    response = {
        "biography": "A sourced story.",
        "claims": [{"claim": "Unsupported", "source_ids": ["unknown"], "inferred": False}],
    }
    service = analyzer(FakeOllamaClient([json.dumps(response)]))
    document = ResearchDocument("doc-1", tmp_path / "record.txt", "Ada Lovelace")

    with pytest.raises(ModelInferenceError, match="unknown source ids"):
        await service.biography("qwen2.5:14b", person(), [document])


@pytest.mark.asyncio
async def test_ollama_connection_failure_is_reported() -> None:
    service = analyzer(FakeOllamaClient(error=httpx.ConnectError("offline")))

    with pytest.raises(OllamaServiceError, match="Could not query local Ollama"):
        await service.available_models()


def test_analyzer_rejects_nonlocal_ollama_host() -> None:
    with pytest.raises(ValueError, match="loopback"):
        OllamaAnalyzer(settings=Settings(ollama_host="https://example.com"))


@pytest.mark.asyncio
async def test_biography_without_evidence_is_not_generated() -> None:
    service = analyzer(FakeOllamaClient())

    with pytest.raises(ModelInferenceError, match="insufficient evidence"):
        await service.biography("qwen2.5:14b", person=None, documents=[])
