# How to build an answer_key.json

For each fixture PDF, open the actual PDF and manually record its true
structure below. This is not generated — it's what you confirm by reading
the document yourself. It's the ground truth every stage gets checked against.

Only fill in what you can verify by looking at the PDF. If something is
genuinely absent (no Chapters, no Schedules), leave it as an empty array —
don't guess or pad it.

Minimum you must verify by hand for each fixture:
- Total number of Sections, and their exact numbers (so gaps/renumbering
  are catchable)
- Jurisdiction + enacting/assent authority (from the enacting clause)
- At least 2-3 full Section texts, verbatim, including any Sub-section/
  Clause/Proviso nesting inside them — pick ones that are structurally
  representative (one simple section, one with a Proviso, one with a
  Schedule reference)
- Every Schedule name that exists in the document
- For the OCR'd Punjab fixture specifically: note any pages where the
  scan quality is poor enough that even you're unsure of the correct
  reading — mark these explicitly, don't silently pick one interpretation