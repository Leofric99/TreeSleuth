import json
from pathlib import Path

from fastapi.testclient import TestClient

from treesleuth.analysis import AuditResponse, BiographyResponse
from treesleuth.config import Settings
from treesleuth.main import create_app
from treesleuth.pipeline import PipelineCoordinator
from treesleuth.logging_config import configure_logging
import treesleuth.main as main_module


GEDCOM = """0 HEAD
1 SOUR end-to-end
1 GEDC
2 VERS 5.5
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Ada /Lovelace/
1 BIRT
2 DATE 10 DEC 1815
2 PLAC London, England
1 DEAT
2 DATE 27 NOV 1852
2 PLAC London, England
0 TRLR
"""


class CountingExtractor:
    def __init__(self) -> None:
        self.calls: list[Path] = []

    def extract_text(self, source: Path) -> str:
        self.calls.append(source)
        return source.read_text(encoding="utf-8")


class FixtureAnalyzer:
    async def available_models(self) -> list[str]:
        return ["fixture-model"]

    async def audit(self, _model, person, documents, cluster=None) -> AuditResponse:
        assert person is not None
        assert documents
        return AuditResponse(
            findings=[
                {
                    "outcome": "conflict",
                    "person_id": person.id,
                    "source_document_id": documents[0].id,
                    "source_claim": "The census lists Ada in 1860.",
                    "baseline_source_id": f"gedcom:{person.id}:death",
                    "baseline_claim": "GEDCOM records a death in 1852.",
                    "explanation": "The census date is later than the recorded death.",
                    "confidence": 0.94,
                }
            ]
        )

    async def biography(self, _model, person, documents, cluster=None) -> BiographyResponse:
        assert person is not None
        return BiographyResponse(
            biography="Ada Lovelace was born in London in 1815. A later source lists an 1860 census.",
            claims=[
                {
                    "claim": "Ada Lovelace was born in London in 1815.",
                    "source_ids": [f"gedcom:{person.id}:birth"],
                    "inferred": False,
                },
                {
                    "claim": "A source mentions an 1860 census.",
                    "source_ids": [documents[0].id],
                    "inferred": False,
                },
            ],
        )


def test_full_local_pipeline_reuses_cache_and_saves_auditable_results(
    tmp_path: Path,
    monkeypatch,
) -> None:
    log_path = configure_logging(tmp_path / "logs")
    monkeypatch.setattr(main_module, "configure_logging", lambda: configure_logging(log_path.parent))
    research_root = tmp_path / "research"
    (research_root / "genealogy").mkdir(parents=True)
    (research_root / "scans" / "census").mkdir(parents=True)
    (research_root / "genealogy" / "family.ged").write_text(GEDCOM, encoding="utf-8")
    source = research_root / "scans" / "census" / "entry.txt"
    source.write_text("Ada Lovelace is listed in the census in 1860.", encoding="utf-8")
    extractor = CountingExtractor()
    coordinator = PipelineCoordinator(
        settings=Settings(max_workers=1, max_active_runs=1),
        extractor=extractor,
        analyzer=FixtureAnalyzer(),
    )

    with TestClient(create_app(coordinator)) as client:
        for expected_cache_hit in (False, True):
            start = client.post(
                "/api/run-pipeline",
                json={"path": str(research_root), "model": "fixture-model"},
            )
            assert start.status_code == 202
            run_id = start.json()["run_id"]
            with client.stream("GET", start.json()["events_url"]) as stream:
                event_stream = "".join(stream.iter_text())
            snapshot = client.get(f"/api/runs/{run_id}").json()

            assert snapshot["status"] == "completed"
            assert len(snapshot["people"]) == 1
            person = snapshot["people"][0]
            assert person["name"] == "Ada Lovelace"
            assert person["status"] == "Finished"
            assert person["document_count"] == 1
            assert person["conflicts"][0]["source_document_id"] == str(Path("scans") / "census" / "entry.txt")
            assert "event: person" in event_stream
            assert "event: complete" in event_stream
            assert f'"cache_hit":{str(expected_cache_hit).lower()}' in event_stream

            biography_path = Path(person["biography_path"])
            assert biography_path.is_file()
            assert "Ada Lovelace was born" in biography_path.read_text(encoding="utf-8")
            conflict_files = list((research_root / "output").glob("*_Conflicts.json"))
            conflict_data = json.loads(conflict_files[0].read_text(encoding="utf-8"))
            assert conflict_data["findings"][0]["source_claim"] == "The census lists Ada in 1860."
            assert "1852" in conflict_data["findings"][0]["baseline_claim"]

    assert extractor.calls == [source]
    assert "Ada Lovelace is listed in the census in 1860." in log_path.read_text(encoding="utf-8")
