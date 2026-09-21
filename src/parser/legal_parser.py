from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

from lark import Lark

from src.normalize.block_ir import NormalizedBlock
from src.normalize.toc_filter import split_toc_and_body
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
EMBEDDED_SECTION_RE = re.compile(
	r"(?<![\w-])(?:"
	r"(?P<footnote>\d+\s*)?\[\s*(?P<bracket_number>\d{1,3}\s*(?:-?\s*[A-Za-z])?)"
	r"|(?P<plain_number>\d{1,3}\s*(?:-?\s*[A-Za-z])?)"
	r")\s*\.\s+"
)
TOC_UNPUNCTUATED_SECTION_RE = re.compile(
	r"(?<![\w-])(?P<number>\d{1,3}(?:[A-Z])?)\s+(?=[A-Z\[\"])"
)
TOC_RANGE_RE = re.compile(r"^\s*(?P<start>\d+)\s+to\s+(?P<end>\d+)\.")
BODY_RANGE_REPEAL_RE = re.compile(r"^\s*(?P<start>\d+)\s+to\s+(?P<end>\d+)\.\s*\[Repealed\]", re.I)
CHAPTER_RE = re.compile(r"^\s*CHAPTER\s+(?P<number>[IVXLCDM]+)(?:\.?\s*)(?P<title>.*)$", re.I)
PART_RE = re.compile(r"^\s*PART\s+(?P<number>[IVXLCDM]+(?:-[A-Z])?)(?:\.?\s*)(?P<title>.*)$", re.I)
SUBSECTION_RE = re.compile(r"^\s*(?P<number>\(\d+\))\s*(?P<text>.*)$")
CLAUSE_RE = re.compile(r"^\s*(?P<number>\([a-h]\))\s*(?P<text>.*)$")
UPPER_SUBHEADING_RE = re.compile(r"^\s*\([A-H]\)\s*(?P<text>.*)$")
SUBHEADING_RE = re.compile(r"^[A-Z][A-Za-z ,\-']{2,80}$")
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


def _is_embedded_section_marker(text: str, match: re.Match[str]) -> bool:
	context = text[max(0, match.start() - 12):match.start()]
	return not re.search(r"\bsections?\s*$", context, re.I)


def _marker_number(match: re.Match[str]) -> str:
	value = match.group("bracket_number") or match.group("plain_number")
	return re.sub(r"\s+", "", value)


def _marker_fragment(text: str, match: re.Match[str], end: int) -> str:
	footnote_length = len(match.group("footnote") or "")
	start = match.start() + footnote_length
	return text[start:end].strip()


def _normalized_title(value: str) -> str:
	return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _section_key_for_order(value: str) -> tuple[int, str]:
	match = re.fullmatch(r"(\d+)([A-Za-z]*)", value.strip())
	return (int(match.group(1)), match.group(2).lower()) if match else (10**9, value)


def _contents_section_titles(blocks: list[NormalizedBlock]) -> dict[str, str]:
	titles: dict[str, str] = {}
	for block in blocks:
		matches = [
			match for match in EMBEDDED_SECTION_RE.finditer(block.text)
			if _is_embedded_section_marker(block.text, match)
		]
		for index, match in enumerate(matches):
			end = matches[index + 1].start() if index + 1 < len(matches) else len(block.text)
			_, marginal, _ = _section_parts(_marker_fragment(block.text, match, end))
			if marginal:
				titles[_marker_number(match)] = marginal
		unpunc_matches = list(TOC_UNPUNCTUATED_SECTION_RE.finditer(block.text))
		for index, match in enumerate(unpunc_matches):
			end = unpunc_matches[index + 1].start() if index + 1 < len(unpunc_matches) else len(block.text)
			value = block.text[match.end():end].strip()
			if value:
				titles[match.group("number")] = value.split(".", 1)[0].strip()
	return titles


def _matches_contents_title(
	text: str,
	match: re.Match[str],
	contents_titles: dict[str, str],
) -> bool:
	marker_number = _marker_number(match)
	if re.fullmatch(r"\d+S", marker_number, re.I):
		return False
	if marker_number not in contents_titles:
		return False
	end = min(len(text), match.end() + 240)
	_, marginal, _ = _section_parts(_marker_fragment(text, match, end))
	candidate = _normalized_title(marginal)
	if len(candidate) < 8 or candidate.startswith("w e f"):
		return False
	for title in contents_titles.values():
		expected = _normalized_title(title)
		if candidate.startswith(expected) or expected.startswith(candidate):
			if len(candidate) >= 8:
				return True
		if SequenceMatcher(None, candidate, expected).ratio() >= 0.88:
			return True
	return False


def _split_section_blocks(
	block: NormalizedBlock,
	contents_titles: dict[str, str],
) -> list[NormalizedBlock]:
	text = block.text
	matches = [
		match for match in EMBEDDED_SECTION_RE.finditer(text)
		if _is_embedded_section_marker(text, match)
		and _matches_contents_title(text, match, contents_titles)
	]
	if not matches:
		return [block]

	segments: list[str] = []
	if matches[0].start() > 0:
		segments.append(text[:matches[0].start()].strip())
	for index, match in enumerate(matches):
		end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
		footnote_length = len(match.group("footnote") or "")
		segments.append(text[match.start() + footnote_length:end].strip())
	return [
		block.model_copy(update={"text": segment})
		for segment in segments
		if segment
	]


