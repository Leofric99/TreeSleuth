#!/usr/bin/env python
"""Test GEDCOM validator on Arthur Astle family tree."""

from pathlib import Path
from treesleuth.gedcom import parse_gedcom_files
from treesleuth.validator import GedcomValidator

gedcom_path = Path(r'C:\Users\micro\Desktop\Astle\Arthur Astle (1870)\V1.1.ged')
print(f"Validating: {gedcom_path}")
print(f"File exists: {gedcom_path.exists()}")

# Parse GEDCOM
index = parse_gedcom_files([gedcom_path])
print(f"\nGEDCOM Statistics:")
print(f"  Individuals: {len(index.individuals)}")
print(f"  Families: {len(index.families)}")
print(f"  Parse errors: {len(index.errors)}")
if index.errors:
    for error in index.errors:
        print(f"    - {error}")

# Run validation
print(f"\nRunning validation...")
validator = GedcomValidator(index)
issues = validator.validate()

print(f"\nValidation Results:")
print(f"  Total issues: {len(issues)}")
error_count = sum(1 for i in issues if i.severity == "error")
warning_count = sum(1 for i in issues if i.severity == "warning")
print(f"  Errors: {error_count}")
print(f"  Warnings: {warning_count}")

if issues:
    print(f"\nIssues by category:")
    by_category = {}
    for issue in issues:
        by_category.setdefault(issue.category, []).append(issue)
    
    for category in sorted(by_category.keys()):
        cat_issues = by_category[category]
        print(f"\n  {category.upper()} ({len(cat_issues)}):")
        for issue in cat_issues[:5]:  # Show first 5 of each category
            print(f"    [{issue.severity.upper()}] {issue.person_name}: {issue.message}")
        if len(cat_issues) > 5:
            print(f"    ... and {len(cat_issues) - 5} more")
else:
    print("\n* No issues found!")

