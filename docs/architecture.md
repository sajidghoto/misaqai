# Architecture — Legal Document Structuring Pipeline

## Pipeline

    PDF
     │
     ▼
    PDF Characterizer            (native text vs scanned/image — page-level decision)
     │
     ├─ native text ──► PyMuPDF (primary extractor)
     │
     └─ scanned/image ─► PyMuPDF OCR via Tesseract (secondary, invoked only per page)
     │
     ▼
    Normalized Block IR           (Pydantic: text, page, bbox, font_size, font_name,
     │                             extraction_method["native"|"ocr"])
     ▼
    Legal Structure Parser        (Lark grammar — deterministic, no LLM)
     │
     ▼
    Legal Structure IR            (Pydantic: Act → Chapter/Part → Section →
     │                             Subsection → Clause → Proviso/Explanation,
     │                             Schedule linked by reference)
     ▼
    Deterministic Validator       (sequential numbering, orphaned refs, schema
     │                             conformance, provenance completeness)
     │
     ├─ fail ──► quarantine / review queue ──► (optional gated LLM repair) ──► re-enter validator
     │
     └─ pass ─► Verified Legal Units
                  │
                  ▼
             RAG Index            (chunk = Section; sub-levels are metadata only)

## Stage boundaries (build and validate in this order)

1. **Extraction** — Characterizer + PyMuPDF + OCR path. Output: raw Normalized
   Block IR per fixture. No legal semantics yet.
2. **Schema** — Pydantic models for both Block IR and Legal Structure IR.
3. **Grammar/Parser** — Lark grammar mined from real fixture text, consumes
   Block IR, emits Legal Structure IR.
4. **Validator** — deterministic checks against the Legal Structure IR.
5. **Pipeline wiring + chunking** — connects stages 1–4 end to end, emits
   Section-level chunks with full provenance for the RAG index.

Do not start a stage until the previous one passes all 4 fixtures.

## Key decisions and why

- **PyMuPDF primary / PyMuPDF OCR secondary**: fast and reliable on native-text
  PDFs (3 of 4 fixtures); OCR invoked only where the Characterizer detects a
  scanned page, keeping the common case cheap.
- **Grammar-based parser, not an LLM**: the numbering hierarchy is a known,
  finite, regular grammar (per Pakistan's Legislative Drafting Manual) —
  matches established practice in production legal-data systems (e.g.
  Akoma Ntoso tooling, South Africa's Slaw/Bluebell), which stay deterministic
  for structure and validation, using an LLM (if at all) only for narrow,
  gated ingestion edge cases.
- **Section as atomic chunk unit**: it's the level legal citation and
  cross-reference operate at; splitting below it (e.g. isolating a Proviso)
  destroys legal meaning.
- **Provenance threaded end to end**: without page/bbox/extraction_method
  surviving into the final IR, the RAG system can't cite back to an exact
  source location — the entire point of doing this over a flat-text dataset.

## Fixtures

4 hand-checked documents in /fixtures/, one federal, one Sindh, one Punjab
(scanned/OCR), one more — each paired with a `*.answer_key.json` manually
verified against the source PDF. These are ground truth for every stage;
do not treat automated tool output as truth without checking against them.