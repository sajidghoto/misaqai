import json
from pathlib import Path

from src.parser.legal_parser import flatten_section_text, parse_blocks


FIXTURE_BLOCKS = Path(__file__).parents[1] / "output" / "PK-SRA1877_Source.blocks.json"
CPC_BLOCKS = Path(__file__).parents[1] / "output" / "CPC1908.blocks.json"
REGA_BLOCKS = Path(__file__).parents[1] / "output" / "REGA1908.blocks.json"


def test_federal_fixture_parser_builds_expected_verified_sections():
	data = json.loads(FIXTURE_BLOCKS.read_text(encoding="utf-8"))
	act = parse_blocks(data["blocks"])
	sections = {}
	def collect(nodes):
		for node in nodes:
			for section in node.sections:
				sections[section.section_number] = section
			for field in ("chapters", "parts"):
				for child in getattr(node, field, []):
					collect([child])
	collect([act])

	assert {"8", "9", "10"}.issubset(sections)
	assert "Procedure" in flatten_section_text(sections["8"])
	assert sections["8"].amendment_history == ["Procedure2"]
	assert sections["9"].provenance[0].page == 7
	assert sections["10"].explanations


def test_cpc_parser_uses_operative_body_and_drops_form_restarts():
	data = json.loads(CPC_BLOCKS.read_text(encoding="utf-8"))
	act = parse_blocks(data["blocks"])
	sections = {}
	def collect(nodes):
		for node in nodes:
			for section in node.sections:
				sections.setdefault(section.section_number, section)
			for field in ("chapters", "parts"):
				for child in getattr(node, field, []):
					collect([child])
	collect([act])

	assert act.meta.short_title == "This Act may be cited as the Code of Civil Procedure, 1908."
	assert list(sections)[:3] == ["1", "2", "3"]
	assert len([number for number in sections if number in {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13"}]) == 13


def test_rega_section_50_continuation_is_merged():
	data = json.loads(REGA_BLOCKS.read_text(encoding="utf-8"))
	act = parse_blocks(data["blocks"])
	sections = []
	def collect(nodes):
		for node in nodes:
			sections.extend(node.sections)
			for field in ("chapters", "parts"):
				for child in getattr(node, field, []):
					collect([child])
	collect([act])

	section_50 = [section for section in sections if section.section_number == "50"]
	assert len(section_50) == 1
	assert len(section_50[0].provenance) >= 2
