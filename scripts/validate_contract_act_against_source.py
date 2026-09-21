from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import fitz

from src.parser.legal_parser import parse_blocks


PDF_PATH = Path(
    "pk-legal-corpus/00-foundation/PK-CA1872_Contract_Act_1872/PK-CA1872_source.pdf"
)
BLOCKS_PATH = Path("output/CA1872.blocks.json")


def _collect_sections(node) -> list:
    sections = list(node.sections)
    for field in ("chapters", "parts"):
        for child in getattr(node, field, []):
            sections.extend(_collect_sections(child))
    return sections


def source_ground_truth() -> dict:
    with fitz.open(PDF_PATH) as document:
        contents = " ".join(document[index].get_text("text") for index in range(10))

    normalized = re.sub(r"\s+", " ", contents)
    assert "76 to 123. [Repealed]" in normalized
    assert "239 to 266. [Repealed]" in normalized
    assert "SCHEDULE [Repealed]" in normalized
    assert "178A. Pledge by person in possession under voidable contract" in normalized

    operative_numbers = [str(number) for number in range(1, 76)]
    operative_numbers.extend(str(number) for number in range(124, 239))
    return {
        "operative_section_numbers": operative_numbers,
        "special_operative_sections": ["178A"],
        "repealed_ranges": ["76-123", "239-266"],
        "repealed_schedule": True,
    }


def validate_output() -> dict:
    ground_truth = source_ground_truth()
    data = json.loads(BLOCKS_PATH.read_text(encoding="utf-8"))
    act = parse_blocks(data["blocks"])
    sections = _collect_sections(act)
    actual_numbers = [section.section_number for section in sections]
    expected_numbers = (
        ground_truth["operative_section_numbers"]
        + ground_truth["special_operative_sections"]
    )
    return {
        "source": str(PDF_PATH),
        "source_operative_count": len(expected_numbers),
        "source_numeric_slots": 266,
        "source_repealed_ranges": ground_truth["repealed_ranges"],
        "source_repealed_slot_count": 48 + 28,
        "source_repealed_schedule": ground_truth["repealed_schedule"],
        "output_section_count": len(actual_numbers),
        "missing_operative_sections": [
            number for number in expected_numbers if number not in actual_numbers
        ],
        "unexpected_output_sections": [
            number for number in actual_numbers if number not in expected_numbers
        ],
        "duplicate_output_sections": sorted(
            number for number, count in Counter(actual_numbers).items() if count > 1
        ),
        "output_repealed_schedule": [
            schedule.content for schedule in act.schedules
            if schedule.schedule_name.upper() == "SCHEDULE"
        ],
        "passes": set(expected_numbers) == set(actual_numbers)
        and not any(
            count > 1 for count in Counter(actual_numbers).values()
        ),
    }


if __name__ == "__main__":
    report = validate_output()
    print(json.dumps(report, indent=2))