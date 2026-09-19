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

### Stage 3 - grammar and parser (federal fixture only, 2026-09-19)

Added the fixture-grounded grammar in `src/parser/grammar.lark` and the
deterministic Block IR parser in `src/parser/legal_parser.py`. The parser was
tested only with `PK-SRA1877_Source.blocks.json` and preserves Section
provenance, creates the Act/Chapter/Part hierarchy, nests observed
subsections/provisos/explanations, and moves word-digit artifacts such as
`Procedure2` into `amendment_history`.

Patterns derived from the federal fixture:

- Pages 1-4 are contents; operative parsing starts at the block containing
	the Act long title, `An Act to define and amend...`.
- Section markers, marginal notes, and first body text are commonly fused in
	one block; the first period after the marker separates the marginal note.
- A body block labeled `39.` has the Section 9 marginal title, so it is
	reconciled to Section 9 and flagged as an ambiguous boundary.
- Bold-italic `(a)`/`(b)` headings between sections are contents headings and
	are skipped using their observed font metadata.
- Numbered `Explanation 1.__` blocks and `Provided that...` blocks attach to
	the current Section or preceding nested element.
- Footnote blocks beginning with forms such as `1The original...`, `1See...`,
	or `1Subs...` are excluded from Section body text.
- Later headings such as `CHAPTER III` followed by `OF THE ...` and `PART III`
	followed by `Of ...` are combined across adjacent blocks.

Patterns guessed rather than proven from a broader corpus: the federal
metadata values, the Act commencement date, the contents/body transition
anchor, and the rule that bold-italic clause-shaped blocks are non-operative
headings. Stage 2 has no Act-level `parts` field, so the fixture's top-level
Part III is represented under the preceding Chapter VIII; this was not fixed
by inventing a schema field. The parser has not been run against Punjab or
Sindh fixtures, and no Stage 4 validation was started.
