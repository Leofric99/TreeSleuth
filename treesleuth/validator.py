"""GEDCOM data validation for timeline mistakes and logical errors."""

import logging
from dataclasses import dataclass
from typing import Callable

from treesleuth.gedcom import GedcomIndex, IndividualRecord, FamilyRecord, GenealogyEvent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValidationIssue:
    """A data quality issue found during validation."""
    severity: str  # "error", "warning", "info"
    category: str  # e.g., "anachronism", "time_travel", "lifespan", "marriage", "location"
    person_id: str
    person_name: str
    message: str
    details: dict[str, object] | None = None


class GedcomValidator:
    """Validates GEDCOM data for logical inconsistencies and timeline errors."""

    # Age constraints (based on historical records and biological reality)
    MIN_REPRODUCTION_AGE = 15  # Historically, <15 is extremely rare
    MAX_REPRODUCTION_AGE = 50  # Biologically and historically implausible after 50
    MAX_LIFESPAN = 110         # Maximum reasonable human lifespan
    GESTATION_MONTHS = 9       # Allow 9 months after father's death for conception

    def __init__(self, index: GedcomIndex):
        """Initialize validator with parsed GEDCOM index."""
        self.index = index
        self.issues: list[ValidationIssue] = []

    def validate(self, on_issue: Callable[[ValidationIssue], None] | None = None) -> list[ValidationIssue]:
        """
        Run all validation checks on the GEDCOM data.
        
        Args:
            on_issue: Optional callback invoked for each issue found
            
        Returns:
            List of all validation issues found
        """
        self.issues = []
        for person in self.index.individuals.values():
            self._validate_person(person, on_issue)
        for family in self.index.families.values():
            self._validate_family(family, on_issue)
        return self.issues

    def _validate_person(self, person: IndividualRecord, callback: Callable[[ValidationIssue], None] | None) -> None:
        """Validate a single individual record."""
        # Check lifespan errors
        self._check_lifespan(person, callback)
        
        # Check birth/death relationships with parents
        self._check_parent_relationships(person, callback)
        
        # Check reproduction age constraints
        self._check_reproduction_age(person, callback)

    def _validate_family(self, family: FamilyRecord, callback: Callable[[ValidationIssue], None] | None) -> None:
        """Validate a family unit."""
        # Check marriage timing relative to birth/death
        self._check_marriage_timing(family, callback)
        
        # Check children born after parent death
        self._check_child_viability(family, callback)

    def _check_lifespan(self, person: IndividualRecord, callback: Callable[[ValidationIssue], None] | None) -> None:
        """Check for invalid lifespans (death before birth, >110 years)."""
        if not person.birth_year or not person.death_year:
            return
        
        # Check: death before birth
        if person.death_year < person.birth_year:
            issue = ValidationIssue(
                severity="error",
                category="lifespan",
                person_id=person.id,
                person_name=person.name,
                message=f"Death year ({person.death_year}) is before birth year ({person.birth_year})",
                details={"birth_year": person.birth_year, "death_year": person.death_year},
            )
            self._add_issue(issue, callback)
        
        # Check: unusually long lifespan
        lifespan = person.death_year - person.birth_year
        if lifespan > self.MAX_LIFESPAN:
            issue = ValidationIssue(
                severity="warning",
                category="lifespan",
                person_id=person.id,
                person_name=person.name,
                message=f"Reported lifespan of {lifespan} years exceeds maximum expected ({self.MAX_LIFESPAN})",
                details={"birth_year": person.birth_year, "death_year": person.death_year, "lifespan": lifespan},
            )
            self._add_issue(issue, callback)

    def _check_parent_relationships(self, person: IndividualRecord, callback: Callable[[ValidationIssue], None] | None) -> None:
        """Check birth/death constraints with parents."""
        # Find family where this person is a child
        child_families = [
            self.index.families[fam_id]
            for fam_id in person.family_ids
            if fam_id in self.index.families and person.id in self.index.families[fam_id].child_ids
        ]
        
        if not child_families:
            return
        
        for family in child_families:
            # Check birth before parents' deaths
            if person.birth_year:
                if family.husband_id and family.husband_id in self.index.individuals:
                    father = self.index.individuals[family.husband_id]
                    if father.death_year and person.birth_year > father.death_year + self.GESTATION_MONTHS:
                        issue = ValidationIssue(
                            severity="error",
                            category="time_travel",
                            person_id=person.id,
                            person_name=person.name,
                            message=f"Birth year {person.birth_year} is {person.birth_year - father.death_year} years after father's death ({father.death_year})",
                            details={
                                "child_name": person.name,
                                "father_name": father.name,
                                "child_birth_year": person.birth_year,
                                "father_death_year": father.death_year,
                            },
                        )
                        self._add_issue(issue, callback)
                
                if family.wife_id and family.wife_id in self.index.individuals:
                    mother = self.index.individuals[family.wife_id]
                    if mother.death_year and person.birth_year > mother.death_year:
                        issue = ValidationIssue(
                            severity="error",
                            category="time_travel",
                            person_id=person.id,
                            person_name=person.name,
                            message=f"Birth year {person.birth_year} is after mother's death ({mother.death_year})",
                            details={
                                "child_name": person.name,
                                "mother_name": mother.name,
                                "child_birth_year": person.birth_year,
                                "mother_death_year": mother.death_year,
                            },
                        )
                        self._add_issue(issue, callback)

    def _check_reproduction_age(self, person: IndividualRecord, callback: Callable[[ValidationIssue], None] | None) -> None:
        """Check for biologically implausible birth/pregnancy ages."""
        if not person.birth_year:
            return
        
        # Find families where this person is a parent
        parent_families = [
            self.index.families[fam_id]
            for fam_id in person.family_ids
            if fam_id in self.index.families and (
                person.id == self.index.families[fam_id].husband_id or
                person.id == self.index.families[fam_id].wife_id
            )
        ]
        
        for family in parent_families:
            for child_id in family.child_ids:
                if child_id not in self.index.individuals:
                    continue
                child = self.index.individuals[child_id]
                if not child.birth_year:
                    continue
                
                age_at_birth = child.birth_year - person.birth_year
                
                # Check minimum reproductive age
                if age_at_birth < self.MIN_REPRODUCTION_AGE:
                    issue = ValidationIssue(
                        severity="error",
                        category="anachronism",
                        person_id=person.id,
                        person_name=person.name,
                        message=f"Birth of {child.name} ({child.birth_year}) when {person.name} was only {age_at_birth} years old",
                        details={
                            "parent_name": person.name,
                            "parent_birth_year": person.birth_year,
                            "child_name": child.name,
                            "child_birth_year": child.birth_year,
                            "parent_age": age_at_birth,
                        },
                    )
                    self._add_issue(issue, callback)
                
                # Check maximum reproductive age (only for mothers - women)
                if person.sex == "F" and age_at_birth > self.MAX_REPRODUCTION_AGE:
                    issue = ValidationIssue(
                        severity="warning",
                        category="anachronism",
                        person_id=person.id,
                        person_name=person.name,
                        message=f"Birth of {child.name} ({child.birth_year}) when {person.name} was {age_at_birth} years old (unusual for historical records)",
                        details={
                            "parent_name": person.name,
                            "parent_birth_year": person.birth_year,
                            "child_name": child.name,
                            "child_birth_year": child.birth_year,
                            "parent_age": age_at_birth,
                        },
                    )
                    self._add_issue(issue, callback)

    def _check_marriage_timing(self, family: FamilyRecord, callback: Callable[[ValidationIssue], None] | None) -> None:
        """Check marriage events relative to birth/death dates."""
        marriage_events = [e for e in family.events if e.tag == "MARR"]
        if not marriage_events or not marriage_events[0].date:
            return
        
        marriage_year = self._extract_year(marriage_events[0].date)
        if not marriage_year:
            return
        
        # Check both spouses
        for spouse_id in [family.husband_id, family.wife_id]:
            if not spouse_id or spouse_id not in self.index.individuals:
                continue
            spouse = self.index.individuals[spouse_id]
            
            # Marriage before birth
            if spouse.birth_year and marriage_year < spouse.birth_year:
                issue = ValidationIssue(
                    severity="error",
                    category="marriage",
                    person_id=spouse.id,
                    person_name=spouse.name,
                    message=f"Marriage in {marriage_year} is before birth year ({spouse.birth_year})",
                    details={
                        "person_name": spouse.name,
                        "birth_year": spouse.birth_year,
                        "marriage_year": marriage_year,
                    },
                )
                self._add_issue(issue, callback)
            
            # Marriage after death
            if spouse.death_year and marriage_year > spouse.death_year:
                issue = ValidationIssue(
                    severity="error",
                    category="marriage",
                    person_id=spouse.id,
                    person_name=spouse.name,
                    message=f"Marriage in {marriage_year} is after death year ({spouse.death_year})",
                    details={
                        "person_name": spouse.name,
                        "death_year": spouse.death_year,
                        "marriage_year": marriage_year,
                    },
                )
                self._add_issue(issue, callback)

    def _check_child_viability(self, family: FamilyRecord, callback: Callable[[ValidationIssue], None] | None) -> None:
        """Check if children are born after parents died."""
        # Get parents
        father = self.index.individuals[family.husband_id] if family.husband_id and family.husband_id in self.index.individuals else None
        mother = self.index.individuals[family.wife_id] if family.wife_id and family.wife_id in self.index.individuals else None
        
        for child_id in family.child_ids:
            if child_id not in self.index.individuals:
                continue
            child = self.index.individuals[child_id]
            if not child.birth_year:
                continue
            
            # Check against father's death
            if father and father.death_year:
                # Allow up to GESTATION_MONTHS after death
                months_after_death = (child.birth_year - father.death_year) * 12
                if child.birth_year > father.death_year + self.GESTATION_MONTHS:
                    issue = ValidationIssue(
                        severity="error",
                        category="time_travel",
                        person_id=child.id,
                        person_name=child.name,
                        message=f"{child.name} born in {child.birth_year}, {child.birth_year - father.death_year} years after father {father.name} died ({father.death_year})",
                        details={
                            "child_name": child.name,
                            "father_name": father.name,
                            "child_birth_year": child.birth_year,
                            "father_death_year": father.death_year,
                            "years_after_death": child.birth_year - father.death_year,
                        },
                    )
                    self._add_issue(issue, callback)
            
            # Check against mother's death (strictly)
            if mother and mother.death_year and child.birth_year > mother.death_year:
                issue = ValidationIssue(
                    severity="error",
                    category="time_travel",
                    person_id=child.id,
                    person_name=child.name,
                    message=f"{child.name} born in {child.birth_year}, {child.birth_year - mother.death_year} years after mother {mother.name} died ({mother.death_year})",
                    details={
                        "child_name": child.name,
                        "mother_name": mother.name,
                        "child_birth_year": child.birth_year,
                        "mother_death_year": mother.death_year,
                        "years_after_death": child.birth_year - mother.death_year,
                    },
                )
                self._add_issue(issue, callback)

    def _extract_year(self, date_str: str | None) -> int | None:
        """Extract year from a date string."""
        if not date_str:
            return None
        for part in reversed(date_str.split()):
            if len(part) == 4 and part.isdecimal():
                return int(part)
        return None

    def _add_issue(self, issue: ValidationIssue, callback: Callable[[ValidationIssue], None] | None) -> None:
        """Add an issue to the list and call callback if provided."""
        self.issues.append(issue)
        if callback:
            callback(issue)
        logger.debug("Validation issue: %s - %s", issue.category, issue.message)
