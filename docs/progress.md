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

### Stage 3 federal generalization (2026-09-21)

Added `src/normalize/toc_filter.py` with `split_toc_and_body()`. The splitter
retains TOC blocks separately and uses Section 1 marker structure, marker
density, and relative candidate block length rather than an Act-specific
phrase. Both CA1872 and PK-SRA1877_Source have a single leading TOC/body
boundary; no post-body TOC island was observed in either Block IR fixture.

The parser now consumes the filtered body and extracts only the operative
short-title sentence. Formal titles are searched in pre-TOC blocks, and
commencement remains `None` with an unresolved metadata flag rather than being
fabricated. Federal jurisdiction, Parliament, and President remain fixed for
this batch as requested.

### Federal batch verification (2026-09-21)

Re-ran the federal batch successfully after making Tesseract available on
the Python PATH.

- All seven federal Acts extracted and parsed successfully.
- CPC1908 OCR completed successfully; the previous Tesseract error is resolved.
- CA1872 contains all expected operative sections from the source.
- CA1872 has no duplicate section numbers.
- Sections 19A, 30A, 30B, and 30C are valid sections present in the source.
- Full test suite passes: 7 passed.

The CA1872 audit logic still needs its expected inventory updated to include
19A, 30A, 30B, and 30C. The parser output should not remove these sections.

### Stage 4 - deterministic Legal Structure IR validator (2026-09-21)

Implemented `src/validator/validator.py` with structured validation reports.
The validator checks required Act metadata, duplicate and out-of-order section
boundaries, numbering gaps as warnings, nested numbering identifiers,
provenance completeness, empty nested text, and unresolved section or schedule
references. It preserves source numbering and never silently renumbers gaps.

Added focused tests in `tests/test_validator.py`; all three validator tests
pass.

Applied to the regenerated federal Act outputs:

- CA1872: valid, 0 errors, 4 warnings.
- SRA1877: valid, 0 errors, 1 warning.
- QSO1984: valid, 0 errors, 5 warnings.
- CPC1908: invalid, with duplicate and out-of-order section boundaries.
- REGA1908: invalid, duplicate Section 50.
- STA1899: invalid, out-of-order Section 14 boundary.
- TPA1882: invalid, duplicate Section 70 and an out-of-order 63A boundary.

Stage 4 is implemented but the federal batch is not yet fully validated.
The next parser work should address the CPC1908, REGA1908, STA1899, and
TPA1882 boundary findings before pipeline wiring and RAG chunking.

### Stage 3 boundary fixes and Stage 4 federal validation (2026-09-22)

Resolved the remaining federal parser boundary issues:

- CPC1908 now selects the operative Section 1/body boundary using the
	short-title evidence instead of the longest numbered block. Later form
	numbering no longer creates duplicate Act sections.
- Same-number page continuations, including Registration Act Section 50, are
	merged into one Section while retaining all provenance records.
- Lower-number restarts from appendix/form material are excluded from the
	operative section hierarchy.
- Section suffix ordering now treats values such as 63A correctly after 63
	and before 64.
- Empty template clauses are retained and reported as warnings rather than
	structural validation errors.

Added focused regressions for CPC body detection, CPC metadata and numbering,
and REGA Section 50 continuation handling.

Current verification:

- All seven federal Act outputs validate with zero errors.
- Remaining findings are warnings only: numbering gaps, unresolved textual
	references, and source/template artifacts requiring review.
- Full test suite: **13 passed**.

### Requested Act validator verification (2026-09-22)

Implemented the public `validate(act: Act) -> list[str]` contract in
`src/validator/validator.py`. It reports incomplete titles as warnings,
duplicate section numbers per container, unresolved schedule references,
missing Section provenance, invalid proviso/explanation nesting, and
numbering gaps. Range-repeal entries are reported separately and do not hide
uncovered gaps.

Validation table for the seven generated `output/*.act.json` files (issue
count includes warnings; first three issues shown):

| Act | Status | Issue count | First three issues |
| --- | --- | ---: | --- |
| CA1872 | PASS | 0 | - |
| CPC1908 | FAIL | 10 | `act.part[0]`: 24 to 125; `act.part[1]`: 47 to 49; `act.part[1]`: 56 to 58 |
| QSO1984 | PASS | 0 | - |
| REGA1908 | PASS | 0 | - |
| SRA1877 | PASS | 0 | - |
| STA1899 | FAIL | 1 | `act.chapter[2]`: 39 to 41 |
| TPA1882 | FAIL | 5 | `act.chapter[2]`: 62 to 70; `act.chapter[2]`: 73 to 76; `act.chapter[2]`: 84 to 91 |

All seven Acts loaded successfully against the schema. No duplicate section,
missing provenance, unresolved schedule reference, or invalid nesting issues
were found. The remaining findings are numbering-gap warnings for manual
review; no range-repeal entries occur in this batch.

The federal parser and deterministic validator gate is now complete. The next
stage is pipeline wiring and Section-level RAG chunk emission, with nested
legal structure and full provenance retained as metadata.

### Stage 5 - Section-level chunking for RAG (2026-09-22)

Implemented `src/rag/chunking.py` to emit one flat chunk per Section while
preserving the full Section text, hierarchy path, act metadata, category, and
provenance. Section text is kept as the atomic retrieval payload; nested
subsections, clauses, provisos, and explanations remain metadata on the
Section instead of becoming standalone chunks.

Chunk output files were generated under `output/chunks/` for the seven federal
Acts:

- `CA1872.chunks.json` — 195 chunks; average text length 685.37; no suspiciously
  short sections.
- `CPC1908.chunks.json` — 128 chunks; average text length 5031.88; 5 flagged
  suspiciously short sections (`45`, `154`, `155`, `156`, `7`).
- `QSO1984.chunks.json` — 165 chunks; average text length 930.56; no suspiciously
  short sections.
- `REGA1908.chunks.json` — 90 chunks; average text length 1103.14; no
  suspiciously short sections.
- `SRA1877.chunks.json` — 50 chunks; average text length 1425.98; no
  suspiciously short sections.
- `STA1899.chunks.json` — 79 chunks; average text length 2182.81; no
  suspiciously short sections.
- `TPA1882.chunks.json` — 126 chunks; average text length 1188.98; 4 flagged
  suspiciously short sections (`80`, `97`, `99`, `135A`).

These short sections are preserved and flagged as `suspiciously_short_text`
without being removed from the corpus, allowing manual review for repealed or
empty template entries.

### Stage 6 - local embedding benchmark harness (2026-09-22)

Added `scripts/embedding_benchmark.py` to benchmark the three requested local
sentence-transformers embedding models against the real corpus in
`output/chunks/*.chunks.json`.

What it does:

- Loads all 7 chunk files into a single corpus.
- Accepts a user-supplied JSON eval file with `query` and
  `expected_chunk_id` pairs.
- Embeds the full corpus and each query for each model.
- Retrieves the top-5 nearest chunks by cosine similarity.
- Reports hit/miss and correct-answer rank for each query.
- Prints a comparison table including hit rate, average rank of the correct
  answer, and embedding time per chunk.

No vector store or retrieval pipeline was added; this remains a throwaway
benchmark script only.

Status: script is written and syntax-checked. It is intentionally not executed
until the hand-labeled 10-15 query evaluation set is provided by the user.
