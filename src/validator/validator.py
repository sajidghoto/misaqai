from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.schema.legal_structure_ir import Act, Clause, Explanation, Part, Proviso, Section, Subsection


SECTION_NUMBER_RE = re.compile(r"^(?P<number>\d+)(?P<suffix>[A-Za-z]*)$")
SUBSECTION_NUMBER_RE = re.compile(r"^\(\d+\)$")
CLAUSE_ID_RE = re.compile(r"^\([a-z]\)$")
SUBCLAUSE_ID_RE = re.compile(r"^\([ivxlcdm]+\)$", re.I)


@dataclass(frozen=True)
class ValidationIssue:
	code: str
	location: str
	message: str
	severity: str = "error"


@dataclass
class ValidationReport:
	issues: list[ValidationIssue] = field(default_factory=list)

	@property
	def errors(self) -> list[ValidationIssue]:
		return [issue for issue in self.issues if issue.severity == "error"]

	@property
	def warnings(self) -> list[ValidationIssue]:
		return [issue for issue in self.issues if issue.severity == "warning"]

	@property
	def is_valid(self) -> bool:
		return not self.errors


def _issue(report: ValidationReport, code: str, location: str, message: str, severity: str = "error") -> None:
	report.issues.append(ValidationIssue(code, location, message, severity))


def _section_key(value: str) -> tuple[int, str] | None:
	match = SECTION_NUMBER_RE.fullmatch(value.strip())
	return (int(match.group("number")), match.group("suffix").lower()) if match else None


def _validate_number_sequence(
	report: ValidationReport,
	values: list[str],
	location: str,
	label: str,
) -> None:
	seen: set[str] = set()
	previous_end: int | None = None
	for value in values:
		if value in seen:
			_issue(report, "duplicate_number", location, f"Duplicate {label} number: {value}.")
		seen.add(value)
		if label != "section":
			continue
		if "-" in value:
			parts = [part.strip() for part in value.split("-", maxsplit=1)]
			if len(parts) == 2 and all(part.isdigit() for part in parts):
				start, end = (int(part) for part in parts)
				if start > end:
					_issue(report, "invalid_range", location, f"Invalid section range: {value}.")
				elif previous_end is not None and start < previous_end:
					_issue(report, "out_of_order", location, f"Section range {value} follows {previous_end} out of order.")
				else:
					_issue(report, "range_repeal", location, f"Range-repeal section entry: {value}.", "warning")
					if previous_end is not None and start > previous_end + 1:
						_issue(
							report,
							"numbering_gap",
							location,
							f"Section numbering jumps from {previous_end} to {start}; verify repeals or omissions.",
							"warning",
						)
					previous_end = end
				continue
			_issue(report, "invalid_number", location, f"Invalid section number: {value}.")
			continue
		current = _section_key(value)
		if label == "section" and current is None:
			_issue(report, "invalid_number", location, f"Invalid section number: {value}.")
		elif previous_end is not None and current[0] < previous_end:
			_issue(report, "out_of_order", location, f"Section number {value} follows {previous_end} out of order.")
		elif previous_end is not None and current[0] > previous_end + 1:
			_issue(
				report,
				"numbering_gap",
				location,
				f"Section numbering jumps from {previous_end} to {current[0]}; verify repeals or omissions.",
				"warning",
			)
		if current is not None:
			previous_end = current[0]


def _validate_nested(report: ValidationReport, section: Section, location: str) -> None:
	if not section.provenance:
		_issue(report, "missing_provenance", location, "Section has no provenance.")
	for index, provenance in enumerate(section.provenance):
		if len(provenance.bbox) != 4:
			_issue(report, "invalid_provenance", f"{location}.provenance[{index}]", "Bounding box must have four values.")
	for subsection in section.subsections:
		if not SUBSECTION_NUMBER_RE.fullmatch(subsection.subsection_number):
			_issue(report, "invalid_subsection_number", location, f"Invalid subsection number: {subsection.subsection_number}.")
		_validate_subsection(report, subsection, f"{location}.subsection[{subsection.subsection_number}]")
	_validate_nested_items(report, section.provisos, location, Proviso, "Section")
	_validate_nested_items(report, section.explanations, location, Explanation, "Section")


def _validate_nested_items(
	report: ValidationReport,
	items: list[object],
	location: str,
	expected_type: type,
	owner: str,
) -> None:
	for index, item in enumerate(items):
		if not isinstance(item, expected_type):
			_issue(report, "invalid_nesting", f"{location}[{index}]", f"Nested item is not a valid {expected_type.__name__} under {owner}.")
		elif not item.text.strip():
			_issue(report, "empty_nested_text", location, f"Nested {expected_type.__name__.lower()} is empty.")


