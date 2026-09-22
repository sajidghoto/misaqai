from src.schema.legal_structure_ir import Act, ActMeta, Chapter, Section
from src.rag.chunking import chunk_act


def test_chunk_act_creates_section_chunks_and_flags_short_sections():
    act = Act(
        meta=ActMeta(
            jurisdiction="Federal",
            enacting_authority="Parliament",
            assent_authority="President",
            long_title="THE TEST ACT, 2026",
            short_title="Test Act, 2026",
        ),
        chapters=[
            Chapter(
                chapter_number="I",
                chapter_title="General Provisions",
                sections=[
                    Section(
                        section_number="1",
                        marginal_note="Introductory section",
                        text="This is a valid section with enough words to be retained.",
                        provenance=[{"page": 1, "bbox": (10.0, 20.0, 30.0, 40.0), "extraction_method": "native"}],
                    ),
                    Section(
                        section_number="2",
                        marginal_note="Empty section",
                        text="x",
                        provenance=[{"page": 1, "bbox": (10.0, 20.0, 30.0, 40.0), "extraction_method": "native"}],
                    ),
                ],
            )
        ],
    )

    chunks = chunk_act(act, act_id="TEST123", category="01-cross-cutting")

    assert len(chunks) == 2
    assert chunks[0]["chunk_id"] == "TEST123_s1"
    assert chunks[0]["hierarchy_path"] == "Test Act, 2026 > Chapter I > Section 1"
    assert chunks[1]["flags"] == ["suspiciously_short_text"]
    assert chunks[1]["provenance"]["pages"] == [1]
