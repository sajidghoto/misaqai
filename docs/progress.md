## Stage 1 - extraction

Implemented the page-level extraction path:

- `characterizer.py` classifies each page from its usable text layer.
- Native pages use PyMuPDF text blocks.
- Pages without usable text use PyMuPDF OCR via Tesseract.
- `src/normalize/block_ir.py` defines Pydantic `NormalizedBlock` and
	`NormalizedDocument` models with text, page, bbox, font metadata, and
	extraction method.
- `src/pipeline.py` writes `/output/<pdf stem>.blocks.json` for fixture PDFs
	with matching answer keys.

### Fixture status (2026-09-19)

- `PK-SRA1877_Source.pdf`: processed successfully; 35 native pages and 544
	normalized blocks written to `output/PK-SRA1877_Source.blocks.json`.
- `PRPA2009.pdf`: processed successfully; 8 OCR pages and 156 normalized
	blocks written to `output/PRPA2009.blocks.json`.
- `SRPO1979.pdf`: processed successfully; 13 native pages, 1 OCR page, and
	148 normalized blocks written to `output/SRPO1979.blocks.json`.

For the Punjab fixture specifically: 0 pages used native extraction, 8 pages
were routed to OCR, and all 8 pages completed through OCR.

Manual review: the final page of `SRPO1979.pdf` is the only page classified as
OCR because it has no usable native text layer. Review the Punjab OCR text for
scan-quality errors before using it as downstream parser input.

### Stage 1 fixture validation (2026-09-19)

Added `tests/validate_fixture.py`, which reports section-marker coverage,
section-aware verbatim exact/fuzzy/miss results, known-issue locations, thin
repealed/empty sections, fused word-digit artifacts, and OCR completion. It
writes one `*.validation_report.json` beside each generated Block IR file.

Current validation results:

- `PK-SRA1877_Source.pdf`: 51/51 section markers found; 1 fuzzy and 2
	verbatim misses; 35 native pages; 3 informational digit artifacts.
- `PRPA2009.pdf`: 32/36 section markers found; 3 verbatim misses; 8 OCR
	pages completed; 0 OCR pages empty.
- `SRPO1979.pdf`: 27/28 section markers found; 1 exact, 2 fuzzy, and 0
	verbatim misses; 13 native pages and 1 OCR page completed.

These are reports only. No fixture answer key or Block IR file was modified.

0 exact verbatim matches in Stage 1 validator, suspected TOC-vs-body
double-counting, not re-investigated - revisit if Stage 3 grammar parsing shows
unexpected duplicate sections.

### Stage 2 - Legal Structure IR schema (2026-09-19)

Added the Pydantic Legal Structure IR models in
`src/schema/legal_structure_ir.py`: Act metadata, chapters, parts, sections,
subsections, clauses, subclauses, provisos, explanations, schedules, flags,
and provenance. The existing Normalized Block IR was preserved unchanged.

Added a placeholder composition test in `tests/test_schema.py`. No grammar,
parser, or fixture parsing was added.
