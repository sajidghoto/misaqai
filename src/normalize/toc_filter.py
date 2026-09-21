from __future__ import annotations

import re

from src.normalize.block_ir import NormalizedBlock


SECTION_PATTERN_RE = re.compile(r"\d+\.\s")
SECTION_ONE_RE = re.compile(r"^\s*1\.\s", re.S)
SHORT_TITLE_RE = re.compile(r"(?:This Act may be called|This Act may be cited as)", re.I)


def _section_marker_count(block: NormalizedBlock) -> int:
    return len(SECTION_PATTERN_RE.findall(block.text))


def _is_body_section_one(block: NormalizedBlock) -> bool:
    return bool(SECTION_ONE_RE.match(block.text))


def split_toc_and_body(
    blocks: list[NormalizedBlock],
) -> tuple[list[NormalizedBlock], list[NormalizedBlock]]:
    """Split the leading contents region from the operative body."""
    candidates = [
        (index, block)
        for index, block in enumerate(blocks)
        if _is_body_section_one(block)
    ]
    if not candidates:
        return blocks, []
    short_title_candidates = [candidate for candidate in candidates if SHORT_TITLE_RE.search(candidate[1].text)]
    if short_title_candidates:
        body_start, _ = min(short_title_candidates, key=lambda candidate: candidate[0])
    else:
        body_start, _ = max(
            candidates,
            key=lambda candidate: (
                len(candidate[1].text.strip()),
                -_section_marker_count(candidate[1]),
            ),
        )
    return blocks[:body_start], blocks[body_start:]