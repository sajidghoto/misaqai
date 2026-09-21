from pathlib import Path
import json

from src.pipeline import extract_document
from src.parser.legal_parser import parse_blocks

FEDERAL_PDFS = {
    "CA1872": Path("pk-legal-corpus/00-foundation/PK-CA1872_Contract_Act_1872/PK-CA1872_source.pdf"),
    "SRA1877": Path("pk-legal-corpus/01-cross-cutting/PK-SRA1877_Specific_Relief_Act_1877/PK-SRA1877_Source.pdf"),
    "CPC1908": Path("pk-legal-corpus/01-cross-cutting/PK-CPC1908_Code_Civil_Procedure_1908/PK-CPC1908_souce.pdf"),
    "QSO1984": Path("pk-legal-corpus/01-cross-cutting/PK-QSO1984_Qanun_e_Shahadat_1984/PK-QSO1984_Source.pdf"),
    "REGA1908": Path("pk-legal-corpus/01-cross-cutting/PK-REGA1908_Registration_Act_1908/PK-REGA1908_source.pdf"),
    "STA1899": Path("pk-legal-corpus/01-cross-cutting/PK-STA1899_Stamp_Act_1899/PK-STA1899_source.pdf"),
    "TPA1882": Path("pk-legal-corpus/02-domain-property-rent/PK-TPA1882_Transfer_of_Property_Act_1882/PK-TPA1882_source.pdf"),
}

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


def count_sections(act):
    total = len(act.sections)
    for ch in act.chapters:
        total += len(ch.sections)
        for p in ch.parts:
            total += len(p.sections)
    for p in act.parts:
        total += len(p.sections)
        for ch in p.chapters:
            total += len(ch.sections)
    return total


def section_numbers(act):
    numbers = []
    def walk(node):
        numbers.extend(section.section_number for section in node.sections)
        for field in ("chapters", "parts"):
            for child in getattr(node, field, []):
                walk(child)
    walk(act)
    return numbers


results = []
for act_id, pdf_path in FEDERAL_PDFS.items():
    row = {"act_id": act_id, "pdf": str(pdf_path)}
    if not pdf_path.exists():
        row["error"] = "PDF NOT FOUND"
        print(f"{act_id}: PDF NOT FOUND at {pdf_path}")
        results.append(row)
        continue
    try:
        normalized = extract_document(pdf_path)
        (OUTPUT_DIR / f"{act_id}.blocks.json").write_text(
            normalized.model_dump_json(indent=2), encoding="utf-8"
        )
        row["extracted"] = True
        row["page_count"] = normalized.page_count
        row["blocks_count"] = len(normalized.blocks)
    except Exception as e:
        row["extracted"] = False
        row["extract_error"] = f"{type(e).__name__}: {e}"
        print(f"{act_id}: EXTRACTION FAILED - {row['extract_error']}")
        results.append(row)
        continue

    try:
        before_act = parse_blocks(normalized.blocks, filter_toc=False)
        act = parse_blocks(normalized.blocks)
        section_count = count_sections(act)
        before_numbers = section_numbers(before_act)
        after_numbers = section_numbers(act)
        row["section_count_before_toc_filter"] = len(before_numbers)
        row["section_count_after_toc_filter"] = len(after_numbers)
        row["duplicate_section_numbers"] = sorted(
            number for number in set(after_numbers) if after_numbers.count(number) > 1
        )
        row["parsed"] = True
        row["section_count"] = section_count
        row["chapter_count"] = len(act.chapters) + sum(len(p.chapters) for p in act.parts)
        row["part_count"] = len(act.parts)
        row["short_title"] = act.meta.short_title or None
        row["long_title"] = act.meta.long_title or None
        row["metadata_flags"] = [flag.note for flag in act.flags]
        (OUTPUT_DIR / f"{act_id}.act.json").write_text(
            act.model_dump_json(indent=2), encoding="utf-8"
        )
    except Exception as e:
        row["parsed"] = False
        row["parse_error"] = f"{type(e).__name__}: {e}"
        print(f"{act_id}: PARSE FAILED - {row['parse_error']}")
        results.append(row)
        continue

    print(
        f"{act_id}: OK - {row['page_count']} pages, {row['blocks_count']} blocks, "
        f"{section_count} sections, {row['chapter_count']} chapters, {row['part_count']} parts"
    )
    results.append(row)

summary_path = OUTPUT_DIR / "federal_stage13_summary.json"
summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
print(f"\nSummary written to {summary_path}")