from pathlib import Path
import json

from src.normalize.block_ir import NormalizedBlock
from src.parser.legal_parser import parse_blocks

OUTPUT_DIR = Path("output")

def collect_sections(act_dict):
    sections = []
    def walk(node, prefix=""):
        for s in node.get("sections", []):
            sections.append((s["section_number"], s.get("marginal_note"), s["text"][:120]))
        for ch in node.get("chapters", []):
            walk(ch, prefix + f"Ch.{ch.get('chapter_number')} ")
        for p in node.get("parts", []):
            walk(p, prefix + f"Part {p.get('part_number')} ")
    walk(act_dict)
    return sections

for act_file in sorted(OUTPUT_DIR.glob("*.act.json")):
    act_id = act_file.stem.replace(".act", "")
    data = json.loads(act_file.read_text(encoding="utf-8"))
    blocks_data = json.loads((OUTPUT_DIR / f"{act_id}.blocks.json").read_text(encoding="utf-8"))
    blocks = [NormalizedBlock.model_validate(block) for block in blocks_data["blocks"]]
    before = parse_blocks(blocks, filter_toc=False)
    after = parse_blocks(blocks)
    sections = collect_sections(data)
    before_sections = collect_sections(before.model_dump())
    after_numbers = [number for number, _, _ in sections]
    duplicates = sorted(number for number in set(after_numbers) if after_numbers.count(number) > 1)
    print(f"\n{'='*60}\n{act_id} — {len(sections)} sections found\n{'='*60}")
    print(f"Section count before/after TOC filtering: {len(before_sections)} / {len(sections)}")
    print("Extracted short_title:", data.get("meta", {}).get("short_title") or "[NOT FOUND]")
    print("Extracted long_title:", data.get("meta", {}).get("long_title") or "[NOT FOUND]")
    print("Meta:", data.get("meta"))
    print("\nFirst 5 sections:")
    for num, note, preview in sections[:5]:
        print(f"  [{num}] {note} — {preview}...")
    print("\nLast 5 sections:")
    for num, note, preview in sections[-5:]:
        print(f"  [{num}] {note} — {preview}...")
    numbers = [n for n, _, _ in sections]
    dupes = [n for n in set(numbers) if numbers.count(n) > 1]
    if dupes:
        print(f"\n  WARNING - duplicate section numbers: {dupes}")
    else:
        print("\n  No duplicate section numbers")