def _validate_subsection(report: ValidationReport, subsection: Subsection, location: str) -> None:
	_validate_nested_items(report, subsection.provisos, location, Proviso, "Subsection")
	_validate_nested_items(report, subsection.explanations, location, Explanation, "Subsection")
	for clause in subsection.clauses:
		if not CLAUSE_ID_RE.fullmatch(clause.clause_id):
			_issue(report, "invalid_clause_id", location, f"Invalid clause ID: {clause.clause_id}.")
		for subclause in clause.subclauses:
			if not SUBCLAUSE_ID_RE.fullmatch(subclause.subclause_id):
				_issue(report, "invalid_subclause_id", location, f"Invalid sub-clause ID: {subclause.subclause_id}.")
		_validate_nested_items(report, clause.provisos, location, Proviso, "Clause")
		_validate_nested_items(report, clause.explanations, location, Explanation, "Clause")
		if not clause.text.strip():
			_issue(report, "empty_nested_text", location, f"Clause {clause.clause_id} is empty.", "warning")


def _walk_containers(act: Act):
	def walk_container(container, location: str):
		yield location, list(getattr(container, "sections", []))
		for index, part in enumerate(getattr(container, "parts", [])):
			yield from walk_container(part, f"{location}.part[{index}]")
		for index, chapter in enumerate(getattr(container, "chapters", [])):
			yield from walk_container(chapter, f"{location}.chapter[{index}]")

	yield from walk_container(act, "act")


def validate_act(act: Act) -> ValidationReport:
	"""Run deterministic structural checks over a Legal Structure IR Act."""
	report = ValidationReport()
	if act.meta.long_title is None:
		_issue(report, "incomplete_metadata", "act.meta.long_title", "Long title is incomplete.", "warning")
	if act.meta.short_title is None:
		_issue(report, "incomplete_metadata", "act.meta.short_title", "Short title is incomplete.", "warning")
	if not act.meta.jurisdiction.strip():
		_issue(report, "missing_metadata", "act.meta.jurisdiction", "Jurisdiction is required.")
	if not act.meta.enacting_authority.strip():
		_issue(report, "missing_metadata", "act.meta.enacting_authority", "Enacting authority is required.")

	all_sections: list[Section] = []
	for location, sections in _walk_containers(act):
		_validate_number_sequence(report, [section.section_number for section in sections], location, "section")
		for index, section in enumerate(sections):
			_validate_nested(report, section, f"{location}.section[{index}]")
			all_sections.append(section)

	section_numbers = {section.section_number for section in all_sections}
	schedule_names = {schedule.schedule_name.casefold() for schedule in act.schedules}
	for section in all_sections:
		for schedule_ref in section.schedule_refs:
			if schedule_ref.casefold() not in schedule_names:
				_issue(report, "unresolved_reference", f"section[{section.section_number}]", f"Schedule reference does not resolve: {schedule_ref}.")
		for reference in re.findall(r"\bsections?\s+(\d+[A-Za-z]*)\b", section.text, re.I):
			if reference not in section_numbers:
				_issue(report, "unresolved_reference", f"section[{section.section_number}]", f"Section reference does not resolve: {reference}.", "warning")
	return report


def _validate_requested(act: Act) -> ValidationReport:
	report = ValidationReport()
	if act.meta.long_title is None:
		_issue(report, "incomplete_metadata", "act.meta.long_title", "Long title is incomplete.", "warning")
	if act.meta.short_title is None:
		_issue(report, "incomplete_metadata", "act.meta.short_title", "Short title is incomplete.", "warning")

	all_sections: list[Section] = []
	for location, sections in _walk_containers(act):
		_validate_number_sequence(report, [section.section_number for section in sections], location, "section")
		for index, section in enumerate(sections):
			section_location = f"{location}.section[{index}]"
			if not section.provenance:
				_issue(report, "missing_provenance", section_location, "Section has no provenance.")
			_validate_nested_items(report, section.provisos, section_location, Proviso, "Section")
			_validate_nested_items(report, section.explanations, section_location, Explanation, "Section")
			for subsection_index, subsection in enumerate(section.subsections):
				subsection_location = f"{section_location}.subsection[{subsection_index}]"
				_validate_nested_items(report, subsection.provisos, subsection_location, Proviso, "Subsection")
				_validate_nested_items(report, subsection.explanations, subsection_location, Explanation, "Subsection")
				for clause_index, clause in enumerate(subsection.clauses):
					clause_location = f"{subsection_location}.clause[{clause_index}]"
					_validate_nested_items(report, clause.provisos, clause_location, Proviso, "Clause")
					_validate_nested_items(report, clause.explanations, clause_location, Explanation, "Clause")
			all_sections.append(section)

	schedule_names = {schedule.schedule_name.casefold() for schedule in act.schedules}
	for section in all_sections:
		for schedule_ref in section.schedule_refs:
			if schedule_ref.casefold() not in schedule_names:
				_issue(
					report,
					"unresolved_reference",
					f"section[{section.section_number}]",
					f"Schedule reference does not resolve: {schedule_ref}.",
				)
	return report


def validate(act: Act) -> list[str]:
	"""Return human-readable issues for the requested Act validation checks."""
	return [
		f"{issue.severity}: {issue.location}: {issue.message}"
		for issue in _validate_requested(act).issues
	]
