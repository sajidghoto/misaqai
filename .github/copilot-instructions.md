# Copilot Instructions — Pakistani Legal Document Structuring Pipeline

## Goal
Convert Pakistani federal/provincial statute PDFs into a validated, hierarchical,
provenance-tracked JSON corpus for a production RAG system.

## Architecture — do not deviate without asking
PDF → Characterizer (native text vs scanned) → PyMuPDF (primary extractor) /
PyMuPDF OCR via Tesseract (secondary, only when scanned) → Normalized Block IR
(Pydantic: text, page, bbox, font_size, font_name, extraction_method) →
Legal Structure Parser (Lark grammar, deterministic — NOT an LLM) →
Legal Structure IR (Pydantic: Act > Chapter/Part > Section > Subsection >
Clause > Proviso/Explanation, Schedule linked by reference) →
Deterministic Validator (sequential numbering, orphaned refs, schema
conformance) → Verified units → RAG index (chunk = Section; everything below
Section is nested metadata, never a separate chunk).

## Hard rules
- Section is the atomic chunk/retrieval unit. Never split, chunk, or emit
  anything below Section as a top-level/standalone unit.
- Sub-section, Clause, Sub-clause, Proviso, Explanation always nest inside
  their parent Section — never siblings, never standalone.
- Schedules are referenced by name from body text (schedule_ref field), never
  duplicated/inlined into a section's text.
- Marginal notes and amendment footnotes (e.g. "Subs. by Act X of Year, s.2")
  are metadata fields, never merged into body "text".
- No LLM anywhere in the core parsing/validation path. If an LLM repair stage
  is added later, it is narrowly scoped, only engages on validator-flagged
  failures, and its output must re-enter the deterministic validator before
  acceptance — never bypasses it.
- Every extracted text unit carries provenance (page, bbox, extraction_method)
  through every stage into the final IR. Never drop it.
- Numbering hierarchy, in nesting order: Chapter (Roman) → Part → Section
  (Arabic) → Sub-section "(1)" → Clause "(a)" → Sub-clause "(i)" → un-numbered
  Proviso ("Provided that...") / Explanation ("Explanation.—"), each attached
  to its immediately preceding clause/section.
- Do not renumber or "fix" gaps in source numbering. Preserve exactly as
  written; flag anomalies instead of silently correcting them.
- Federal vs provincial acts share one grammar. Only `jurisdiction` and
  `enacting_authority` fields differ (Federal/President vs
  Sindh|Punjab|KP|Balochistan Assembly/Governor) — detect from the enacting
  clause and assent line, never assume.

## Fixtures (ground truth — do not treat as optional)
/fixtures/ contains 3 hand-checked documents (1 federal, 1 Sindh, 1 Punjab OCR)
against these before being considered done. Do not generalize to documents
outside /fixtures/ until a stage passes all 4.

## Input locations
- /fixtures/ — 3 hand-verified documents with answer keys. Ground truth only.
  Never write pipeline output here.
- /pk-legal-corpus — real production PDFs to be processed, no answer key, not to be used for validating correctness.
- /output/ — all generated JSON lands here, gitignored.

## Session workflow
1. Read docs/progress.md before starting any task to see what's already done.
2. Work one stage at a time (see docs/architecture.md for stage breakdown).
   Do not jump ahead to later stages before earlier ones pass their fixtures.
3. At the end of a session, update docs/progress.md: what was built, what
   passed/failed against fixtures, what's flagged for manual review.
4. Ask before installing any new dependency not already in requirements.txt.
5. Output code only for the stage requested — do not refactor unrelated files
   unless explicitly asked.