from pathlib import Path

from treesleuth.entity_resolution import (
    ResearchDocument,
    cluster_without_gedcom,
    correlate_documents,
)
from treesleuth.gedcom import IndividualRecord


def person(record_id: str, name: str, given: str, surname: str, birth: int, death: int) -> IndividualRecord:
    return IndividualRecord(
        id=record_id,
        name=name,
        given_name=given,
        surname=surname,
        sex=None,
        birth_date=str(birth),
        birth_place=None,
        death_date=str(death),
        death_place=None,
        birth_year=birth,
        death_year=death,
        events=(),
        family_ids=(),
        source_file="family.ged",
    )


def test_document_matches_person_with_name_and_lifespan_evidence(tmp_path: Path) -> None:
    ada = person("I1", "Ada Lovelace", "Ada", "Lovelace", 1815, 1852)
    document = ResearchDocument("doc-1", tmp_path / "letter.txt", "Ada Lovelace visited London in 1843.")

    result = correlate_documents([document], [ada])[0]

    assert result.status == "matched"
    assert result.person_id == "I1"
    assert result.candidates[0].confidence >= 0.9
    assert any("lifespan" in evidence for evidence in result.candidates[0].evidence)


def test_duplicate_name_candidates_remain_ambiguous(tmp_path: Path) -> None:
    older = person("I1", "John Smith", "John", "Smith", 1750, 1810)
    younger = person("I2", "John Smith", "John", "Smith", 1850, 1910)
    document = ResearchDocument("doc-1", tmp_path / "record.txt", "John Smith attended a school in 1880.")

    result = correlate_documents([document], [older, younger])[0]

    assert result.status == "ambiguous"
    assert result.person_id is None
    assert {candidate.person_id for candidate in result.candidates} == {"I1", "I2"}


def test_no_matching_name_is_unmatched(tmp_path: Path) -> None:
    document = ResearchDocument("doc-1", tmp_path / "record.txt", "A local census document from 1880.")

    result = correlate_documents([document], [person("I1", "Ada Lovelace", "Ada", "Lovelace", 1815, 1852)])[0]

    assert result.status == "unmatched"
    assert result.person_id is None


def test_no_gedcom_clusters_matching_names_with_overlapping_years(tmp_path: Path) -> None:
    docs = [
        ResearchDocument("doc-1", tmp_path / "a.txt", "Ada Lovelace lived in London from 1830 to 1850."),
        ResearchDocument("doc-2", tmp_path / "b.txt", "A letter by Ada Lovelace dated 1842."),
    ]

    clusters = cluster_without_gedcom(docs)

    ada = next(cluster for cluster in clusters if cluster.name == "Ada Lovelace")
    assert ada.status == "inferred"
    assert ada.document_ids == ("doc-1", "doc-2")
    assert ada.years == (1830, 1842, 1850)


def test_no_gedcom_does_not_merge_non_overlapping_timelines(tmp_path: Path) -> None:
    docs = [
        ResearchDocument("doc-1", tmp_path / "a.txt", "John Smith record from 1750."),
        ResearchDocument("doc-2", tmp_path / "b.txt", "John Smith record from 1900."),
    ]

    clusters = cluster_without_gedcom(docs)

    john_clusters = [cluster for cluster in clusters if cluster.name == "John Smith"]
    assert len(john_clusters) == 2
    assert all(cluster.status == "inferred" for cluster in john_clusters)
