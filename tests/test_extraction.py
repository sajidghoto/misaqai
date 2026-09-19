from pathlib import Path

import fitz

from src.extraction.characterizer import characterize_document
from src.extraction.pymupdf_extractor import extract_native_page
from src.normalize.block_ir import NormalizedBlock


FIXTURES = Path(__file__).parents[1] / "fixtures"


def test_native_fixture_pages_are_characterized_as_native():
	with fitz.open(FIXTURES / "PK-SRA1877_Source.pdf") as document:
		decisions = characterize_document(document)

	assert all(decision.extraction_method == "native" for decision in decisions)


def test_native_extraction_preserves_block_provenance():
	with fitz.open(FIXTURES / "PK-SRA1877_Source.pdf") as document:
		blocks = extract_native_page(document[1], 2)

	assert blocks
	assert all(isinstance(block, NormalizedBlock) for block in blocks)
	assert all(block.page == 2 and block.extraction_method == "native" for block in blocks)
	assert all(len(block.bbox) == 4 for block in blocks)


def test_punjab_fixture_is_characterized_as_ocr():
	with fitz.open(FIXTURES / "PRPA2009.pdf") as document:
		decisions = characterize_document(document)

	assert len(decisions) == 8
	assert all(decision.extraction_method == "ocr" for decision in decisions)
