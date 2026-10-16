from pathlib import Path

from treesleuth.gedcom import parse_gedcom_files


GEDCOM_FIXTURE = """0 HEAD
1 SOUR TreeSleuth
1 GEDC
2 VERS 5.5
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Ada /Lovelace/
1 SEX F
1 BIRT
2 DATE 10 DEC 1815
2 PLAC London, England
1 DEAT
2 DATE 27 NOV 1852
1 FAMS @F1@
0 @I2@ INDI
1 NAME William /King/
1 SEX M
1 FAMS @F1@
0 @I3@ INDI
1 NAME Anne /King/
1 FAMC @F1@
0 @F1@ FAM
1 HUSB @I2@
1 WIFE @I1@
1 CHIL @I3@
1 MARR
2 DATE 8 JUL 1835
2 PLAC London, England
0 TRLR
"""


def test_parse_gedcom_preserves_people_families_events_and_relationships(tmp_path: Path) -> None:
    gedcom = tmp_path / "family.ged"
    gedcom.write_text(GEDCOM_FIXTURE, encoding="utf-8")

    result = parse_gedcom_files([gedcom])

    ada = next(person for person in result.individuals.values() if person.name == "Ada Lovelace")
    family = next(iter(result.families.values()))
    assert ada.birth_date == "10 DEC 1815"
    assert ada.birth_place == "London, England"
    assert ada.birth_year == 1815
    assert ada.death_year == 1852
    assert family.wife_id == ada.id
    assert family.husband_id in result.individuals
    assert family.child_ids[0] in result.individuals
    assert family.events[0].date == "8 JUL 1835"
    assert ada.id.endswith("#@I1@")


def test_malformed_gedcom_does_not_discard_valid_tree(tmp_path: Path) -> None:
    valid = tmp_path / "valid.ged"
    malformed = tmp_path / "malformed.ged"
    valid.write_text(GEDCOM_FIXTURE, encoding="utf-8")
    malformed.write_text("This is not a GEDCOM record\n", encoding="utf-8")

    result = parse_gedcom_files([malformed, valid])

    assert len(result.individuals) == 3
    assert len(result.families) == 1
    assert len(result.source_files) == 1
    assert len(result.errors) == 1
    assert "malformed.ged" in result.errors[0]
