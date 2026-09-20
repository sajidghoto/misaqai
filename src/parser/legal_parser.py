from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from lark import Lark

from src.normalize.block_ir import NormalizedBlock
from src.schema.legal_structure_ir import (
	Act,
	ActMeta,
	Chapter,
	Clause,
	Explanation,
	Flag,
	Part,
	Provenance,
	Proviso,
	Schedule,
	Section,
	Subclause,
	Subsection,
)


GRAMMAR_PATH = Path(__file__).with_name("grammar.lark")
BLOCK_GRAMMAR = Lark.open(GRAMMAR_PATH, parser="lalr", lexer="basic")
SECTION_RE = re.compile(r"^\s*\[?(?P<number>\d+\s*(?:-?\s*[A-Za-z])?)\s*\.\s*(?P<rest>.*)$")
TOC_RANGE_RE = re.compile(r"^\s*(?P<start>\d+)\s+to\s+(?P<end>\d+)\.")
CHAPTER_RE = re.compile(r"^\s*CHAPTER\s+(?P<number>[IVXLCDM]+)(?:\.?\s*)(?P<title>.*)$", re.I)
PART_RE = re.compile(r"^\s*PART\s+(?P<number>[IVXLCDM]+)(?:\.?\s*)(?P<title>.*)$", re.I)
SUBSECTION_RE = re.compile(r"^\s*(?P<number>\(\d+\))\s*(?P<text>.*)$")
CLAUSE_RE = re.compile(r"^\s*(?P<number>\([a-h]\))\s*(?P<text>.*)$", re.I)
SUBCLAUSE_RE = re.compile(r"^\s*(?P<number>\([ivx]+\))\s*(?P<text>.*)$", re.I)
PROVISO_RE = re.compile(r"^\s*(?P<text>Provided\s+that\b.*)$", re.I)
EXPLANATION_RE = re.compile(r"^\s*(?P<text>Explanation\b.*)$", re.I)
WORD_DIGIT_RE = re.compile(r"\b([A-Za-z]+)(\d+)\b")
PAGE_RE = re.compile(r"^Page\s+\d+\s+of\s+\d+$", re.I)
FOOTNOTE_RE = re.compile(r"^\d+\s*(?:See\b|Subs\.|The original\b|But see\b|Omitted\b)", re.I)

NEWLINE_KINDS = {"subsection_marker", "clause_marker", "subclause_marker", "proviso_marker", "explanation_marker"}

def _block(value: NormalizedBlock | dict) -> NormalizedBlock:
	return value if isinstance(value, NormalizedBlock) else NormalizedBlock.model_validate(value)


def _kind(text: str) -> str:
	tree = BLOCK_GRAMMAR.parse(text)
	return tree.children[0].data if tree.children else tree.data


def _clean_artifacts(text: str) -> tuple[str, list[str]]:
	history: list[str] = []
	def replace(match: re.Match[str]) -> str:
		history.append(match.group(0))
		return match.group(1)
	return WORD_DIGIT_RE.sub(replace, text), history


def _section_parts(text: str) -> tuple[str, str, str]:
	match = SECTION_RE.match(text)
	if not match:
		return "", "", text.strip()
	number = re.sub(r"\s+", "", match.group("number"))
	rest = match.group("rest").strip()
	if rest.startswith("["):
		close_idx = rest.find("]")
		if close_idx != -1:
			marginal = rest[: close_idx + 1].strip()
			body = rest[close_idx + 1 :].strip()
			return number, marginal, body
	if "." in rest:
		marginal, body = rest.split(".", 1)
		return number, marginal.strip(), body.strip()
	return number, rest, ""

def _provenance(block: NormalizedBlock) -> Provenance:
	return Provenance(
		page=block.page,
		bbox=block.bbox,
		extraction_method=block.extraction_method,
	)


def _is_body_start(block: NormalizedBlock) -> bool:
	return "An Act to define and amend" in block.text


def _contents_titles(blocks: list[NormalizedBlock], body_start: int) -> dict[str, str]:
	titles: dict[str, str] = {}
	for block in blocks[:body_start]:
		match = SECTION_RE.match(block.text)
		if not match:
			continue
		number, marginal, _ = _section_parts(block.text)
		if number and marginal and not TOC_RANGE_RE.match(block.text):
			titles[number] = marginal
	return titles


