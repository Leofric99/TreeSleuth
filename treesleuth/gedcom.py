from dataclasses import dataclass
import logging
from pathlib import Path

from gedcom.element.family import FamilyElement
from gedcom.element.individual import IndividualElement
from gedcom.parser import GedcomFormatViolationError, Parser

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GenealogyEvent:
    tag: str
    date: str | None
    place: str | None
    value: str | None


@dataclass(frozen=True)
class IndividualRecord:
    id: str
    name: str
    given_name: str
    surname: str
    sex: str | None
    birth_date: str | None
    birth_place: str | None
    death_date: str | None
    death_place: str | None
    birth_year: int | None
    death_year: int | None
    events: tuple[GenealogyEvent, ...]
    family_ids: tuple[str, ...]
    source_file: str


@dataclass(frozen=True)
class FamilyRecord:
    id: str
    husband_id: str | None
    wife_id: str | None
    child_ids: tuple[str, ...]
    events: tuple[GenealogyEvent, ...]
    source_file: str


@dataclass(frozen=True)
class GedcomIndex:
    individuals: dict[str, IndividualRecord]
    families: dict[str, FamilyRecord]
    source_files: tuple[str, ...]
    errors: tuple[str, ...]


EVENT_TAGS = frozenset(
    {
        "BAPM",
        "BARM",
        "BURI",
        "CENS",
        "CHR",
        "CONF",
        "CREM",
        "DEAT",
        "EDUC",
        "EMIG",
        "EVEN",
        "IMMI",
        "MARR",
        "NATU",
        "OCCU",
        "RESI",
        "WILL",
        "BIRT",
    }
)


def _child_value(element: object, tag: str) -> str | None:
    for child in element.get_child_elements():
        if child.get_tag() == tag and child.get_value():
            return child.get_value()
    return None


def _event_from_element(element: object) -> GenealogyEvent:
    return GenealogyEvent(
        tag=element.get_tag(),
        date=_child_value(element, "DATE"),
        place=_child_value(element, "PLAC"),
        value=element.get_value() or None,
    )


def _record_events(element: object) -> tuple[GenealogyEvent, ...]:
    return tuple(
        _event_from_element(child)
        for child in element.get_child_elements()
        if child.get_tag() in EVENT_TAGS
    )


def _year(date_value: str | None) -> int | None:
    if not date_value:
        return None
    for part in reversed(date_value.split()):
        if len(part) == 4 and part.isdecimal():
            return int(part)
    return None


def _names(element: IndividualElement) -> tuple[str, str, str]:
    given_name, surname = element.get_name()
    name = " ".join(part for part in (given_name.strip(), surname.strip()) if part)
    if not name:
        name = element.get_pointer() or "Unknown individual"
    return name, given_name.strip(), surname.strip()


def _person_id(tree_id: str, pointer: str) -> str:
    return f"{tree_id}#{pointer}"


def parse_gedcom_file(path: Path) -> tuple[dict[str, IndividualRecord], dict[str, FamilyRecord]]:
    parser = Parser()
    parser.parse_file(str(path), strict=True)
    tree_id = path.resolve().as_uri()
    source_file = str(path.resolve())
    records = parser.get_root_child_elements()
    individuals: dict[str, IndividualRecord] = {}
    families: dict[str, FamilyRecord] = {}

    for element in records:
        pointer = element.get_pointer()
        if not pointer:
            continue
        if isinstance(element, IndividualElement):
            name, given_name, surname = _names(element)
            birth_date, birth_place, _ = element.get_birth_data()
            death_date, death_place, _ = element.get_death_data()
            family_ids = tuple(
                f"{tree_id}#{child.get_value()}"
                for child in element.get_child_elements()
                if child.get_tag() in {"FAMS", "FAMC"} and child.get_value()
            )
            individuals[_person_id(tree_id, pointer)] = IndividualRecord(
                id=_person_id(tree_id, pointer),
                name=name,
                given_name=given_name,
                surname=surname,
                sex=element.get_gender() or None,
                birth_date=birth_date or None,
                birth_place=birth_place or None,
                death_date=death_date or None,
                death_place=death_place or None,
                birth_year=_year(birth_date),
                death_year=_year(death_date),
                events=_record_events(element),
                family_ids=family_ids,
                source_file=source_file,
            )
        elif isinstance(element, FamilyElement):
            family_id = f"{tree_id}#{pointer}"
            spouses: dict[str, str] = {}
            children: list[str] = []
            for child in element.get_child_elements():
                tag = child.get_tag()
                value = child.get_value()
                if not value:
                    continue
                if tag in {"HUSB", "WIFE"}:
                    spouses[tag] = _person_id(tree_id, value)
                elif tag == "CHIL":
                    children.append(_person_id(tree_id, value))
            families[family_id] = FamilyRecord(
                id=family_id,
                husband_id=spouses.get("HUSB"),
                wife_id=spouses.get("WIFE"),
                child_ids=tuple(children),
                events=_record_events(element),
                source_file=source_file,
            )
    return individuals, families


def parse_gedcom_files(paths: list[Path]) -> GedcomIndex:
    individuals: dict[str, IndividualRecord] = {}
    families: dict[str, FamilyRecord] = {}
    source_files: list[str] = []
    errors: list[str] = []

    for path in paths:
        try:
            parsed_individuals, parsed_families = parse_gedcom_file(path)
        except (OSError, UnicodeDecodeError, GedcomFormatViolationError, ValueError) as exc:
            logger.exception("Could not parse GEDCOM file %s", path)
            errors.append(f"{path}: GEDCOM parse failed: {exc}")
            continue
        individuals.update(parsed_individuals)
        families.update(parsed_families)
        source_files.append(str(path.resolve()))

    return GedcomIndex(
        individuals=individuals,
        families=families,
        source_files=tuple(source_files),
        errors=tuple(errors),
    )
