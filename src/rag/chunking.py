from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.schema.legal_structure_ir import Act, Chapter, Part, Section


def _clean_title(value: str | None) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    value = value.rstrip(".")
    prefixes = (
        "This Act may be called the ",
        "This Act may be cited as the ",
        "This Act may be cited as ",
    )
    for prefix in prefixes:
        if value.lower().startswith(prefix.lower()):
            value = value[len(prefix):]
            break
    return value.strip()


def _section_text(section: Section) -> str:
    fragments: list[str] = []
    if section.text.strip():
        fragments.append(section.text.strip())
    for subsection in section.subsections:
        if subsection.text.strip():
            fragments.append(subsection.text.strip())
        for clause in subsection.clauses:
            if clause.text.strip():
                fragments.append(clause.text.strip())
            for subclause in clause.subclauses:
                if subclause.text.strip():
                    fragments.append(subclause.text.strip())
            for proviso in clause.provisos:
                if proviso.text.strip():
                    fragments.append(proviso.text.strip())
            for explanation in clause.explanations:
                if explanation.text.strip():
                    fragments.append(explanation.text.strip())
    for proviso in section.provisos:
        if proviso.text.strip():
            fragments.append(proviso.text.strip())
    for explanation in section.explanations:
        if explanation.text.strip():
            fragments.append(explanation.text.strip())
    return "\n\n".join(part for part in fragments if part).strip()


def _iter_sections(act: Act):
    for chapter in act.chapters:
        for section in chapter.sections:
            yield section, chapter, None
        for part in chapter.parts:
            for section in part.sections:
                yield section, chapter, part
    for part in act.parts:
        for section in part.sections:
            yield section, None, part
        for chapter in part.chapters:
            for section in chapter.sections:
                yield section, chapter, part
    for section in act.sections:
        yield section, None, None


def _path_for_section(act: Act, section: Section, chapter: Chapter | None, part: Part | None) -> str:
    act_title = _clean_title(act.meta.short_title) or _clean_title(act.meta.long_title) or "Act"
    steps: list[str] = [act_title]
    if chapter is not None:
        if chapter.chapter_number:
            steps.append(f"Chapter {chapter.chapter_number}")
        elif chapter.chapter_title:
            steps.append(chapter.chapter_title)
    if part is not None and chapter is None:
        if part.part_number:
            steps.append(f"Part {part.part_number}")
        elif part.part_title:
            steps.append(part.part_title)
    steps.append(f"Section {section.section_number}")
    return " > ".join(steps)


def chunk_act(act: Act, act_id: str, category: str = "") -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for section, chapter, part in _iter_sections(act):
        text = _section_text(section)
        flags: list[str] = []
        if len(text) < 10:
            flags.append("suspiciously_short_text")

        provenance = {
            "pages": sorted({item.page for item in section.provenance}),
            "extraction_methods": sorted({item.extraction_method for item in section.provenance}),
            "records": [
                {
                    "page": item.page,
                    "bbox": list(item.bbox),
                    "extraction_method": item.extraction_method,
                }
                for item in section.provenance
            ],
        }

        chunks.append(
            {
                "chunk_id": f"{act_id}_s{section.section_number}",
                "text": text,
                "hierarchy_path": _path_for_section(act, section, chapter, part),
                "act_id": act_id,
                "act_short_title": _clean_title(act.meta.short_title),
                "jurisdiction": act.meta.jurisdiction,
                "category": category,
                "section_number": section.section_number,
                "marginal_note": section.marginal_note,
                "schedule_refs": list(section.schedule_refs),
                "provenance": provenance,
                "flags": flags,
            }
        )
    return chunks


def write_chunk_file(act: Act, act_id: str, output_dir: Path, category: str = "") -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks = chunk_act(act, act_id=act_id, category=category)
    out_path = output_dir / f"{act_id}.chunks.json"
    out_path.write_text(json.dumps(chunks, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out_path


def summarize_chunks(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    lengths = [len(str(chunk.get("text") or "")) for chunk in chunks]
    short = [
        {
            "chunk_id": chunk["chunk_id"],
            "section_number": chunk["section_number"],
            "length": len(str(chunk.get("text") or "")),
        }
        for chunk in chunks
        if len(str(chunk.get("text") or "")) < 10
    ]
    return {
        "count": len(chunks),
        "average_text_length": round(sum(lengths) / len(lengths), 2) if lengths else 0.0,
        "short_sections": short,
    }