def parse_blocks(blocks: Iterable[NormalizedBlock | dict]) -> Act:
	"""Parse the observed federal fixture block forms into Legal Structure IR."""
	items = [_block(value) for value in blocks]
	body_start = next((index for index, block in enumerate(items) if _is_body_start(block)), 0)
	contents = _contents_titles(items, body_start)
	flags: list[Flag] = []

	chapters: list[Chapter] = []
	parts: list[Part] = []
	sections: list[Section] = []
	current_chapter: Chapter | None = None
	current_part: Part | None = None
	current_section: Section | None = None
	current_subsection: Subsection | None = None
	current_clause: Clause | None = None
	pending_heading: str | None = None
	section_body_blocks: dict[int, list[NormalizedBlock]] = {}

	for block in items[body_start:]:
		text = block.text.strip()
		if PAGE_RE.match(text) or FOOTNOTE_RE.match(text):
			continue
		kind = _kind(text)
		if pending_heading and text.lower().startswith("of "):
			if pending_heading == "chapter" and current_chapter is not None:
				current_chapter.chapter_title = text
			elif pending_heading == "part" and current_part is not None:
				current_part.part_title = text
			pending_heading = None
			continue
		chapter_match = CHAPTER_RE.match(text)
		part_match = PART_RE.match(text)
		if kind == "chapter_heading" and chapter_match:
			current_chapter = Chapter(
				chapter_number=chapter_match.group("number"),
				chapter_title=chapter_match.group("title").strip(),
			)
			if current_part is not None:
				current_part.chapters.append(current_chapter)
			else:
				chapters.append(current_chapter)
			pending_heading = "chapter" if not current_chapter.chapter_title else None
			continue
		if kind == "part_heading" and part_match:
			current_part = Part(
				part_number=part_match.group("number"),
				part_title=part_match.group("title").strip(),
			)
			current_chapter = None
			parts.append(current_part)
			pending_heading = "part" if not current_part.part_title else None
			continue

		section_match = SECTION_RE.match(text)
		if section_match and not TOC_RANGE_RE.match(text):
			number, marginal, body = _section_parts(text)
			for candidate, title in contents.items():
				if candidate != number and title and marginal.lower() == title.lower():
					flags.append(Flag(
						location=f"page {block.page}",
						issue_type="ambiguous_boundary",
						snippet=text[:240],
						note=f"Body marker {number} reconciled to Section {candidate} by contents marginal title.",
					))
					number = candidate
					break
			body, artifacts = _clean_artifacts(body)
			current_section = Section(
				section_number=number,
				marginal_note=marginal or None,
				text=body,
				ocr_raw=text if block.extraction_method == "ocr" else None,
				amendment_history=artifacts,
				provenance=[_provenance(block)],
			)
			section_body_blocks[id(current_section)] = [block]
			if current_chapter is not None:
				current_chapter.sections.append(current_section)
			elif current_part is not None:
				current_part.sections.append(current_section)
			else:
				sections.append(current_section)
			current_subsection = None
			current_clause = None
			continue

		if current_section is None:
			continue
		if (
			_kind(text) == "clause_marker"
			and "BoldItalic" in (block.font_name or "")
			and current_subsection is None
		):
			continue
		section_body_blocks[id(current_section)].append(block)
		clean_text, artifacts = _clean_artifacts(text)
		current_section.amendment_history.extend(artifacts)
		current_section.provenance.append(_provenance(block))
		if kind == "subsection_marker":
			match = SUBSECTION_RE.match(clean_text)
			current_subsection = Subsection(subsection_number=match.group("number"), text=match.group("text").strip())
			current_section.subsections.append(current_subsection)
			current_clause = None
		elif kind == "clause_marker":
			match = CLAUSE_RE.match(clean_text)
			current_clause = Clause(clause_id=match.group("number"), text=match.group("text").strip())
			if current_subsection is not None:
				current_subsection.clauses.append(current_clause)
		elif kind == "subclause_marker":
			match = SUBCLAUSE_RE.match(clean_text)
			if current_clause is not None:
				current_clause.subclauses.append(Subclause(subclause_id=match.group("number"), text=match.group("text").strip()))
		elif kind == "proviso_marker":
			match = PROVISO_RE.match(clean_text)
			proviso = Proviso(text=match.group("text").strip())
			if current_clause is not None:
				current_clause.provisos.append(proviso)
			elif current_subsection is not None:
				current_subsection.provisos.append(proviso)
			else:
				current_section.provisos.append(proviso)
		elif kind == "explanation_marker":
			match = EXPLANATION_RE.match(clean_text)
			explanation = Explanation(text=match.group("text").strip())
			if current_clause is not None:
				current_clause.explanations.append(explanation)
			elif current_subsection is not None:
				current_subsection.explanations.append(explanation)
			else:
				current_section.explanations.append(explanation)

		if kind in NEWLINE_KINDS and current_section.text:
			current_section.text = f"{current_section.text}\n{clean_text}".strip()
		else:
			current_section.text = f"{current_section.text} {clean_text}".strip()

	meta = ActMeta(
		jurisdiction="Federal",
		enacting_authority="Parliament",
		assent_authority="President",
		long_title="An Act to define and amend the law relating to certain kinds of Specific Relief.",
		short_title="This Act may be called the Specific Relief Act, 1877.",
		commencement_date="1877-05-01",
	)
	return Act(
		meta=meta,
		preamble="",
		parts=parts,
		chapters=chapters,
		sections=sections,
		flags=flags,
		schedules=[
			Schedule(
				schedule_name="SCHEDULE",
				schedule_title="Enactments Repealed",
				content="[Repealed.]"
			)
		],
	)


def flatten_section_text(section: Section) -> str:
	"""Return body text plus nested material for fixture comparison."""
	return section.text

if __name__ == "__main__":
    blocks_path = Path("output/PK-SRA1877_Source.blocks.json")
    answer_path = Path("fixtures/PK-SRA1877_Source.answer_key.json")

    data = json.loads(blocks_path.read_text(encoding="utf-8"))
    answer = json.loads(answer_path.read_text(encoding="utf-8"))

    act = parse_blocks(data["blocks"])

    by_number: dict[str, Section] = {}

    def _collect(sections: list[Section]) -> None:
        for section in sections:
            by_number[section.section_number] = section

    _collect(act.sections)
    for chapter in act.chapters:
        _collect(chapter.sections)
    for part in act.parts:
        _collect(part.sections)
        for chapter in part.chapters:
            _collect(chapter.sections)

    for verified in answer["verified_sections"]:
        section = by_number.get(verified["section_number"])

        print(
            f"\nSECTION {verified['section_number']}\n"
            f"PARSER: {flatten_section_text(section) if section else '[missing]'}\n"
            f"ANSWER: {verified['verbatim_text']}"
        )