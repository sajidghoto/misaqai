import json
from pathlib import Path

from src.normalize.block_ir import NormalizedBlock
from src.normalize.toc_filter import split_toc_and_body


OUTPUT_DIR = Path(__file__).parents[1] / "output"


def _fixture_blocks(name: str) -> list[NormalizedBlock]:
    data = json.loads((OUTPUT_DIR / f"{name}.blocks.json").read_text(encoding="utf-8"))
    return [NormalizedBlock.model_validate(block) for block in data["blocks"]]


def test_real_fixture_section_one_blocks_are_body_blocks():
    for name in ("CA1872", "PK-SRA1877_Source"):
        toc_blocks, body_blocks = split_toc_and_body(_fixture_blocks(name))
        section_one = next(
            block for block in body_blocks
            if block.text.lstrip().startswith("1.") and "may be called" in block.text
        )

        assert section_one not in toc_blocks
        assert len(toc_blocks) + len(body_blocks) > 0


def test_real_fixtures_have_no_post_body_toc_island():
    for name in ("CA1872", "PK-SRA1877_Source"):
        blocks = _fixture_blocks(name)
        _, body_blocks = split_toc_and_body(blocks)
        body_start = blocks.index(body_blocks[0])
        later_operative_section_one = [
            block for block in blocks[body_start + 1:]
            if block.text.lstrip().startswith("1.") and "may be called" in block.text
        ]

        assert not later_operative_section_one


def test_cpc_body_starts_at_operative_short_title():
    blocks = _fixture_blocks("CPC1908")
    toc_blocks, body_blocks = split_toc_and_body(blocks)

    assert body_blocks[0].page == 11
    assert body_blocks[0].text.startswith("1. Short title")
    assert toc_blocks[-1].page <= body_blocks[0].page