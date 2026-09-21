from src.schema.legal_structure_ir import Act, ActMeta, Provenance, Section
from src.validator.validator import validate_act


def _act(section_numbers: list[str]) -> Act:
	return Act(
		meta=ActMeta(jurisdiction="Federal", enacting_authority="Parliament"),
		sections=[
			Section(
				section_number=number,
				text=f"Text for section {number}.",
				provenance=[Provenance(page=1, bbox=(0, 0, 1, 1), extraction_method="native")],
			)
			for number in section_numbers
		],
	)


def test_validator_accepts_ordered_sections_with_provenance():
	report = validate_act(_act(["1", "2", "3"]))

	assert report.is_valid
	assert not report.errors


def test_validator_reports_duplicates_and_numbering_gaps():
	report = validate_act(_act(["1", "3", "3"]))

	assert not report.is_valid
	assert any(issue.code == "duplicate_number" for issue in report.errors)
	assert any(issue.code == "numbering_gap" for issue in report.warnings)


def test_validator_reports_missing_provenance_and_unresolved_references():
	act = _act(["1"])
	act.sections[0].provenance = []
	act.sections[0].text = "See section 99."

	report = validate_act(act)

	assert not report.is_valid
	assert any(issue.code == "missing_provenance" for issue in report.errors)
	assert any(issue.code == "unresolved_reference" for issue in report.warnings)
