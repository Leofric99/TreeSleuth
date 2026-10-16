import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from treesleuth.gedcom import IndividualRecord

YEAR_PATTERN = re.compile(r"\b(?:1[0-9]{3}|20[0-9]{2})\b")
NAME_PATTERN = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b")
NAME_STOP_WORDS = frozenset({"the", "and", "from", "born", "married", "died"})


@dataclass(frozen=True)
class ResearchDocument:
    id: str
    path: Path
    text: str


@dataclass(frozen=True)
class PersonCandidate:
    person_id: str
    confidence: float
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class DocumentAssociation:
    document_id: str
    status: Literal["matched", "ambiguous", "unmatched"]
    person_id: str | None
    candidates: tuple[PersonCandidate, ...]


@dataclass(frozen=True)
class ProvisionalCluster:
    id: str
    name: str
    document_ids: tuple[str, ...]
    years: tuple[int, ...]
    status: Literal["inferred"]


def _normalized_words(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", value.casefold()))


def _word_occurs(words: tuple[str, ...], candidate: str) -> bool:
    candidate_words = _normalized_words(candidate)
    if not candidate_words or len(candidate_words) > len(words):
        return False
    width = len(candidate_words)
    return any(words[index : index + width] == candidate_words for index in range(len(words) - width + 1))


def _lifespan_evidence(person: IndividualRecord, years: set[int]) -> tuple[float, str | None]:
    if not years or person.birth_year is None and person.death_year is None:
        return 0.0, None
    start = person.birth_year if person.birth_year is not None else min(years)
    end = person.death_year if person.death_year is not None else max(years)
    if any(start <= year <= end for year in years):
        return 0.1, f"Document year overlaps recorded lifespan {start}-{end}"
    return 0.0, None


def _score_person(person: IndividualRecord, text: str) -> PersonCandidate | None:
    words = _normalized_words(text)
    name_words = _normalized_words(person.name)
    if not name_words:
        return None
    exact_name = _word_occurs(words, person.name)
    matched_parts = sum(_word_occurs(words, part) for part in (person.given_name, person.surname) if part)
    if not exact_name and matched_parts == 0:
        return None

    score = 0.88 if exact_name else 0.45
    evidence = ["Full GEDCOM name appears in document text"] if exact_name else []
    if not exact_name and matched_parts == 2:
        score = 0.82
        evidence.append("Given name and surname both appear in document text")
    elif not exact_name and matched_parts == 1:
        evidence.append("One GEDCOM name component appears in document text")

    years = {int(year) for year in YEAR_PATTERN.findall(text)}
    lifespan_score, lifespan_detail = _lifespan_evidence(person, years)
    score = min(0.99, score + lifespan_score)
    if lifespan_detail:
        evidence.append(lifespan_detail)
    return PersonCandidate(person_id=person.id, confidence=score, evidence=tuple(evidence))


def correlate_documents(
    documents: list[ResearchDocument],
    individuals: list[IndividualRecord],
) -> list[DocumentAssociation]:
    associations: list[DocumentAssociation] = []
    for document in documents:
        candidates = [
            candidate
            for person in individuals
            if (candidate := _score_person(person, document.text)) is not None
        ]
        candidates.sort(key=lambda candidate: (-candidate.confidence, candidate.person_id))
        if not candidates:
            associations.append(
                DocumentAssociation(document_id=document.id, status="unmatched", person_id=None, candidates=())
            )
            continue

        best = candidates[0]
        second_score = candidates[1].confidence if len(candidates) > 1 else 0.0
        if best.confidence >= 0.8 and (len(candidates) == 1 or best.confidence - second_score >= 0.12):
            associations.append(
                DocumentAssociation(
                    document_id=document.id,
                    status="matched",
                    person_id=best.person_id,
                    candidates=tuple(candidates),
                )
            )
        else:
            associations.append(
                DocumentAssociation(
                    document_id=document.id,
                    status="ambiguous",
                    person_id=None,
                    candidates=tuple(candidates),
                )
            )
    return associations


def _document_name_candidates(text: str) -> set[str]:
    names = set()
    for match in NAME_PATTERN.finditer(text):
        candidate = " ".join(match.group(1).split())
        words = _normalized_words(candidate)
        if words and words[0] not in NAME_STOP_WORDS:
            names.add(candidate)
    return names


def cluster_without_gedcom(documents: list[ResearchDocument]) -> list[ProvisionalCluster]:
    by_name: dict[str, tuple[str, list[tuple[ResearchDocument, set[int]]]]] = {}
    for document in documents:
        years = {int(year) for year in YEAR_PATTERN.findall(document.text)}
        for name in _document_name_candidates(document.text):
            key = " ".join(_normalized_words(name))
            if key not in by_name:
                by_name[key] = (name, [])
            by_name[key][1].append((document, years))

    clusters: list[ProvisionalCluster] = []
    for normalized_name, (display_name, entries) in by_name.items():
        groups: list[list[tuple[ResearchDocument, set[int]]]] = []
        for entry in sorted(entries, key=lambda item: item[0].id):
            years = entry[1]
            matching_groups = [
                group
                for group in groups
                if years
                and any(
                    other_years
                    and min(years) <= max(other_years)
                    and min(other_years) <= max(years)
                    for _, other_years in group
                )
            ]
            if matching_groups:
                target = matching_groups[0]
                target.append(entry)
                for other in matching_groups[1:]:
                    target.extend(other)
                    groups.remove(other)
            else:
                groups.append([entry])

        for group in groups:
            document_ids = tuple(sorted({document.id for document, _ in group}))
            group_years = tuple(sorted({year for _, years in group for year in years}))
            digest = hashlib.sha256(
                f"{normalized_name}|{','.join(document_ids)}".encode("utf-8")
            ).hexdigest()[:12]
            clusters.append(
                ProvisionalCluster(
                    id=f"provisional-{digest}",
                    name=display_name,
                    document_ids=document_ids,
                    years=group_years,
                    status="inferred",
                )
            )
    return sorted(clusters, key=lambda cluster: (cluster.name.casefold(), cluster.id))
