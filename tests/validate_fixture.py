"""Validate generated Block IR against hand-verified fixture answer keys.

This module reports extraction quality only. It does not infer or validate
legal structure.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
from pathlib import Path
from typing import Any


FUZZY_THRESHOLD = 0.82
WORD_DIGIT_PATTERN = re.compile(r"\b[A-Za-z]+\d+\b")
PAGE_PATTERN = re.compile(r"\bpages?\s+(\d+)(?:\s*-\s*(\d+))?\b", re.IGNORECASE)
SECTION_PATTERN = re.compile(r"\bsection\s+([0-9]+(?:[- ]?[A-Za-z]+)?)\b", re.IGNORECASE)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def answer_key_for(pdf_path: Path, fixtures_dir: Path) -> Path | None:
    candidates = (
        fixtures_dir / f"{pdf_path.name}.answer_key.json",
        pdf_path.with_suffix(".answer_key.json"),
        pdf_path.with_suffix(".answere_key.json"),
    )
    return next((candidate for candidate in candidates if candidate.exists()), None)


def normalize_text(text: str) -> str:
    return " ".join(text.split()).strip()


def section_variants(section_number: str) -> list[str]:
    variants = [section_number]
    if "-" in section_number:
        variants.append(section_number.replace("-", ""))
    return variants


def section_marker_pattern(section_number: str) -> re.Pattern[str]:
    alternatives = "|".join(re.escape(value) for value in section_variants(section_number))
    return re.compile(rf"(?<![\w-])(?:{alternatives})(?=\s*\.)", re.IGNORECASE)


def matching_section_blocks(blocks: list[dict[str, Any]], section_number: str) -> list[dict[str, Any]]:
    pattern = section_marker_pattern(section_number)
    return [block for block in blocks if pattern.search(block.get("text", ""))]


def diff_text(expected: str, actual: str) -> str:
    diff = "\n".join(
        difflib.unified_diff(
            [normalize_text(expected)],
            [normalize_text(actual)],
            fromfile="answer_key",
            tofile="block_ir",
            lineterm="",
        )
    )
    return diff[:4000]


def verified_text_match(
    blocks: list[dict[str, Any]], expected: str, section_number: str | None = None
) -> tuple[str, float, list[dict[str, Any]], str]:
    normalized_expected = normalize_text(expected)
    best_ratio = 0.0
    best_actual = ""
    best_blocks: list[dict[str, Any]] = []
    candidate_blocks = (
        matching_section_blocks(blocks, section_number)
        if section_number and matching_section_blocks(blocks, section_number)
        else blocks
    )

    for index, block in enumerate(candidate_blocks):
        for width in range(1, min(6, len(candidate_blocks) - index) + 1):
            window = candidate_blocks[index : index + width]
            actual = normalize_text(" ".join(item.get("text", "") for item in window))
            if normalized_expected and normalized_expected in actual:
                return "exact", 1.0, window, diff_text(expected, actual)
            ratio = difflib.SequenceMatcher(None, normalized_expected, actual).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_actual = actual
                best_blocks = window

    status = "fuzzy" if best_ratio >= FUZZY_THRESHOLD else "miss"
    return status, best_ratio, best_blocks, diff_text(expected, best_actual)


def parse_location(location: str) -> tuple[list[int], str | None]:
    pages: list[int] = []
    page_match = PAGE_PATTERN.search(location)
    if page_match:
        start = int(page_match.group(1))
        end = int(page_match.group(2) or start)
        pages = list(range(start, end + 1))
    section_match = SECTION_PATTERN.search(location)
    return pages, section_match.group(1) if section_match else None


def known_issue_checks(
    answer_key: dict[str, Any], blocks: list[dict[str, Any]], page_methods: list[str]
) -> list[dict[str, Any]]:
    checks = []
    for issue in answer_key.get("known_issues", []) or []:
        location = issue.get("location", "")
        pages, section_number = parse_location(location)
        if pages:
            location_blocks = [block for block in blocks if block.get("page") in pages]
            expected_methods = {page_methods[page - 1] for page in pages if 0 < page <= len(page_methods)}
        elif section_number:
            location_blocks = matching_section_blocks(blocks, section_number)
            expected_methods = {block_method for block_method in page_methods}
            expected_methods = {
                block.get("extraction_method")
                for block in location_blocks
                if block.get("page", 0) <= len(page_methods)
                for block_method in [page_methods[block["page"] - 1]]
            }
        else:
            location_blocks = []
            expected_methods = set()

        actual_methods = sorted({block.get("extraction_method") for block in location_blocks})
        method_mismatches = [
            {
                "page": block.get("page"),
                "expected": page_methods[block["page"] - 1]
                if 0 < block.get("page", 0) <= len(page_methods)
                else None,
                "actual": block.get("extraction_method"),
            }
            for block in location_blocks
            if 0 < block.get("page", 0) <= len(page_methods)
            and block.get("extraction_method") != page_methods[block["page"] - 1]
        ]
        checks.append(
            {
                "location": location,
                "note": issue.get("note", ""),
                "pages_checked": pages,
                "section_checked": section_number,
                "blocks_found": len(location_blocks),
                "extraction_methods": actual_methods,
                "expected_page_methods": sorted(expected_methods),
                "method_mismatches": method_mismatches,
                "status": "found" if location_blocks else "not_found",
            }
        )
    return checks


def validate_fixture(answer_key_path: Path, blocks_path: Path) -> dict[str, Any]:
    answer_key = load_json(answer_key_path)
    generated = load_json(blocks_path)
    blocks = generated.get("blocks", [])
    page_methods = generated.get("page_methods", [])

    sequence_coverage = []
    thin_sections = []
    section_matched_blocks: list[dict[str, Any]] = []
    for section_number in answer_key.get("section_numbers_in_order", []):
        matches = matching_section_blocks(blocks, str(section_number))
        section_matched_blocks.extend(matches)
        entry = {
            "section_number": section_number,
            "count": len(matches),
            "status": "found" if matches else "missing",
            "pages": sorted({block.get("page") for block in matches}),
        }
        sequence_coverage.append(entry)
        if matches and all(len(normalize_text(block.get("text", ""))) < 15 for block in matches):
            thin_sections.append(
                {
                    "section_number": section_number,
                    "pages": sorted({block.get("page") for block in matches}),
                    "texts": [block.get("text", "") for block in matches],
                }
            )

    verified_matches = {"exact": [], "fuzzy": [], "miss": []}
    for verified in answer_key.get("verified_sections", []):
        status, ratio, matched_blocks, diff = verified_text_match(
            blocks,
            verified.get("verbatim_text", ""),
            verified.get("section_number"),
        )
        result = {
            "section_number": verified.get("section_number"),
            "expected_text": verified.get("verbatim_text", ""),
            "similarity": round(ratio, 4),
            "matched_pages": sorted({block.get("page") for block in matched_blocks}),
            "matched_block_count": len(matched_blocks),
            "diff": diff if status == "fuzzy" else "",
        }
        verified_matches[status].append(result)

    artifact_blocks = []
    seen_artifacts: set[tuple[int, str]] = set()
    for block in section_matched_blocks:
        for match in WORD_DIGIT_PATTERN.finditer(block.get("text", "")):
            key = (block.get("page", 0), match.group(0))
            if key not in seen_artifacts:
                seen_artifacts.add(key)
                artifact_blocks.append(
                    {
                        "page": block.get("page"),
                        "text": block.get("text", ""),
                        "artifact": match.group(0),
                        "extraction_method": block.get("extraction_method"),
                    }
                )

    ocr_pages = [index + 1 for index, method in enumerate(page_methods) if method == "ocr"]
    native_pages = [index + 1 for index, method in enumerate(page_methods) if method == "native"]
    ocr_block_pages = {
        block.get("page")
        for block in blocks
        if block.get("extraction_method") == "ocr"
    }
    ocr_completion = {
        "ocr_pages_routed": len(ocr_pages),
        "native_pages_routed": len(native_pages),
        "ocr_pages_with_ocr_blocks": len(set(ocr_pages) & ocr_block_pages),
        "ocr_pages_with_zero_blocks": len(
            [page for page in ocr_pages if not any(block.get("page") == page for block in blocks)]
        ),
        "ocr_pages": ocr_pages,
    }

    missing_sections = [entry["section_number"] for entry in sequence_coverage if entry["status"] == "missing"]
    report = {
        "source_file": generated.get("source_file"),
        "answer_key": answer_key_path.name,
        "blocks_file": blocks_path.name,
        "summary": {
            "section_sequence_pass": not missing_sections,
            "verbatim_exact_count": len(verified_matches["exact"]),
            "verbatim_fuzzy_count": len(verified_matches["fuzzy"]),
            "verbatim_miss_count": len(verified_matches["miss"]),
            "known_issue_not_found_count": sum(
                check["status"] == "not_found" for check in known_issue_checks(answer_key, blocks, page_methods)
            ),
        },
        "section_sequence_coverage": sequence_coverage,
        "missing_section_numbers": missing_sections,
        "repealed_or_empty_sections": thin_sections,
        "verbatim_text_matches": verified_matches,
        "known_issues_cross_check": known_issue_checks(answer_key, blocks, page_methods),
        "footnote_digit_artifacts": artifact_blocks,
        "ocr_completion": ocr_completion,
    }
    return report


def print_summary(report: dict[str, Any]) -> None:
    summary = report["summary"]
    passed = (
        summary["section_sequence_pass"]
        and summary["verbatim_miss_count"] == 0
        and summary["known_issue_not_found_count"] == 0
        and report["ocr_completion"]["ocr_pages_with_zero_blocks"] == 0
    )
    status = "PASS" if passed else "FAIL"
    coverage = report["section_sequence_coverage"]
    print(f"{status}: {report['source_file']}")
    print(
        f"  sections: {sum(item['status'] == 'found' for item in coverage)} found, "
        f"{len(report['missing_section_numbers'])} missing; "
        f"thin: {len(report['repealed_or_empty_sections'])}"
    )
    print(
        f"  verbatim: {summary['verbatim_exact_count']} exact, "
        f"{summary['verbatim_fuzzy_count']} fuzzy, {summary['verbatim_miss_count']} misses"
    )
    ocr = report["ocr_completion"]
    print(
        f"  pages: {ocr['native_pages_routed']} native, {ocr['ocr_pages_routed']} OCR routed; "
        f"{ocr['ocr_pages_with_ocr_blocks']} OCR completed, {ocr['ocr_pages_with_zero_blocks']} empty"
    )
    print(f"  artifacts: {len(report['footnote_digit_artifacts'])}; report: {report['blocks_file'].replace('.blocks.json', '.validation_report.json')}")


def run(fixtures_dir: Path, output_dir: Path) -> list[Path]:
    reports = []
    for blocks_path in sorted(output_dir.glob("*.blocks.json")):
        pdf_stem = blocks_path.name.removesuffix(".blocks.json")
        pdf_path = fixtures_dir / f"{pdf_stem}.pdf"
        answer_key_path = answer_key_for(pdf_path, fixtures_dir)
        if answer_key_path is None:
            continue
        report = validate_fixture(answer_key_path, blocks_path)
        report_path = output_dir / f"{pdf_stem}.validation_report.json"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        print_summary(report)
        reports.append(report_path)
    return reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate Stage 1 fixture Block IR outputs.")
    parser.add_argument("--fixtures", type=Path, default=Path("fixtures"))
    parser.add_argument("--output", type=Path, default=Path("output"))
    args = parser.parse_args()
    run(args.fixtures, args.output)