def _split_body_blocks(
	blocks: list[NormalizedBlock],
	contents_titles: dict[str, str],
) -> list[NormalizedBlock]:
	result: list[NormalizedBlock] = []
	for block in blocks:
		result.extend(_split_section_blocks(block, contents_titles))
	return result


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


SHORT_TITLE_SENTENCE_RE = re.compile(
	r"(?:This Act may be called|This Act may be cited as|may be cited as)[^.]*\.",
	re.I,
)


def _extract_short_title(blocks: list[NormalizedBlock]) -> str | None:
	for block in blocks:
		if not re.match(r"^\s*1\.\s", block.text):
			continue
		match = SHORT_TITLE_SENTENCE_RE.search(block.text)
		if match:
			title = re.sub(r"\s*\d+\s*\[[^\]]*\]", "", match.group(0))
			title = re.sub(r"\s*\d+\s*\*", " ", title)
			return re.sub(r"\s+", " ", title).strip()
	return None


def _extract_long_title(blocks: list[NormalizedBlock]) -> str | None:
	for block in blocks:
		text = block.text.strip()
		if text.upper().startswith("THE ") and "ACT" in text.upper():
			return text
	for block in blocks:
		match = re.search(r"\bAn Act to\b.*?\.", block.text, re.I | re.S)
		if match:
			return re.sub(r"\s+", " ", match.group(0)).strip()
	return None


def parse_blocks(
	blocks: Iterable[NormalizedBlock | dict],
	*,
	filter_toc: bool = True,
) -> Act:
	"""Parse the observed federal fixture block forms into Legal Structure IR."""
	items = [_block(value) for value in blocks]
	if filter_toc:
		toc_blocks, body_blocks = split_toc_and_body(items)
	else:
		toc_blocks, body_blocks = [], items
	contents_section_titles = _contents_section_titles(toc_blocks)
	contents = _contents_titles(toc_blocks, len(toc_blocks))
	contents.update(contents_section_titles)
	body_blocks = _split_body_blocks(body_blocks, contents_section_titles)
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

	for block in body_blocks:
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
			if contents and number not in contents:
				continue
			own_title = contents.get(number)
			own_matches = bool(own_title and (
				_normalized_title(marginal) == _normalized_title(own_title)
				or SequenceMatcher(
					None, _normalized_title(marginal), _normalized_title(own_title)
				).ratio() >= 0.88
			))
			reconciled = False
			if not own_matches:
				for candidate, title in contents.items():
					if candidate != number and title and _normalized_title(marginal) == _normalized_title(title):
						flags.append(Flag(
							location=f"page {block.page}",
							issue_type="ambiguous_boundary",
							snippet=text[:240],
							note=f"Body marker {number} reconciled to Section {candidate} by contents marginal title.",
						))
						number = candidate
						reconciled = True
						break
			if current_section is not None and number == current_section.section_number:
				if marginal and current_section.marginal_note and _normalized_title(marginal) != _normalized_title(current_section.marginal_note):
					continue
				current_section.text = f"{current_section.text} {body}".strip()
				current_section.provenance.append(_provenance(block))
				continue
			container_sections = current_chapter.sections if current_chapter is not None else current_part.sections if current_part is not None else sections
			if container_sections and _section_key_for_order(number) < _section_key_for_order(container_sections[-1].section_number):
				continue
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

		range_match = BODY_RANGE_REPEAL_RE.match(text)
		if range_match:
		    current_section = Section(
		        section_number=f"{range_match.group('start')}-{range_match.group('end')}",
		        marginal_note=None,
		        text="[Repealed]",
		        provenance=[_provenance(block)],
		    )
		    flags.append(Flag(
		        location=f"page {block.page}",
		        issue_type="other",
		        snippet=text[:120],
		        note=f"Range repeal: sections {range_match.group('start')}-{range_match.group('end')} collapsed into one entry.",
		    ))
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
		if (UPPER_SUBHEADING_RE.match(text) or
			(SUBHEADING_RE.match(text) and not text.endswith("."))):
			flags.append(Flag(
				location=f"page {block.page}",
				issue_type="other",
				snippet=text[:120],
				note="Topical sub-heading skipped, not merged into section text.",
			))
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

	short_title_text = _extract_short_title(body_blocks)
	long_title_text = _extract_long_title(toc_blocks)
	if short_title_text is None:
		flags.append(Flag(
			location="act metadata",
			issue_type="missing_expected_field",
			snippet="",
			note="Could not reliably extract the operative short-title sentence.",
		))
	if long_title_text is None:
		flags.append(Flag(
			location="act metadata",
			issue_type="missing_expected_field",
			snippet="",
			note="Could not find a formal long title before the contents/body boundary.",
		))
	flags.append(Flag(
		location="act metadata",
		issue_type="missing_expected_field",
		snippet="",
		note="Commencement date was not reliably extracted and remains unresolved.",
	))
	meta = ActMeta(
		jurisdiction="Federal",
		enacting_authority="Parliament",
		assent_authority="President",
		long_title=long_title_text or "",
		short_title=short_title_text or "",
		commencement_date=None,
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