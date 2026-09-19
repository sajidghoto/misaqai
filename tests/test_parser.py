import json
from pathlib import Path

from src.parser.legal_parser import flatten_section_text, parse_blocks


FIXTURE_BLOCKS = Path(__file__).parents[1] / "output" / "PK-SRA1877_Source.blocks.json"


def test_federal_fixture_parser_builds_expected_verified_sections():
	data = json.loads(FIXTURE_BLOCKS.read_text(encoding="utf-8"))
	act = parse_blocks(data["blocks"])
	sections = {
		section.section_number: section
		for chapter in act.chapters
		for section in chapter.sections
	}

	assert {"8", "9", "10"}.issubset(sections)
	assert "Procedure" in flatten_section_text(sections["8"])
	assert sections["8"].amendment_history == ["Procedure2"]
	assert sections["9"].provenance[0].page == 7
	assert sections["10"].explanations
