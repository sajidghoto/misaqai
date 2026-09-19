from src.schema.legal_structure_ir import (
	Act,
	ActMeta,
	Chapter,
	Clause,
	Explanation,
	Proviso,
	Section,
	Subclause,
	Subsection,
)


def test_nested_legal_structure_ir_composes():
	act = Act(
		meta=ActMeta(
			jurisdiction="Federal",
			enacting_authority="Parliament",
			assent_authority="President",
			long_title="A placeholder long title.",
			short_title="Placeholder Act",
			commencement_date="2026-01-01",
		),
		preamble="A placeholder preamble.",
		chapters=[
			Chapter(
				chapter_number="I",
				chapter_title="Placeholder Chapter",
				sections=[
					Section(
						section_number="1",
						text="Placeholder section text.",
						subsections=[
							Subsection(
								subsection_number="(1)",
								text="Placeholder subsection text.",
								clauses=[
									Clause(
										clause_id="(a)",
										text="Placeholder clause text.",
										provisos=[Proviso(text="Provided that placeholder condition.")],
										subclauses=[Subclause(subclause_id="(i)", text="Placeholder subclause text.")],
									)
								],
							)
						],
					)
				]
			)
		]
	)

	assert act.chapters[0].sections[0].subsections[0].clauses[0].provisos[0].text.startswith("Provided")