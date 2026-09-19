import argparse
from pathlib import Path

import fitz

from src.extraction.characterizer import characterize_document
from src.extraction.ocr_extractor import extract_ocr_page
from src.extraction.pymupdf_extractor import extract_native_page
from src.normalize.block_ir import NormalizedDocument


def extract_document(pdf_path: Path) -> NormalizedDocument:
	with fitz.open(pdf_path) as document:
		decisions = characterize_document(document)
		blocks = []
		for decision in decisions:
			page = document[decision.page - 1]
			if decision.extraction_method == "native":
				blocks.extend(extract_native_page(page, decision.page))
			else:
				blocks.extend(extract_ocr_page(page, decision.page))
		return NormalizedDocument(
			source_file=pdf_path.name,
			page_count=len(document),
			page_methods=[decision.extraction_method for decision in decisions],
			blocks=blocks,
		)


def write_fixture_outputs(fixtures_dir: Path, output_dir: Path) -> list[Path]:
	output_dir.mkdir(parents=True, exist_ok=True)
	outputs = []
	for pdf_path in sorted(fixtures_dir.glob("*.pdf")):
		answer_key_candidates = (
			fixtures_dir / f"{pdf_path.name}.answer_key.json",
			pdf_path.with_suffix(".answer_key.json"),
			pdf_path.with_suffix(".answere_key.json"),
		)
		if not any(candidate.exists() for candidate in answer_key_candidates):
			continue
		normalized = extract_document(pdf_path)
		output_path = output_dir / f"{pdf_path.stem}.blocks.json"
		output_path.write_text(normalized.model_dump_json(indent=2) + "\n", encoding="utf-8")
		outputs.append(output_path)
	return outputs


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Run Stage 1 extraction for fixture PDFs.")
	parser.add_argument("--fixtures", type=Path, default=Path("fixtures"))
	parser.add_argument("--output", type=Path, default=Path("output"))
	args = parser.parse_args()
	for output_path in write_fixture_outputs(args.fixtures, args.output):
		print(output_path)
